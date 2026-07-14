"""Fintraffic Digitraffic Marine AIS client with a unified, mock-safe schema."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from config import DIGITRAFFIC_BASE_URL, DIGITRAFFIC_BBOX, DIGITRAFFIC_USER_AGENT, PROCESSED_DATA
from ais_schema import finite_float, in_bbox, iso8601_timestamp, map_ship_type, optional_string

HEADERS = {"Digitraffic-User": DIGITRAFFIC_USER_AGENT, "User-Agent": DIGITRAFFIC_USER_AGENT, "Accept": "application/json"}


def _get(path: str, params: dict | None = None) -> Any:
    """Request JSON with three bounded retries; raises only after all retries fail."""
    for attempt in range(3):
        try:
            response = requests.get(DIGITRAFFIC_BASE_URL + path, headers=HEADERS, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def _items(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("features") or payload.get("items") or payload.get("data") or payload.get("vessels") or []
    return []


def _value(item: dict, *names: str) -> Any:
    properties = item.get("properties", {}) if isinstance(item, dict) else {}
    for name in names:
        if name in item and item[name] is not None:
            return item[name]
        if name in properties and properties[name] is not None:
            return properties[name]
    return None


def _in_bbox(lat: float, lon: float) -> bool:
    return in_bbox(lat, lon, DIGITRAFFIC_BBOX)


def _position(item: dict) -> tuple[float | None, float | None]:
    geometry = item.get("geometry", {}) if isinstance(item, dict) else {}
    coordinates = geometry.get("coordinates", []) if isinstance(geometry, dict) else []
    lon = _value(item, "longitude", "lon")
    lat = _value(item, "latitude", "lat")
    if len(coordinates) >= 2:
        lon, lat = coordinates[0], coordinates[1]
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def fetch_digitraffic_ais() -> list[dict]:
    """Fetch latest locations and metadata, join by MMSI, and return the unified schema."""
    bbox_params = {"latitude": 60.0, "longitude": 24.0, "radius": 500.0}
    locations = _items(_get("/locations", bbox_params))
    metadata_by_mmsi = {str(_value(item, "mmsi", "MMSI")): item for item in _items(_get("/vessels")) if _value(item, "mmsi", "MMSI")}
    records = []
    for item in locations:
        lat, lon = _position(item)
        mmsi = optional_string(_value(item, "mmsi", "MMSI"))
        if not mmsi or lat is None or not _in_bbox(lat, lon):
            continue
        meta = metadata_by_mmsi.get(mmsi, {})
        raw_time = _value(item, "timestampExternal", "lastUpdated", "time", "timestamp")
        timestamp = iso8601_timestamp(raw_time)
        records.append({
            "mmsi": mmsi,
            "imo": optional_string(_value(meta, "imo", "imoNumber")),
            "name": optional_string(_value(meta, "name", "vesselName")),
            "callsign": optional_string(_value(meta, "callsign", "callSign")),
            "flag": optional_string(_value(meta, "flag", "country")),
            "ship_type": map_ship_type(_value(meta, "shipType", "shipTypeCode", "type")),
            "lat": lat,
            "lon": lon,
            "speed": finite_float(_value(item, "sog", "speed")),
            "course": finite_float(_value(item, "cog", "course")),
            "heading": finite_float(_value(item, "heading")),
            "timestamp": timestamp,
            "source": "digitraffic",
        })
    return records


def write_latest(records: list[dict]) -> Path:
    """Write the first latest snapshot; preserve older snapshots with dated names."""
    PROCESSED_DATA.mkdir(parents=True, exist_ok=True)
    base = PROCESSED_DATA / "ais_latest_digitraffic.json"
    path = base if not base.exists() else PROCESSED_DATA / ("ais_latest_digitraffic_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    try:
        output = write_latest(fetch_digitraffic_ais())
        print(output)
    except requests.RequestException as error:
        print("Digitraffic fetch failed; existing data preserved:", error)
