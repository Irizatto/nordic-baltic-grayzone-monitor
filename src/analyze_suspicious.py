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
    return datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(timezone.utc)


def _rules(rule_id: str, points: int, evidence: str) -> dict:
    return {"rule_id":rule_id,"points":points,"evidence":evidence}


def _layers() -> list[dict]:
    result = []
    for filename in ("cables.geojson","pipelines.geojson"):
        payload = json.loads((DOCS_DATA / "layers" / filename).read_text(encoding="utf-8"))
        result.extend(payload["features"])
    return result


def nearest_infrastructure(vessel: dict, features: list[dict] | None = None) -> dict:
    """Return nearest schematic cable/pipeline infrastructure."""
    closest = None
    for feature in features or _layers():
        distance = point_to_linestring_distance_km(vessel["lat"], vessel["lon"], feature["geometry"]["coordinates"])
        if closest is None or distance < closest["distance_km"]:
            props = feature["properties"]
            closest = {"name":props["name"],"type":props["category"],"distance_km":round(distance,1)}
    return closest or {"name":"Not available","type":"not available","distance_km":None}


def _watchlist() -> list[dict]:
    path = ROOT / "data" / "reference" / "watchlist_vessels.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _match_watchlist(vessel: dict, rows: list[dict]) -> list[dict]:
    matches = []
    for row in rows:
        if any(str(vessel.get(k,"")).strip().lower() and str(vessel.get(k,"")).strip().lower() == str(row.get(k,"")).strip().lower() for k in ("imo","mmsi","name")):
            source = row.get("source","").lower()
            if source == "sanctions": matches.append(_rules("sanctions_match",8,"Matched sanctions watchlist entry"))
            if source == "shadow_fleet": matches.append(_rules("shadow_fleet_match",5,"Matched shadow-fleet watchlist entry"))
    return matches


def _history_rules(vessel: dict, history: list[dict], nearest: dict, sar: list[dict]) -> list[dict]:
    """Apply only rules backed by stored earlier positions; empty history fires none."""
    if not history:
        return []
    now, prior = _time(vessel["timestamp"]), sorted(history, key=lambda item:_time(item["timestamp"]))
    rules, all_points = [], prior + [vessel]
    gaps = [(_time(b["timestamp"])-_time(a["timestamp"])).total_seconds()/3600 for a,b in zip(all_points,all_points[1:])]
    gap = max(gaps, default=0)
    if gap > 18: rules.append(_rules("ais_gap_18h",4,f"AIS reporting gap of {gap:.1f} hours"))
    elif gap > 6: rules.append(_rules("ais_gap_6h",2,f"AIS reporting gap of {gap:.1f} hours"))
    near = nearest["distance_km"] is not None and nearest["distance_km"] <= 10
    slow = [p for p in all_points if float(p.get("speed",0)) < 6]
    if near and slow:
        span = (_time(slow[-1]["timestamp"])-_time(slow[0]["timestamp"])).total_seconds()/3600
        if span > 6: rules.append(_rules("low_speed_near_infra_6h",4,f"Speed below 6 kn near schematic infrastructure for {span:.1f} hours"))
        elif span > 2: rules.append(_rules("low_speed_near_infra_2h",2,f"Speed below 6 kn near schematic infrastructure for {span:.1f} hours"))
    changes = [abs(((float(b.get("course",0))-float(a.get("course",0))+180)%360)-180) for a,b in zip(all_points,all_points[1:])]
    if sum(change >= 60 for change in changes) >= 3: rules.append(_rules("zigzag_or_anchor_drag_proxy",2,"Repeated large course changes in stored AIS positions"))
    identity_fields = ("name","mmsi","imo","callsign","flag")
    if any(str(p.get(field) or "") != str(vessel.get(field) or "") for p in prior for field in identity_fields): rules.append(_rules("identity_change",3,"Identity field changed compared with stored AIS position"))
    sensitive = _sensitive_bboxes()
    visits = sum(any(point_in_bbox(p["lat"],p["lon"],*box) for box in sensitive) for p in all_points)
    if visits >= 3: rules.append(_rules("repeat_sensitive_area_presence",2,"Repeated stored presence inside a sensitive-area bounding box"))
    if gap > 6:
        for detection in sar:
            if not detection.get("matched") and abs((_time(detection["timestamp"])-now).total_seconds()) <= 12*3600 and haversine_km(vessel["lat"],vessel["lon"],detection["lat"],detection["lon"]) <= 10:
                rules.append(_rules("sar_unmatched_near_ais_gap",5,"Unmatched SAR lead is spatially and temporally close to an AIS gap")); break
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
    item, kind = dict(vessel), vessel.get("ship_type","unknown")
    if kind in {"naval","law_enforcement"}:
        item.update({"risk_score":0,"risk_level":"Normal","triggered_rules":[],"nearest_infrastructure":nearest_infrastructure(vessel,features)})
        return item
    nearest = nearest_infrastructure(vessel,features); rules = []
    distance = nearest["distance_km"]
    if distance is not None:
        if distance <= 1: rules.append(_rules("infra_proximity_1km",3,f"{distance:.1f} km from {nearest['type']} {nearest['name']}"))
        elif distance <= 5: rules.append(_rules("infra_proximity_5km",2,f"{distance:.1f} km from {nearest['type']} {nearest['name']}"))
        elif distance <= 10: rules.append(_rules("infra_proximity_10km",1,f"{distance:.1f} km from {nearest['type']} {nearest['name']}"))
    rules.extend(_history_rules(vessel,history or [],nearest,sar or []))
    rules.extend(_match_watchlist(vessel,watchlist if watchlist is not None else _watchlist()))
    if vessel.get("suspected_sts_rendezvous"): rules.append(_rules("sts_rendezvous",4,"Suspected ship-to-ship rendezvous lead supplied by upstream analysis"))
    raw = sum(rule["points"] for rule in rules)
    score = round(raw * MULTIPLIERS.get(kind,0.6))
    level = next(level for threshold,level in LEVELS if score >= threshold)
    item.update({"risk_score":score,"risk_level":level,"triggered_rules":rules,"nearest_infrastructure":nearest})
    return item


def update_history(vessels: list[dict], path: Path = HISTORY_PATH, now: datetime | None = None) -> dict[str,list[dict]]:
    """Append source positions and retain only the previous 14 days."""
    now = now or datetime.now(timezone.utc); cutoff = now-timedelta(days=14); retained=[]
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record=json.loads(line)
                if _time(record["timestamp"]) >= cutoff: retained.append(record)
            except (ValueError,json.JSONDecodeError,KeyError): pass
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8") as handle:
        for record in retained+vessels: handle.write(json.dumps(record)+"\n")
    grouped={}
    for record in retained: grouped.setdefault(str(record.get("mmsi")),[]).append(record)
    return grouped
