"""Global Fishing Watch SAR detection adapter with approval-safe mock fallback."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from config import GFW_API_TOKEN, GFW_SAR_BBOXES, PROCESSED_DATA

GFW_REPORT_URL = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"


def mock_sar_detections() -> list[dict]:
    """Return clearly labelled fictional SAR leads for an operational frontend fallback."""
    now = datetime.now(timezone.utc)
    return [
        {"detection_id":"mock-sar-001","lat":59.80,"lon":24.45,"timestamp":now.isoformat(),"matched":True,"matched_mmsi":"255100001","confidence":0.82,"length_m":182.0,"source":"mock"},
        {"detection_id":"mock-sar-002","lat":55.20,"lon":15.90,"timestamp":(now-timedelta(hours=3)).isoformat(),"matched":False,"matched_mmsi":None,"confidence":0.61,"length_m":74.0,"source":"mock"},
        {"detection_id":"mock-sar-003","lat":72.50,"lon":29.90,"timestamp":(now-timedelta(hours=8)).isoformat(),"matched":False,"matched_mmsi":None,"confidence":0.48,"length_m":None,"source":"mock"},
    ]


def _convert(item: dict) -> dict | None:
    """Convert a GFW SAR response item to the project SAR schema."""
    position = item.get("position", item.get("coordinates", {}))
    if isinstance(position, list) and len(position) >= 2:
        lon, lat = position[0], position[1]
    else:
        lat, lon = item.get("lat", item.get("latitude")), item.get("lon", item.get("longitude"))
    try:
        return {"detection_id":str(item.get("id", item.get("detectionId"))),"lat":float(lat),"lon":float(lon),"timestamp":str(item.get("timestamp", item.get("date"))),"matched":bool(item.get("matched", item.get("matchedMmsi"))),"matched_mmsi":str(item["matchedMmsi"]) if item.get("matchedMmsi") else None,"confidence":float(item.get("confidence", 0)),"length_m":float(item["length"]) if item.get("length") is not None else None,"source":"gfw_sar"}
    except (TypeError, ValueError):
        return None


def fetch_gfw_sar() -> tuple[list[dict], str, str]:
    """Query the last seven days of SAR leads, or return mock data without raising."""
    if not GFW_API_TOKEN:
        return mock_sar_detections(), "credentials_missing_fallback_mock", "GFW_API_TOKEN is unavailable; SAR dataset approval may still be pending."
    end = datetime.now(timezone.utc)
    body = {"datasets":["public-global-sar"],"startDate":(end-timedelta(days=7)).date().isoformat(),"endDate":end.date().isoformat(),"regions":[{"type":"Feature","geometry":{"type":"MultiPolygon","coordinates":[[[[box["lon_min"],box["lat_min"]],[box["lon_max"],box["lat_min"]],[box["lon_max"],box["lat_max"]],[box["lon_min"],box["lat_max"]],[box["lon_min"],box["lat_min"]]]] for box in GFW_SAR_BBOXES]}}]}
    try:
        response = requests.post(GFW_REPORT_URL, json=body, headers={"Authorization":"Bearer "+GFW_API_TOKEN,"Accept":"application/json"}, timeout=60)
        if response.status_code in {401, 403}:
            return mock_sar_detections(), "credentials_missing_fallback_mock", "GFW SAR permission is unavailable; using mock review leads."
        response.raise_for_status()
        items = response.json().get("entries", response.json().get("data", []))
        return [record for item in items if (record := _convert(item))], "ok", "Live GFW SAR data"
    except requests.RequestException as error:
        return mock_sar_detections(), "error_kept_old_data", "GFW request unavailable; using mock review leads: "+str(error)


def write_latest(records: list[dict]) -> Path:
    """Write a dated processed SAR snapshot while preserving existing files."""
    PROCESSED_DATA.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DATA / ("sar_latest_gfw_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return path
