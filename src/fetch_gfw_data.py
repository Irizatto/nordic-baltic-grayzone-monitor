"""Global Fishing Watch SAR adapter with approval-safe mock fallback."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from ais_schema import finite_float, iso8601_timestamp, optional_string
from config import GFW_API_TOKEN, GFW_SAR_BBOXES, PROCESSED_DATA

GFW_REPORT_URL = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
GFW_LAST_REPORT_URL = "https://gateway.api.globalfishingwatch.org/v3/4wings/last-report"
GFW_SAR_DATASET = "public-global-sar-presence:latest"


class GFWPermissionUnavailable(Exception):
    """Raised when the token or SAR dataset approval is unavailable."""


def mock_sar_detections() -> list[dict]:
    """Return clearly labelled fictional SAR leads for an operational fallback."""
    now = datetime.now(timezone.utc)
    return [
        {"detection_id":"mock-sar-001","lat":59.80,"lon":24.45,"timestamp":now.isoformat(),"matched":True,"matched_mmsi":"255100001","confidence":0.82,"length_m":182.0,"source":"mock"},
        {"detection_id":"mock-sar-002","lat":55.20,"lon":15.90,"timestamp":(now-timedelta(hours=3)).isoformat(),"matched":False,"matched_mmsi":None,"confidence":0.61,"length_m":74.0,"source":"mock"},
        {"detection_id":"mock-sar-003","lat":72.50,"lon":29.90,"timestamp":(now-timedelta(hours=8)).isoformat(),"matched":False,"matched_mmsi":None,"confidence":0.48,"length_m":None,"source":"mock"},
    ]


def _geojson_region() -> dict:
    polygons = []
    for box in GFW_SAR_BBOXES:
        polygons.append([[box["lon_min"],box["lat_min"]],[box["lon_max"],box["lat_min"]],[box["lon_max"],box["lat_max"]],[box["lon_min"],box["lat_max"]],[box["lon_min"],box["lat_min"]]])
    return {"type":"MultiPolygon","coordinates":[[ring] for ring in polygons]}


def _poll_last_report(headers: dict) -> dict:
    """Recover a timed-out GFW report through the documented last-report endpoint."""
    for poll_attempt in range(4):
        poll = requests.get(GFW_LAST_REPORT_URL, headers=headers, timeout=60)
        if poll.status_code in {401, 403}:
            raise GFWPermissionUnavailable("GFW SAR permission is unavailable")
        poll.raise_for_status()
        payload = poll.json()
        if payload.get("status") == "running":
            time.sleep(2 ** poll_attempt)
            continue
        if isinstance(payload.get("status"), int) and payload["status"] >= 400:
            raise requests.HTTPError("GFW last report finished with an error")
        return payload
    raise requests.Timeout("GFW report was still running after bounded polling")


def _request_report(params: dict, body: dict) -> dict:
    """Request one report with bounded retry and documented timeout recovery."""
    headers = {"Authorization":"Bearer "+str(GFW_API_TOKEN),"Accept":"application/json","Content-Type":"application/json"}
    for attempt in range(3):
        try:
            response = requests.post(GFW_REPORT_URL, params=params, json=body, headers=headers, timeout=60)
            if response.status_code in {401, 403}:
                raise GFWPermissionUnavailable("GFW SAR permission is unavailable")
            if response.status_code == 429:
                return _poll_last_report(headers)
            if response.status_code == 524:
                return _poll_last_report(headers)
            response.raise_for_status()
            payload = response.json()
            return _poll_last_report(headers) if payload.get("status") == "running" else payload
        except GFWPermissionUnavailable:
            raise
        except requests.Timeout:
            try:
                return _poll_last_report(headers)
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def _flatten_entries(payload: dict) -> list[dict]:
    flattened = []
    for entry in payload.get("entries", []):
        if isinstance(entry, dict):
            for values in entry.values():
                if isinstance(values, list):
                    flattened.extend(value for value in values if isinstance(value, dict))
        elif isinstance(entry, list):
            flattened.extend(value for value in entry if isinstance(value, dict))
    return flattened


def _convert(item: dict, matched: bool | None = None, ordinal: int = 0) -> dict | None:
    """Convert a GFW report cell or vessel entry to the project SAR schema."""
    position = item.get("position", item.get("coordinates", {}))
    if isinstance(position, list) and len(position) >= 2:
        lon, lat = position[0], position[1]
    else:
        lat, lon = item.get("lat", item.get("latitude")), item.get("lon", item.get("longitude"))
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    timestamp = iso8601_timestamp(item.get("entryTimestamp", item.get("timestamp", item.get("date"))))
    mmsi = optional_string(item.get("mmsi", item.get("matchedMmsi")))
    is_matched = bool(matched if matched is not None else item.get("matched", mmsi))
    identity = optional_string(item.get("detectionId", item.get("id")))
    if not identity:
        vessel_id = optional_string(item.get("vesselId")) or ""
        seed = f"{lat:.5f}|{lon:.5f}|{timestamp}|{is_matched}|{vessel_id}|{ordinal}"
        identity = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    elif ordinal:
        identity = f"{identity}-{ordinal}"
    length = item.get("length", item.get("length_m"))
    return {
        "detection_id": identity,
        "lat": lat,
        "lon": lon,
        "timestamp": timestamp,
        "matched": is_matched,
        "matched_mmsi": mmsi if is_matched else None,
        "confidence": finite_float(item.get("confidence")),
        "length_m": finite_float(length) if length is not None else None,
        "source": "gfw_sar",
    }


def _records_from_payload(payload: dict, matched: bool) -> list[dict]:
    """Expand aggregated grid-cell counts into schema records at the reported cell centre."""
    records = []
    for item in _flatten_entries(payload):
        try:
            count = max(0, int(float(item.get("detections", 1))))
        except (TypeError, ValueError):
            count = 1
        for ordinal in range(count):
            record = _convert(item, matched, ordinal)
            if record:
                records.append(record)
    return records


def fetch_gfw_sar() -> tuple[list[dict], str, str]:
    """Query seven days of matched/unmatched SAR report cells, or safely use mock leads."""
    if not GFW_API_TOKEN:
        return mock_sar_detections(), "credentials_missing_fallback_mock", "GFW_API_TOKEN is unavailable; SAR dataset approval may still be pending."
    end = datetime.now(timezone.utc)
    common = {
        "spatial-resolution":"HIGH",
        "temporal-resolution":"HOURLY",
        "datasets[0]":GFW_SAR_DATASET,
        "date-range":f"{(end-timedelta(days=7)).date().isoformat()},{end.date().isoformat()}",
        "format":"JSON",
    }
    body = {"geojson":_geojson_region()}
    try:
        unmatched_payload = _request_report({**common,"filters[0]":"matched='false'"}, body)
        matched_payload = _request_report({**common,"filters[0]":"matched='true'","group-by":"VESSEL_ID"}, body)
        records = _records_from_payload(unmatched_payload, False)
        records.extend(_records_from_payload(matched_payload, True))
        unique = {record["detection_id"]:record for record in records}
        return list(unique.values()), "ok", "Live GFW SAR report cells; coordinates are grid-cell centres, not precise individual positions; leads require human review."
    except GFWPermissionUnavailable:
        return mock_sar_detections(), "credentials_missing_fallback_mock", "GFW SAR permission is unavailable; using mock review leads."
    except (requests.RequestException, ValueError, KeyError) as error:
        return mock_sar_detections(), "error_kept_old_data", "GFW request unavailable; previous published SAR should be retained: "+str(error)


def write_latest(records: list[dict]) -> Path:
    """Write a dated processed SAR snapshot while preserving existing files."""
    PROCESSED_DATA.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DATA / ("sar_latest_gfw_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return path
