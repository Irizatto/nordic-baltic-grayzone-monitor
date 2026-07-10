"""Append-only research-lead event ledger and static export."""
from __future__ import annotations
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import DOCS_DATA, ROOT

HEADER=["event_id","date","time","region","lat","lon","vessel_name","mmsi","imo","ship_type","event_type","risk_score","triggered_rules","nearest_infrastructure","distance_km","sources","confidence","notes"]
CSV_PATH=ROOT/"data"/"events"/"events.csv"
EXPORT_PATH=DOCS_DATA/"events.json"
STATIC_CSV=DOCS_DATA/"events.csv"
RULE_EVENT={"low_speed_near_infra_2h":"loitering","low_speed_near_infra_6h":"loitering","ais_gap_6h":"ais_gap","ais_gap_18h":"ais_gap","identity_change":"identity_change","sts_rendezvous":"sts_rendezvous","sanctions_match":"sanctions_match","shadow_fleet_match":"shadow_fleet_match","repeat_sensitive_area_presence":"sensitive_area_repeat_presence","sar_unmatched_near_ais_gap":"sar_unmatched"}

def _now(): return datetime.now(timezone.utc)

def _ensure(path: Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        with path.open("w",newline="",encoding="utf-8") as handle: csv.writer(handle).writerow(HEADER)

def _rows():
    _ensure(CSV_PATH)
    with CSV_PATH.open(newline="",encoding="utf-8") as handle: return list(csv.DictReader(handle))

def _region(lat,lon):
    with (ROOT/"data"/"reference"/"sensitive_areas.csv").open(newline="",encoding="utf-8") as handle:
        for area in csv.DictReader(handle):
            if float(area["lat_min"]) <= lat <= float(area["lat_max"]) and float(area["lon_min"]) <= lon <= float(area["lon_max"]): return area["name"]
    return "Other High North" if lat >= 64 else "Other Baltic"

def _confidence(vessel, rules):
    if not vessel.get("mmsi") or not vessel.get("name"): return "low"
    return "medium" if len(rules) > 1 else "low"

def _event_type(vessel, rules):
    ids={rule["rule_id"] for rule in rules}
    if any(rule.startswith("infra_proximity") for rule in ids):
        return "pipeline_proximity" if vessel.get("nearest_infrastructure",{}).get("type")=="pipeline" else "cable_proximity"
    for rule_id,event_type in RULE_EVENT.items():
        if rule_id in ids: return event_type
    return None

def _daily_id(rows, date):
    prefix="NBGM-"+date.replace("-","")
    numbers=[int(row["event_id"].split("-")[-1]) for row in rows if row["event_id"].startswith(prefix) and row["event_id"].split("-")[-1].isdigit()]
    return f"{prefix}-{max(numbers,default=0)+1:04d}"

def _write(row):
    _ensure(CSV_PATH)
    with CSV_PATH.open("a",newline="",encoding="utf-8") as handle: csv.DictWriter(handle,fieldnames=HEADER).writerow(row)

def _append_or_revision(row, rows):
    now=_now()
    for old in reversed(rows):
        if old["mmsi"]==row["mmsi"] and old["event_type"]==row["event_type"]:
            then=datetime.fromisoformat(old["date"]+"T"+old["time"].replace("Z","+00:00"))
            if now-then <= timedelta(hours=24):
                if float(row["risk_score"]) > float(old["risk_score"]):
                    row["event_id"]=old["event_id"]; row["notes"]="Risk-score revision of existing research lead. "+row["notes"]; _write(row)
                return
    row["event_id"]=_daily_id(rows,now.date().isoformat()); _write(row)

def record_events(vessels, sar_detections):
    """Append Watch+ vessel leads and standalone SAR leads; retain every revision."""
    rows=_rows(); now=_now()
    for vessel in vessels:
        rules=vessel.get("triggered_rules",[]); event_type=_event_type(vessel,rules)
        if vessel.get("risk_level") not in {"Watch","High Review Priority","Critical Review Priority"} and not event_type: continue
        if not event_type: event_type="sensitive_area_repeat_presence"
        nearest=vessel.get("nearest_infrastructure",{})
        row={"event_id":"","date":now.date().isoformat(),"time":now.time().replace(microsecond=0).isoformat(),"region":_region(float(vessel["lat"]),float(vessel["lon"])),"lat":vessel["lat"],"lon":vessel["lon"],"vessel_name":vessel.get("name") or "Unknown","mmsi":vessel.get("mmsi") or "","imo":vessel.get("imo") or "","ship_type":vessel.get("ship_type") or "unknown","event_type":event_type,"risk_score":vessel.get("risk_score",0),"triggered_rules":json.dumps(rules,ensure_ascii=False),"nearest_infrastructure":nearest.get("name",""),"distance_km":nearest.get("distance_km",""),"sources":vessel.get("source",""),"confidence":_confidence(vessel,rules),"notes":"Automated research lead for human review; not a confirmed incident."}
        _append_or_revision(row,rows); rows.append(row)
    for detection in sar_detections:
        if detection.get("matched"): continue
        row={"event_id":"","date":now.date().isoformat(),"time":now.time().replace(microsecond=0).isoformat(),"region":_region(float(detection["lat"]),float(detection["lon"])),"lat":detection["lat"],"lon":detection["lon"],"vessel_name":"","mmsi":"","imo":"","ship_type":"unknown","event_type":"sar_unmatched","risk_score":0,"triggered_rules":"[]","nearest_infrastructure":"","distance_km":"","sources":detection.get("source",""),"confidence":"low","notes":"Unmatched SAR research lead; not confirmation of illicit activity."}
        _append_or_revision(row,rows); rows.append(row)
    return export_events()

def export_events():
    """Export the latest revision per event ID for the static frontend."""
    latest={}
    for row in _rows(): latest[row["event_id"]]=row
    events=sorted(latest.values(),key=lambda row:(row["date"],row["time"]),reverse=True)
    payload={"metadata":{"generated_at":_now().isoformat(),"disclaimer":"This table is a research lead database, not a record of confirmed incidents."},"events":events}
    EXPORT_PATH.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    with STATIC_CSV.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=HEADER); writer.writeheader(); writer.writerows(events)
    return payload
