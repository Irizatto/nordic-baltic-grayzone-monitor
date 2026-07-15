"""Fetch public EMODnet Human Activities infrastructure as safe GeoJSON snapshots.

The browser never calls EMODnet directly. This adapter downloads bounded WFS
subsets, converts them to the dashboard schema, and atomically replaces only a
validated published snapshot. If EMODnet is unavailable, the existing files are
left untouched so the dashboard continues with its last real or schematic data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from shapely.geometry import mapping, shape

from config import (
    DOCS_DATA,
    EMODNET_BBOXES,
    EMODNET_MAX_FEATURES_PER_SOURCE,
    EMODNET_PAGE_SIZE,
    EMODNET_SIMPLIFY_TOLERANCE_DEGREES,
    EMODNET_USER_AGENT,
    EMODNET_WFS_URL,
    ROOT,
    USE_MOCK_DATA,
)

LAYERS_DIR = DOCS_DATA / "layers"
INFRASTRUCTURE_METADATA_PATH = DOCS_DATA / "infrastructure_metadata.json"
RAW_ARCHIVE_DIR = ROOT / "data" / "raw" / "emodnet"
EMODNET_CAPABILITIES_URL = (
    EMODNET_WFS_URL + "?SERVICE=WFS&REQUEST=GetCapabilities&VERSION=2.0.0"
)

LAYER_SPECS: dict[str, tuple[str, ...]] = {
    "cables": (
        "emodnet:bshcontiscables",
        "emodnet:pcablesbshcontis",
        "emodnet:pcablesnve",
    ),
    "pipelines": ("emodnet:pipelines",),
    "ports": ("emodnet:portlocations",),
    "windfarms": ("emodnet:windfarmspoly",),
}
CATEGORIES = {
    "cables": "cable",
    "pipelines": "pipeline",
    "ports": "port",
    "windfarms": "windfarm",
}
ALLOWED_GEOMETRIES = {
    "cable": {"LineString"},
    "pipeline": {"LineString"},
    "port": {"Point"},
    "windfarm": {"Polygon"},
}
NON_OPERATIONAL_WORDS = (
    "planned",
    "proposed",
    "application submitted",
    "approved",
    "under construction",
    "decommissioned",
    "disused",
    "removed",
    "abandoned",
    "out of use",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def _fallback(layer_name: str) -> dict[str, Any]:
    """Return the current validated snapshot, schematic on the first run."""
    payload = _read_json(LAYERS_DIR / f"{layer_name}.geojson", None)
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        return {"type": "FeatureCollection", "features": []}
    return payload


def _bbox_values() -> list[tuple[str, tuple[float, float, float, float]]]:
    result = []
    for name, bbox in EMODNET_BBOXES.items():
        result.append(
            (
                name,
                (
                    float(bbox["lon_min"]),
                    float(bbox["lat_min"]),
                    float(bbox["lon_max"]),
                    float(bbox["lat_max"]),
                ),
            )
        )
    return result


def _request_json(session: requests.Session, params: dict[str, Any]) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.get(
                EMODNET_WFS_URL,
                params=params,
                headers={"User-Agent": EMODNET_USER_AGENT, "Accept": "application/json"},
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
                raise ValueError("EMODnet returned an invalid GeoJSON FeatureCollection")
            return payload
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise RuntimeError(f"EMODnet request failed after 3 attempts: {last_error}")


def _valid_position(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) >= 2
        and all(isinstance(item, (int, float)) and math.isfinite(item) for item in value[:2])
    )


def _valid_line(coordinates: Any) -> bool:
    return isinstance(coordinates, list) and len(coordinates) >= 2 and all(
        _valid_position(position) for position in coordinates
    )


def _valid_polygon(coordinates: Any) -> bool:
    return (
        isinstance(coordinates, list)
        and bool(coordinates)
        and all(_valid_line(ring) and len(ring) >= 4 for ring in coordinates)
    )


def _explode_geometry(geometry: Any) -> list[dict[str, Any]]:
    if not isinstance(geometry, dict):
        return []
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Point" and _valid_position(coordinates):
        return [{"type": "Point", "coordinates": list(coordinates[:2])}]
    if geometry_type == "LineString" and _valid_line(coordinates):
        return [{"type": "LineString", "coordinates": coordinates}]
    if geometry_type == "Polygon" and _valid_polygon(coordinates):
        return [{"type": "Polygon", "coordinates": coordinates}]
    if geometry_type == "MultiLineString" and isinstance(coordinates, list):
        return [
            {"type": "LineString", "coordinates": line}
            for line in coordinates
            if _valid_line(line)
        ]
    if geometry_type == "MultiPolygon" and isinstance(coordinates, list):
        return [
            {"type": "Polygon", "coordinates": polygon}
            for polygon in coordinates
            if _valid_polygon(polygon)
        ]
    if geometry_type == "GeometryCollection":
        result: list[dict[str, Any]] = []
        for item in geometry.get("geometries", []):
            result.extend(_explode_geometry(item))
        return result
    return []


def _simplify_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    """Create a browser-sized, topology-preserving geometry at public-data precision."""
    if geometry.get("type") not in {"LineString", "Polygon"}:
        return geometry
    try:
        simplified = shape(geometry).simplify(
            EMODNET_SIMPLIFY_TOLERANCE_DEGREES, preserve_topology=True
        )
        if simplified.is_empty or simplified.geom_type != geometry["type"]:
            return geometry
        return mapping(simplified)
    except (TypeError, ValueError):
        return geometry


def _first_property(properties: dict[str, Any], names: Iterable[str]) -> Any:
    folded = {str(key).casefold(): value for key, value in properties.items()}
    for name in names:
        value = folded.get(name.casefold())
        if value is not None and str(value).strip():
            return value
    return None


def _date_value(properties: dict[str, Any], retrieved: datetime) -> str:
    value = _first_property(
        properties,
        ("last_updated", "updated", "update_date"),
    )
    if value is None:
        return retrieved.date().isoformat()
    text = str(value).strip()
    if len(text) == 4 and text.isdigit():
        return f"{text}-01-01"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return retrieved.date().isoformat()


def _source_id(feature: dict[str, Any], properties: dict[str, Any], geometry: dict[str, Any]) -> str:
    value = feature.get("id") or _first_property(
        properties, ("id", "fid", "objectid", "globalid", "uuid")
    )
    if value is not None and str(value).strip():
        return str(value).strip()
    encoded = json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


def _feature_name(
    properties: dict[str, Any], category: str, source_id: str, part_number: int
) -> str:
    value = _first_property(
        properties,
        (
            "name",
            "cable_name",
            "pipeline_name",
            "project",
            "port_name",
            "site_name",
            "from_loc",
        ),
    )
    if value is not None:
        return str(value).strip()
    suffix = f" part {part_number}" if part_number > 1 else ""
    return f"EMODnet {category} {source_id}{suffix}"


def _normalise_feature(
    feature: dict[str, Any],
    geometry: dict[str, Any],
    category: str,
    type_name: str,
    retrieved: datetime,
    part_number: int,
) -> dict[str, Any]:
    original = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    source_id = _source_id(feature, original, geometry)
    status = _first_property(original, ("status", "operational", "state"))
    status_text = str(status).strip() if status is not None else None
    scoring_eligible = not any(
        word in (status_text or "").casefold() for word in NON_OPERATIONAL_WORDS
    )
    notes = (
        "Public EMODnet Human Activities geometry; coverage and positional precision vary by "
        "originator. Snapshot retrieved for OSINT context; not for navigation or confirmation. / "
        "EMODnet 公开数据；覆盖范围与位置精度因原始提供方而异，仅作开源研究背景，不能用于导航或确认。"
    )
    properties: dict[str, Any] = {
        "name": _feature_name(original, category, source_id, part_number),
        "category": category,
        "source": "emodnet_human_activities",
        "source_url": EMODNET_CAPABILITIES_URL,
        "last_updated": _date_value(original, retrieved),
        "notes": notes,
        "route_precision": "published_open_data",
        "retrieved_at": retrieved.isoformat(),
        "emodnet_layer": type_name,
        "source_feature_id": source_id,
        "license": "EMODnet terms; verify the original provider metadata and attribution.",
        "scoring_eligible": scoring_eligible,
    }
    for output_name, candidates in {
        "operational_status": ("status", "operational", "state"),
        "operator": ("operator", "owner"),
        "country": ("country", "country_co", "iso3"),
        "medium": ("medium", "product", "substance"),
    }.items():
        value = _first_property(original, candidates)
        if value is not None:
            properties[output_name] = value
    return {"type": "Feature", "properties": properties, "geometry": geometry}


def _fetch_type(
    session: requests.Session,
    type_name: str,
    category: str,
    retrieved: datetime,
    bboxes: list[tuple[str, tuple[float, float, float, float]]] | None = None,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, bbox in bboxes or _bbox_values():
        start_index = 0
        while start_index < EMODNET_MAX_FEATURES_PER_SOURCE:
            params = {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": type_name,
                "bbox": ",".join(str(value) for value in bbox) + ",EPSG:4326",
                "srsName": "EPSG:4326",
                "outputFormat": "application/json",
                "count": EMODNET_PAGE_SIZE,
                "startIndex": start_index,
            }
            payload = _request_json(session, params)
            page = payload.get("features", [])
            for raw_feature in page:
                if not isinstance(raw_feature, dict):
                    continue
                for part_number, geometry in enumerate(
                    _explode_geometry(raw_feature.get("geometry")), start=1
                ):
                    if geometry["type"] not in ALLOWED_GEOMETRIES[category]:
                        continue
                    geometry = _simplify_geometry(geometry)
                    normalised = _normalise_feature(
                        raw_feature, geometry, category, type_name, retrieved, part_number
                    )
                    dedupe_key = "|".join(
                        (
                            type_name,
                            str(normalised["properties"]["source_feature_id"]),
                            json.dumps(geometry, sort_keys=True, separators=(",", ":")),
                        )
                    )
                    if dedupe_key not in seen:
                        seen.add(dedupe_key)
                        features.append(normalised)
            if len(page) < EMODNET_PAGE_SIZE:
                break
            start_index += EMODNET_PAGE_SIZE
    return features


def _fetch_layer(
    layer_name: str,
    session: requests.Session | None = None,
    force: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    existing = _fallback(layer_name)
    if USE_MOCK_DATA and not force:
        return existing, {
            "status": "credentials_missing_fallback_mock",
            "records_fetched": 0,
            "records_published": len(existing["features"]),
            "detail": "USE_MOCK_DATA is enabled; the existing infrastructure snapshot was retained.",
        }
    retrieved = _now()
    client = session or requests.Session()
    live_features: list[dict[str, Any]] = []
    errors: list[str] = []
    successful_sources: list[str] = []
    for type_name in LAYER_SPECS[layer_name]:
        try:
            source_features = _fetch_type(client, type_name, CATEGORIES[layer_name], retrieved)
            successful_sources.append(type_name)
            live_features.extend(source_features)
        except Exception as error:  # keep the last validated snapshot on any adapter failure
            errors.append(f"{type_name}: {type(error).__name__}: {error}"[:500])
    if not live_features:
        detail = "No valid live EMODnet features were returned; existing snapshot retained."
        if errors:
            detail += " " + " | ".join(errors)
        return existing, {
            "status": "error_kept_old_data",
            "records_fetched": 0,
            "records_published": len(existing["features"]),
            "source_layers": successful_sources,
            "detail": detail[:1500],
        }

    if layer_name == "cables":
        schematic_supplement = [
            feature
            for feature in existing["features"]
            if feature.get("properties", {}).get("source") == "manual_schematic"
        ]
        live_features.extend(schematic_supplement)
    else:
        schematic_supplement = []

    detail = (
        f"Fetched {len(live_features) - len(schematic_supplement)} public EMODnet features"
        f" from {len(successful_sources)} WFS layer(s)."
    )
    if schematic_supplement:
        detail += f" Retained {len(schematic_supplement)} labelled schematic cable supplements."
    if errors:
        detail += " Partial-source warnings: " + " | ".join(errors)
    return {"type": "FeatureCollection", "features": live_features}, {
        "status": "ok",
        "records_fetched": len(live_features) - len(schematic_supplement),
        "records_published": len(live_features),
        "schematic_supplement": len(schematic_supplement),
        "source_layers": successful_sources,
        "warnings": errors,
        "detail": detail[:1500],
    }


def fetch_cables(force: bool = False) -> dict[str, Any]:
    """Return EMODnet cable data, with labelled schematic gap-fill where retained."""
    return _fetch_layer("cables", force=force)[0]


def fetch_pipelines(force: bool = False) -> dict[str, Any]:
    """Return EMODnet pipeline data or the existing validated snapshot."""
    return _fetch_layer("pipelines", force=force)[0]


def fetch_ports(force: bool = False) -> dict[str, Any]:
    """Return EMODnet main-port locations or the existing validated snapshot."""
    return _fetch_layer("ports", force=force)[0]


def fetch_windfarms(force: bool = False) -> dict[str, Any]:
    """Return EMODnet wind-farm polygons or the existing validated snapshot."""
    return _fetch_layer("windfarms", force=force)[0]


def fetch_sensitive_areas() -> dict[str, Any]:
    """Sensitive areas remain the project CSV-derived reference layer."""
    return _fallback("sensitive_areas")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def run(force: bool = False) -> dict[str, Any]:
    """Refresh live layers without ever deleting a previous valid snapshot."""
    retrieved = _now()
    archive = RAW_ARCHIVE_DIR / retrieved.strftime("%Y%m%dT%H%M%SZ")
    layer_status: dict[str, dict[str, Any]] = {}
    fallbacks: list[str] = []
    for layer_name in LAYER_SPECS:
        payload, status = _fetch_layer(layer_name, force=force)
        layer_status[layer_name] = status
        destination = LAYERS_DIR / f"{layer_name}.geojson"
        if status["status"] == "ok":
            previous = _read_json(destination, None)
            if previous != payload:
                archive.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    shutil.copy2(destination, archive / destination.name)
                _write_json_atomic(destination, payload)
        else:
            fallbacks.append(f"{layer_name}: {status['detail']}")

    records_fetched = sum(int(item.get("records_fetched", 0)) for item in layer_status.values())
    records_published = sum(
        int(item.get("records_published", 0)) for item in layer_status.values()
    )
    statuses = {item["status"] for item in layer_status.values()}
    if statuses == {"ok"}:
        overall_status = "ok"
    elif statuses == {"credentials_missing_fallback_mock"}:
        overall_status = "credentials_missing_fallback_mock"
    else:
        overall_status = "error_kept_old_data"
    metadata = {
        "generated_at": retrieved.isoformat(),
        "source": "emodnet_human_activities",
        "source_url": EMODNET_CAPABILITIES_URL,
        "status": overall_status,
        "records_fetched": records_fetched,
        "records_published": records_published,
        "layers": layer_status,
        "fallbacks": fallbacks,
        "detail": "EMODnet WFS infrastructure snapshot; public-source coverage and precision vary by originator.",
    }
    _write_json_atomic(INFRASTRUCTURE_METADATA_PATH, metadata)
    return metadata


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore USE_MOCK_DATA for a deliberate live adapter check.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    result = run(force=_arguments().force)
    print(
        "EMODnet infrastructure:",
        result["status"],
        f"{result['records_published']} published features",
    )

