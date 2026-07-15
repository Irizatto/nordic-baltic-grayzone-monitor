"""Explainable, review-priority anomaly scoring (rules v1)."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import DOCS_DATA, PROCESSED_DATA, ROOT
from utils_geo import haversine_km, point_in_bbox, point_to_linestring_distance_km

HISTORY_PATH = PROCESSED_DATA / "ais_history.jsonl"
MULTIPLIERS = {"tanker":1.0,"cargo":1.0,"lng":1.0,"tug":0.8,"research":0.8,"service":0.8,"fishing":0.4,"unknown":0.6}
LEVELS = ((12,"Critical Review Priority"),(8,"High Review Priority"),(5,"Watch"),(0,"Normal"))


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _rules(rule_id: str, points: int, evidence: str) -> dict:
    return {"rule_id":rule_id,"points":points,"evidence":evidence}


def risk_level_for_score(score: int) -> str:
    """Return the exact v1 review-priority level for a multiplied score."""
    return next(level for threshold,level in LEVELS if score >= threshold)


def _layers() -> list[dict]:
    result = []
    for filename in ("cables.geojson","pipelines.geojson"):
        try:
            payload = json.loads(
                (DOCS_DATA / "layers" / filename).read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            # A damaged infrastructure snapshot must not stop AIS/SAR updates.
            # The EMODnet adapter and metadata surface the degraded layer state.
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            continue
        result.extend(
            feature
            for feature in payload["features"]
            if feature.get("properties", {}).get("scoring_eligible", True)
        )
    return result


def _nearest_with_raw_distance(vessel: dict, features: list[dict] | None = None) -> dict:
    closest = None
    for feature in features or _layers():
        distance = point_to_linestring_distance_km(vessel["lat"], vessel["lon"], feature["geometry"]["coordinates"])
        if closest is None or distance < closest["raw_distance_km"]:
            props = feature["properties"]
            closest = {"name":props["name"],"type":props["category"],"raw_distance_km":distance}
    return closest or {"name":"Not available","type":"not available","raw_distance_km":None}


def nearest_infrastructure(vessel: dict, features: list[dict] | None = None) -> dict:
    """Return the nearest eligible cable/pipeline with display-rounded distance."""
    closest = _nearest_with_raw_distance(vessel, features)
    raw = closest["raw_distance_km"]
    return {"name":closest["name"],"type":closest["type"],"distance_km":round(raw,1) if raw is not None else None}


def _watchlist() -> list[dict]:
    path = ROOT / "data" / "reference" / "watchlist_vessels.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _match_watchlist(vessel: dict, rows: list[dict]) -> list[dict]:
    matched_sources = set()
    for row in rows:
        if any(str(vessel.get(k,"")).strip().lower() and str(vessel.get(k,"")).strip().lower() == str(row.get(k,"")).strip().lower() for k in ("imo","mmsi","name")):
            source = row.get("source","").lower()
            if source in {"sanctions", "shadow_fleet"}:
                matched_sources.add(source)
    matches = []
    if "sanctions" in matched_sources:
        matches.append(_rules("sanctions_match",8,"Matched sanctions watchlist entry"))
    if "shadow_fleet" in matched_sources:
        matches.append(_rules("shadow_fleet_match",5,"Matched shadow-fleet watchlist entry"))
    return matches


def _history_rules(vessel: dict, history: list[dict], nearest_raw: dict, sar: list[dict], features: list[dict] | None) -> list[dict]:
    """Apply only rules backed by stored earlier positions; empty history fires none."""
    if not history:
        return []
    now = _time(vessel["timestamp"])
    prior = sorted((item for item in history if _time(item["timestamp"]) < now), key=lambda item:_time(item["timestamp"]))
    if not prior:
        return []
    rules, all_points = [], prior + [vessel]
    gaps = [(_time(b["timestamp"])-_time(a["timestamp"])).total_seconds()/3600 for a,b in zip(all_points,all_points[1:])]
    gap = max(gaps, default=0)
    if gap > 18: rules.append(_rules("ais_gap_18h",4,f"AIS reporting gap of {gap:.1f} hours"))
    elif gap > 6: rules.append(_rules("ais_gap_6h",2,f"AIS reporting gap of {gap:.1f} hours"))
    longest_span, episode_start, episode_end, previous_time = 0.0, None, None, None
    for point in all_points:
        point_time = _time(point["timestamp"])
        if previous_time is not None and point_time-previous_time > timedelta(hours=6):
            episode_start, episode_end = None, None
        point_nearest = _nearest_with_raw_distance(point, features)
        is_near_and_slow = point_nearest["raw_distance_km"] is not None and point_nearest["raw_distance_km"] <= 10 and float(point.get("speed",0)) < 6
        if is_near_and_slow:
            episode_start = episode_start or point_time
            episode_end = point_time
            longest_span = max(longest_span, (episode_end-episode_start).total_seconds()/3600)
        else:
            episode_start, episode_end = None, None
        previous_time = point_time
    if longest_span > 6: rules.append(_rules("low_speed_near_infra_6h",4,f"Speed below 6 kn near schematic infrastructure for {longest_span:.1f} hours"))
    elif longest_span > 2: rules.append(_rules("low_speed_near_infra_2h",2,f"Speed below 6 kn near schematic infrastructure for {longest_span:.1f} hours"))
    changes = [abs(((float(b.get("course",0))-float(a.get("course",0))+180)%360)-180) for a,b in zip(all_points,all_points[1:])]
    if sum(change >= 60 for change in changes) >= 3: rules.append(_rules("zigzag_or_anchor_drag_proxy",2,"Repeated large course changes in stored AIS positions"))
    identity_fields = ("name","mmsi","imo","callsign","flag")
    normalize = lambda value: " ".join(str(value or "").split()).casefold()
    if any(normalize(p.get(field)) != normalize(vessel.get(field)) for p in prior for field in identity_fields): rules.append(_rules("identity_change",3,"Identity field changed compared with stored AIS position"))
    sensitive = _sensitive_bboxes()
    visits = sum(any(point_in_bbox(p["lat"],p["lon"],*box) for box in sensitive) for p in all_points)
    if visits >= 3: rules.append(_rules("repeat_sensitive_area_presence",2,"Repeated stored presence inside a sensitive-area bounding box"))
    if gap > 6:
        gap_pairs = [(a,b) for a,b in zip(all_points,all_points[1:]) if (_time(b["timestamp"])-_time(a["timestamp"])).total_seconds() > 6*3600]
        for detection in sar:
            if detection.get("matched"):
                continue
            detection_time = _time(detection["timestamp"])
            for start, end in gap_pairs:
                start_time, end_time = _time(start["timestamp"]), _time(end["timestamp"])
                near_time = start_time-timedelta(hours=12) <= detection_time <= end_time+timedelta(hours=12)
                near_space = min(haversine_km(start["lat"],start["lon"],detection["lat"],detection["lon"]),haversine_km(end["lat"],end["lon"],detection["lat"],detection["lon"])) <= 10
                if near_time and near_space:
                    rules.append(_rules("sar_unmatched_near_ais_gap",5,"Unmatched SAR lead is spatially and temporally close to an AIS gap"))
                    return rules
    return rules


def _sensitive_bboxes() -> list[tuple]:
    payload = json.loads((DOCS_DATA / "layers" / "sensitive_areas.geojson").read_text(encoding="utf-8"))
    boxes = []
    for feature in payload["features"]:
        ring = feature["geometry"]["coordinates"][0]
        lons, lats = zip(*ring); boxes.append((min(lats),max(lats),min(lons),max(lons)))
    return boxes


def score_vessel(vessel: dict, history: list[dict] | None = None, sar: list[dict] | None = None, features: list[dict] | None = None, watchlist: list[dict] | None = None) -> dict:
    """Score one vessel using stable v1 rule IDs and explainable evidence."""
    item = dict(vessel)
    kind = str(vessel.get("ship_type") or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
    if kind in {"naval","law_enforcement"}:
        item.update({"risk_score":0,"risk_level":"Normal","triggered_rules":[],"nearest_infrastructure":nearest_infrastructure(vessel,features)})
        return item
    nearest_raw = _nearest_with_raw_distance(vessel,features)
    distance = nearest_raw["raw_distance_km"]
    nearest = {"name":nearest_raw["name"],"type":nearest_raw["type"],"distance_km":round(distance,1) if distance is not None else None}
    rules = []
    if distance is not None:
        if distance <= 1: rules.append(_rules("infra_proximity_1km",3,f"{distance:.1f} km from {nearest['type']} {nearest['name']}"))
        elif distance <= 5: rules.append(_rules("infra_proximity_5km",2,f"{distance:.1f} km from {nearest['type']} {nearest['name']}"))
        elif distance <= 10: rules.append(_rules("infra_proximity_10km",1,f"{distance:.1f} km from {nearest['type']} {nearest['name']}"))
    rules.extend(_history_rules(vessel,history or [],nearest_raw,sar or [],features))
    rules.extend(_match_watchlist(vessel,watchlist if watchlist is not None else _watchlist()))
    if vessel.get("suspected_sts_rendezvous"): rules.append(_rules("sts_rendezvous",4,"Suspected ship-to-ship rendezvous lead supplied by upstream analysis"))
    raw = sum(rule["points"] for rule in rules)
    score = round(raw * MULTIPLIERS.get(kind,0.6))
    level = risk_level_for_score(score)
    item.update({"risk_score":score,"risk_level":level,"triggered_rules":rules,"nearest_infrastructure":nearest})
    return item


def _identity_keys(record: dict) -> list[str]:
    """Build conservative aliases so an MMSI change can still find prior identity history."""
    keys = []
    for field in ("mmsi", "imo", "callsign", "name"):
        value = " ".join(str(record.get(field) or "").split()).casefold()
        if value:
            keys.append(f"{field}:{value}")
    return keys


def history_for_vessel(history_index: dict[str, list[dict]], vessel: dict) -> list[dict]:
    """Return de-duplicated prior records matching any stable identity alias."""
    matched = {}
    strong_keys = []
    for field in ("mmsi", "imo", "callsign"):
        value = " ".join(str(vessel.get(field) or "").split()).casefold()
        if value:
            strong_keys.append(f"{field}:{value}")
    for key in strong_keys:
        for record in history_index.get(key, []):
            identity = (str(record.get("mmsi") or ""), str(record.get("timestamp") or ""), str(record.get("source") or ""))
            matched[identity] = record
    if not matched and not vessel.get("imo") and not vessel.get("callsign"):
        name = " ".join(str(vessel.get("name") or "").split()).casefold()
        for record in history_index.get(f"name:{name}", []) if name else []:
            identity = (str(record.get("mmsi") or ""), str(record.get("timestamp") or ""), str(record.get("source") or ""))
            matched[identity] = record
    return sorted(matched.values(), key=lambda item:_time(item["timestamp"]))


def update_history(vessels: list[dict], path: Path = HISTORY_PATH, now: datetime | None = None) -> dict[str,list[dict]]:
    """Append source positions and retain only the previous 14 days."""
    now = now or datetime.now(timezone.utc); cutoff = now-timedelta(days=14); retained=[]
    seen = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record=json.loads(line)
                timestamp = _time(record["timestamp"])
                key = (str(record.get("mmsi") or ""), record["timestamp"], str(record.get("source") or ""))
                if cutoff <= timestamp <= now+timedelta(minutes=5) and key not in seen:
                    retained.append(record); seen.add(key)
            except (ValueError,json.JSONDecodeError,KeyError): pass
    current_keys = {(str(record.get("mmsi") or ""),str(record.get("timestamp") or ""),str(record.get("source") or "")) for record in vessels}
    additions = []
    for record in vessels:
        try:
            timestamp = _time(record["timestamp"])
            key = (str(record.get("mmsi") or ""),record["timestamp"],str(record.get("source") or ""))
            if cutoff <= timestamp <= now+timedelta(minutes=5) and key not in seen:
                additions.append(record); seen.add(key)
        except (ValueError,KeyError):
            continue
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8") as handle:
        for record in retained+additions: handle.write(json.dumps(record)+"\n")
    grouped={}
    for record in retained:
        key = (str(record.get("mmsi") or ""),str(record.get("timestamp") or ""),str(record.get("source") or ""))
        if key not in current_keys:
            for identity_key in _identity_keys(record):
                grouped.setdefault(identity_key,[]).append(record)
    return grouped

