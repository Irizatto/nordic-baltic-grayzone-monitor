"""Merge AIS sources into the static dashboard while preserving safe fallback behaviour."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import DOCS_DATA, PROCESSED_DATA, USE_MOCK_DATA
from fetch_barentswatch_ais import fetch_barentswatch_ais, write_latest as write_barentswatch
from fetch_digitraffic_ais import fetch_digitraffic_ais, write_latest as write_digitraffic
from fetch_gfw_data import fetch_gfw_sar, write_latest as write_gfw_sar
from analyze_suspicious import score_vessel, update_history
from events import record_events


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _decorate_for_dashboard(record: dict) -> dict:
    """Add neutral display fields after source conversion; source records stay unified."""
    item = dict(record)
    item.update({"risk_score":0,"risk_level":"Low","triggered_rules":[],"nearest_infrastructure":{"name":"Not calculated","type":"not available","distance_km":None}})
    return item


def _merge_newest(records: list[dict]) -> list[dict]:
    newest = {}
    for record in records:
        key = str(record.get("mmsi", ""))
        if key and (key not in newest or str(record.get("timestamp","")) > str(newest[key].get("timestamp",""))):
            newest[key] = record
    return list(newest.values())


def run() -> dict:
    """Fetch available sources and write a refreshed derived dashboard artifact."""
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    previous = _read(DOCS_DATA / "data.json", {"vessels":[],"sar_detections":[]})
    source_status = {}
    real_records = []

    if USE_MOCK_DATA:
        source_status["digitraffic"] = {"status":"credentials_missing_fallback_mock","timestamp":_now(),"detail":"USE_MOCK_DATA is enabled"}
    else:
        try:
            digitraffic = fetch_digitraffic_ais()
            write_digitraffic(digitraffic)
            real_records.extend(digitraffic)
            source_status["digitraffic"] = {"status":"ok","timestamp":_now(),"records_fetched":len(digitraffic)}
        except requests.RequestException as error:
            source_status["digitraffic"] = {"status":"error_kept_old_data","timestamp":_now(),"detail":str(error)}

    try:
        barentswatch = None if USE_MOCK_DATA else fetch_barentswatch_ais()
        if barentswatch is None:
            source_status["barentswatch"] = {"status":"credentials_missing_fallback_mock","timestamp":_now(),"detail":"BARENTSWATCH_CLIENT_ID / BARENTSWATCH_CLIENT_SECRET unavailable or mock mode enabled"}
        else:
            write_barentswatch(barentswatch)
            real_records.extend(barentswatch)
            source_status["barentswatch"] = {"status":"ok","timestamp":_now(),"records_fetched":len(barentswatch)}
    except requests.RequestException as error:
        source_status["barentswatch"] = {"status":"error_kept_old_data","timestamp":_now(),"detail":str(error)}

    sar_detections, gfw_status, gfw_detail = fetch_gfw_sar()
    if gfw_status == "ok":
        write_gfw_sar(sar_detections)
    source_status["gfw_sar"] = {"status":gfw_status,"timestamp":_now(),"records_fetched":len(sar_detections),"records_published":len(sar_detections),"detail":gfw_detail}

    mock_vessels = [v for v in previous.get("vessels", []) if v.get("source") == "mock"]
    vessels = _merge_newest([_decorate_for_dashboard(v) for v in real_records] + mock_vessels)
    history_by_mmsi = update_history(vessels)
    vessels = [score_vessel(vessel, history_by_mmsi.get(str(vessel.get("mmsi")), []), sar_detections) for vessel in vessels]
    record_events(vessels, sar_detections)
    records_fetched = list(vessels)
    priority = [vessel for vessel in vessels if vessel.get("risk_level") in {"Watch", "High Review Priority", "Critical Review Priority"}]
    remainder = sorted((vessel for vessel in vessels if vessel not in priority), key=lambda vessel: vessel.get("risk_score", 0), reverse=True)
    vessels = priority + remainder[:max(0, 150 - len(priority))]
    for source in {vessel.get("source", "unknown") for vessel in records_fetched}:
        status = source_status.setdefault(source, {"status":"ok","timestamp":_now()})
        status["records_fetched"] = sum(vessel.get("source") == source for vessel in records_fetched)
        status["records_published"] = sum(vessel.get("source") == source for vessel in vessels)
    all_mock = not real_records
    metadata = {"generated_at":_now(),"mode":"mock" if all_mock else "mixed","sources":["mock"] + sorted({v["source"] for v in real_records}),"source_status":source_status,"fallbacks":["Mock vessels remain available when a live AIS source is missing, unavailable, or returns an error."]}

    output = {"metadata":metadata,"vessels":vessels,"sar_detections":sar_detections}
    (DOCS_DATA / "data.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    (DOCS_DATA / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    result = run()
    print("Dashboard records:", len(result["vessels"]))
