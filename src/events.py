"""Append-only research-lead event ledger and static exports."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import DOCS_DATA, ROOT

HEADER = ["event_id","date","time","region","lat","lon","vessel_name","mmsi","imo","ship_type","event_type","risk_score","triggered_rules","nearest_infrastructure","distance_km","sources","confidence","notes"]
ALLOWED_EVENT_TYPES = {"cable_proximity","pipeline_proximity","loitering","ais_gap","identity_change","sar_unmatched","sts_rendezvous","sanctions_match","shadow_fleet_match","sensitive_area_repeat_presence","news_matched_incident"}
CSV_PATH = ROOT / "data" / "events" / "events.csv"
EXPORT_PATH = DOCS_DATA / "events.json"
STATIC_CSV = DOCS_DATA / "events.csv"
RULE_EVENT = {
    "low_speed_near_infra_2h":"loitering",
    "low_speed_near_infra_6h":"loitering",
    "ais_gap_6h":"ais_gap",
    "ais_gap_18h":"ais_gap",
    "identity_change":"identity_change",
    "sts_rendezvous":"sts_rendezvous",
    "sanctions_match":"sanctions_match",
    "shadow_fleet_match":"shadow_fleet_match",
    "repeat_sensitive_area_presence":"sensitive_area_repeat_presence",
    "sar_unmatched_near_ais_gap":"sar_unmatched",
}
PRIORITY_LEVELS = {"Watch", "High Review Priority", "Critical Review Priority"}
STANDALONE_EVENT_TYPES = {"identity_change", "sanctions_match"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event_time(value) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return _now()


def _ensure(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(HEADER)


def _rows() -> list[dict]:
    _ensure(CSV_PATH)
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _region(lat: float, lon: float) -> str:
    try:
        with (ROOT / "data" / "reference" / "sensitive_areas.csv").open(newline="", encoding="utf-8") as handle:
            for area in csv.DictReader(handle):
                if float(area["lat_min"]) <= lat <= float(area["lat_max"]) and float(area["lon_min"]) <= lon <= float(area["lon_max"]):
                    return area["name"]
    except (OSError, KeyError, ValueError):
        pass
    return "Other High North" if lat >= 64 else "Other Baltic"


def _indicator_sources(vessel: dict, rules: list[dict]) -> set[str]:
    sources = {str(vessel.get("source") or "unknown")}
    ids = {rule.get("rule_id") for rule in rules}
    if ids & {"sanctions_match", "shadow_fleet_match"}:
        sources.add("watchlist")
    if "sar_unmatched_near_ais_gap" in ids:
        sources.add("gfw_sar")
    return sources


def _confidence(vessel: dict, rules: list[dict], sources: set[str]) -> str:
    if not vessel.get("mmsi") or not vessel.get("name"):
        return "low"
    return "medium" if len(sources) > 1 and len(rules) > 1 else "low"


def _event_types(vessel: dict, rules: list[dict]) -> list[str]:
    ids = {rule.get("rule_id") for rule in rules}
    result = []
    if any(str(rule_id).startswith("infra_proximity") for rule_id in ids):
        result.append("pipeline_proximity" if vessel.get("nearest_infrastructure",{}).get("type") == "pipeline" else "cable_proximity")
    for rule_id, event_type in RULE_EVENT.items():
        if rule_id in ids and event_type not in result:
            result.append(event_type)
    return result


def _daily_id(rows: list[dict], day: str) -> str:
    prefix = "NBGM-" + day.replace("-", "")
    numbers = [int(row["event_id"].split("-")[-1]) for row in rows if row.get("event_id", "").startswith(prefix) and row["event_id"].split("-")[-1].isdigit()]
    return f"{prefix}-{max(numbers, default=0)+1:04d}"


def _write(row: dict) -> None:
    _ensure(CSV_PATH)
    with CSV_PATH.open("a", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=HEADER).writerow(row)


def _row_time(row: dict) -> datetime:
    return _event_time(str(row.get("date", "")) + "T" + str(row.get("time", "")))


def _same_entity(old: dict, entity: dict | str) -> bool:
    if isinstance(entity, str) and entity.startswith("sar:"):
        return f"detection_id={entity.removeprefix('sar:')}" in str(old.get("notes", ""))
    if not isinstance(entity, dict):
        return False
    stable_pairs = (
        (str(old.get("imo") or "").strip(), str(entity.get("imo") or "").strip()),
        (str(old.get("mmsi") or "").strip(), str(entity.get("mmsi") or "").strip()),
    )
    if any(left and right and left == right for left, right in stable_pairs):
        return True
    if any(left or right for left, right in stable_pairs):
        return False
    old_name = " ".join(str(old.get("vessel_name") or "").split()).casefold()
    new_name = " ".join(str(entity.get("name") or "").split()).casefold()
    if old_name and new_name:
        return old_name == new_name
    return False


def _append_or_revision(row: dict, rows: list[dict], entity: dict | str) -> dict | None:
    event_time = _row_time(row)
    for old in reversed(rows):
        if old.get("event_type") != row["event_type"] or not _same_entity(old, entity):
            continue
        if abs(event_time - _row_time(old)) <= timedelta(hours=24):
            if float(row["risk_score"]) > float(old.get("risk_score") or 0):
                row["event_id"] = old["event_id"]
                row["notes"] = "Risk-score revision of existing research lead. " + row["notes"]
                _write(row)
                return row
            return None
    row["event_id"] = _daily_id(rows, row["date"])
    _write(row)
    return row


def record_events(vessels: list[dict], sar_detections: list[dict]) -> dict:
    """Append eligible vessel and standalone SAR leads without inventing event types."""
    rows = _rows()
    for vessel in vessels:
        rules = vessel.get("triggered_rules") if isinstance(vessel.get("triggered_rules"), list) else []
        event_types = _event_types(vessel, rules)
        if vessel.get("risk_level") not in PRIORITY_LEVELS:
            event_types = [event_type for event_type in event_types if event_type in STANDALONE_EVENT_TYPES]
        if not event_types:
            continue
        event_time = _event_time(vessel.get("timestamp"))
        nearest = vessel.get("nearest_infrastructure") if isinstance(vessel.get("nearest_infrastructure"), dict) else {}
        sources = _indicator_sources(vessel, rules)
        entity = {"mmsi":vessel.get("mmsi"), "imo":vessel.get("imo"), "name":vessel.get("name")}
        for event_type in event_types:
            row = {
                "event_id":"",
                "date":event_time.date().isoformat(),
                "time":event_time.timetz().replace(microsecond=0).isoformat(),
                "region":_region(float(vessel["lat"]),float(vessel["lon"])),
                "lat":vessel["lat"],"lon":vessel["lon"],
                "vessel_name":vessel.get("name") or "Unknown",
                "mmsi":vessel.get("mmsi") or "","imo":vessel.get("imo") or "",
                "ship_type":vessel.get("ship_type") or "unknown",
                "event_type":event_type,
                "risk_score":vessel.get("risk_score",0),
                "triggered_rules":json.dumps(rules,ensure_ascii=False),
                "nearest_infrastructure":nearest.get("name", ""),
                "distance_km":nearest.get("distance_km", ""),
                "sources":",".join(sorted(sources)),
                "confidence":_confidence(vessel,rules,sources),
                "notes":"Automated research lead for human review; not a confirmed incident.",
            }
            if event_type not in ALLOWED_EVENT_TYPES:
                continue
            written = _append_or_revision(row, rows, entity)
            if written is not None:
                rows.append(written)

    for detection in sar_detections:
        if detection.get("matched"):
            continue
        detection_id = str(detection.get("detection_id") or "unknown")
        event_time = _event_time(detection.get("timestamp"))
        row = {
            "event_id":"","date":event_time.date().isoformat(),"time":event_time.timetz().replace(microsecond=0).isoformat(),
            "region":_region(float(detection["lat"]),float(detection["lon"])),
            "lat":detection["lat"],"lon":detection["lon"],"vessel_name":"","mmsi":"","imo":"","ship_type":"unknown",
            "event_type":"sar_unmatched","risk_score":0,"triggered_rules":"[]","nearest_infrastructure":"","distance_km":"",
            "sources":detection.get("source", ""),"confidence":"low",
            "notes":f"Unmatched SAR research lead; detection_id={detection_id}; not confirmation of illicit activity.",
        }
        written = _append_or_revision(row, rows, "sar:" + detection_id)
        if written is not None:
            rows.append(written)
    return export_events()


def export_events() -> dict:
    """Export the latest append-only revision per event ID for the static frontend."""
    latest = {}
    for row in _rows():
        if row.get("event_id"):
            latest[row["event_id"]] = row
    events = sorted(latest.values(), key=lambda row:(row.get("date", ""),row.get("time", "")), reverse=True)
    payload = {"metadata":{"generated_at":_now().isoformat(),"disclaimer":"This table is a research lead database, not a record of confirmed incidents."},"events":events}
    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    with STATIC_CSV.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=HEADER); writer.writeheader(); writer.writerows(events)
    return payload
