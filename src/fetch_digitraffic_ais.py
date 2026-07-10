"""Fintraffic Digitraffic Marine AIS client with a unified, mock-safe schema."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from config import DIGITRAFFIC_BASE_URL, DIGITRAFFIC_BBOX, DIGITRAFFIC_USER_AGENT, PROCESSED_DATA

HEADERS = {"Digitraffic-User": DIGITRAFFIC_USER_AGENT, "User-Agent": DIGITRAFFIC_USER_AGENT, "Accept": "application/json"}
VALID_TYPES = {"cargo", "tanker", "fishing", "research", "tug", "service", "naval", "law_enforcement", "unknown"}


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


def map_ship_type(raw: Any) -> str:
    """Map AIS type numbers (including Digitraffic values) to the unified enum."""
    try:
        code = int(raw)
    except (TypeError, ValueError):
        return "unknown"
    if 70 <= code <= 79:
        return "cargo"
    if 80 <= code <= 89:
        return "tanker"
    if code == 30:
        return "fishing"
    if code in {31, 32}:
        return "tug"
    if code in {33, 34, 35}:
        return "service"
    if code == 36:
        return "naval"
    if code == 55:
        return "law_enforcement"
    if code in {37, 57, 97}:
        return "research"
    return "unknown"


def _in_bbox(lat: float, lon: float) -> bool:
    return DIGITRAFFIC_BBOX["lat_min"] <= lat <= DIGITRAFFIC_BBOX["lat_max"] and DIGITRAFFIC_BBOX["lon_min"] <= lon <= DIGITRAFFIC_BBOX["lon_max"]


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
        mmsi = _value(item, "mmsi", "MMSI")
        if not mmsi or lat is None or not _in_bbox(lat, lon):
            continue
        meta = metadata_by_mmsi.get(str(mmsi), {})
        raw_time = _value(item, "timestampExternal", "lastUpdated", "time", "timestamp")\n        timestamp = datetime.fromtimestamp(float(raw_time) / 1000, timezone.utc).isoformat() if str(raw_time).isdigit() and float(raw_time) > 10_000_000_000 else datetime.now(timezone.utc).isoformat()
        records.append({"mmsi":str(mmsi),"imo":_value(meta,"imo","imoNumber"),"name":_value(meta,"name","vesselName"),"callsign":_value(meta,"callsign","callSign"),"flag":_value(meta,"flag","country"),"ship_type":map_ship_type(_value(meta,"shipType","shipTypeCode","type")),"lat":lat,"lon":lon,"speed":float(_value(item,"sog","speed") or 0),"course":float(_value(item,"cog","course") or 0),"heading":float(_value(item,"heading") or 0),"timestamp":str(timestamp),"source":"digitraffic"})
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
