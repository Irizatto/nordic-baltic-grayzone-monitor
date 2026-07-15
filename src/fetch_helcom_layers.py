"""Fetch HELCOM Marine Protected Areas as a safe static GeoJSON snapshot.

HELCOM's Map and Data Service exposes this public layer through ArcGIS REST.
No credential is required. The adapter requests a simplified WGS84 GeoJSON
representation, validates and normalises it, then replaces the published file
atomically. Network or schema failures retain the last valid snapshot.
"""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from shapely.geometry import mapping, shape

from config import (
    DOCS_DATA,
    HELCOM_MPA_LAYER_URL,
    HELCOM_MPA_QUERY_URL,
    HELCOM_USER_AGENT,
    ROOT,
)

LAYER_PATH = DOCS_DATA / "layers" / "helcom_mpas.geojson"
METADATA_PATH = DOCS_DATA / "helcom_metadata.json"
RAW_ARCHIVE_DIR = ROOT / "data" / "raw" / "helcom"
REQUEST_PARAMS = {
    "where": "1=1",
    "outFields": (
        "OBJECTID,Name,MPA_ID,Country,Site_link,MPA_status,Date_est,Year_est"
    ),
    "returnGeometry": "true",
    "outSR": "4326",
    "geometryPrecision": "5",
    "maxAllowableOffset": "0.002",
    "f": "geojson",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def _valid_collection(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("type") == "FeatureCollection"
        and isinstance(payload.get("features"), list)
    )


def _existing() -> dict[str, Any]:
    payload = _read_json(LAYER_PATH, None)
    if _valid_collection(payload):
        return payload
    return {"type": "FeatureCollection", "features": []}


def _request_geojson(session: requests.Session) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.get(
                HELCOM_MPA_QUERY_URL,
                params=REQUEST_PARAMS,
                headers={
                    "User-Agent": HELCOM_USER_AGENT,
                    "Accept": "application/geo+json, application/json",
                },
                timeout=90,
            )
            response.raise_for_status()
            payload = response.json()
            if not _valid_collection(payload):
                raise ValueError("HELCOM response is not a GeoJSON FeatureCollection")
            return payload
        except (requests.RequestException, ValueError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(f"HELCOM request failed after 3 attempts: {last_error}")


def _normalise_feature(feature: dict[str, Any], retrieved: datetime) -> dict[str, Any] | None:
    geometry_payload = feature.get("geometry")
    if not isinstance(geometry_payload, dict):
        return None
    try:
        geometry = shape(geometry_payload)
    except (TypeError, ValueError):
        return None
    if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        return None
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        return None

    source = feature.get("properties") or {}
    name = str(source.get("Name") or "Unnamed HELCOM MPA").strip()
    year = source.get("Year_est")
    try:
        year = int(year) if year not in (None, "") else None
    except (TypeError, ValueError):
        year = None
    return {
        "type": "Feature",
        "properties": {
            "name": name,
            "category": "protected_area",
            "source": "helcom_mads",
            "source_url": HELCOM_MPA_LAYER_URL,
            "last_updated": retrieved.date().isoformat(),
            "notes": (
                "Public HELCOM Marine Protected Area boundary for environmental "
                "context; source coverage and precision vary. Not for navigation "
                "or confirmation. / HELCOM公开海洋保护区边界，仅作环境背景参考；"
                "覆盖范围和精度可能不同，不可用于导航或确认。"
            ),
            "route_precision": "published_open_data",
            "retrieved_at": retrieved.isoformat(),
            "source_feature_id": str(source.get("OBJECTID") or ""),
            "mpa_id": source.get("MPA_ID"),
            "country": source.get("Country"),
            "mpa_status": source.get("MPA_status"),
            "established_year": year,
            "site_url": source.get("Site_link"),
            "scoring_eligible": False,
        },
        "geometry": mapping(geometry),
    }


def _write_json_atomic(
    path: Path, payload: dict[str, Any], *, compact: bool = False
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if compact:
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        content = json.dumps(payload, indent=2, ensure_ascii=False)
    temporary.write_text(content + "\n", encoding="utf-8")
    temporary.replace(path)


def run(session: requests.Session | None = None) -> dict[str, Any]:
    """Refresh the HELCOM MPA snapshot and return source-status metadata."""
    retrieved = _now()
    previous = _existing()
    try:
        payload = _request_geojson(session or requests.Session())
        features = [
            normalised
            for feature in payload["features"]
            if (normalised := _normalise_feature(feature, retrieved)) is not None
        ]
        if not features:
            raise ValueError("HELCOM returned no valid MPA polygons")
        published = {"type": "FeatureCollection", "features": features}
        if LAYER_PATH.exists() and previous != published:
            archive = RAW_ARCHIVE_DIR / retrieved.strftime("%Y%m%dT%H%M%SZ")
            archive.mkdir(parents=True, exist_ok=True)
            shutil.copy2(LAYER_PATH, archive / LAYER_PATH.name)
        _write_json_atomic(LAYER_PATH, published, compact=True)
        metadata = {
            "generated_at": retrieved.isoformat(),
            "source": "helcom_mads",
            "source_url": HELCOM_MPA_LAYER_URL,
            "status": "ok",
            "records_fetched": len(payload["features"]),
            "records_published": len(features),
            "fallbacks": [],
            "detail": "HELCOM MADS Marine Protected Areas public GeoJSON snapshot.",
        }
    except Exception as error:  # retain a last-known-good static layer on any adapter error
        metadata = {
            "generated_at": retrieved.isoformat(),
            "source": "helcom_mads",
            "source_url": HELCOM_MPA_LAYER_URL,
            "status": "error_kept_old_data",
            "records_fetched": 0,
            "records_published": len(previous["features"]),
            "fallbacks": [f"HELCOM unavailable; previous snapshot retained: {type(error).__name__}: {error}"[:1000]],
            "detail": "HELCOM refresh unavailable; previous validated snapshot retained.",
        }
    _write_json_atomic(METADATA_PATH, metadata)
    return metadata


if __name__ == "__main__":
    result = run()
    print(
        "HELCOM MPA:",
        result["status"],
        f"{result['records_published']} published features",
    )
