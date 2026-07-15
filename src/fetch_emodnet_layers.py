"""EMODnet Human Activities adapter skeleton.

This stage deliberately does not download live data. Each public function returns
its matching committed schematic GeoJSON file if network access, credentials, or
an implementation-specific EMODnet endpoint is unavailable. Future work can
replace the adapter section while preserving the output schema.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
LAYERS_DIR = ROOT / "docs" / "data" / "layers"
EMODNET_HUMAN_ACTIVITIES = "https://emodnet.ec.europa.eu/en/human-activities"


def _network_available() -> bool:
    """Safely test access to the public EMODnet Human Activities landing page."""
    if os.getenv("USE_MOCK_DATA", "true").lower() == "true":
        return False
    try:
        return requests.head(EMODNET_HUMAN_ACTIVITIES, timeout=5).ok
    except requests.RequestException:
        return False


def _fallback(layer_name: str) -> dict[str, Any]:
    """Load committed schematic data without changing any existing data file."""
    path = LAYERS_DIR / (layer_name + ".geojson")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _fetch_or_fallback(layer_name: str) -> dict[str, Any]:
    """Future download/conversion insertion point; uses a stable schematic fallback now."""
    if not _network_available():
        return _fallback(layer_name)
    # EMODnet dataset endpoints and licence-compatible conversion are not wired yet.
    return _fallback(layer_name)


def fetch_cables() -> dict[str, Any]:
    """Return cable features in the dashboard GeoJSON schema."""
    return _fetch_or_fallback("cables")


def fetch_pipelines() -> dict[str, Any]:
    """Return pipeline features in the dashboard GeoJSON schema."""
    return _fetch_or_fallback("pipelines")


def fetch_ports() -> dict[str, Any]:
    """Return port reference features in the dashboard GeoJSON schema."""
    return _fetch_or_fallback("ports")


def fetch_windfarms() -> dict[str, Any]:
    """Return wind-area features in the dashboard GeoJSON schema."""
    return _fetch_or_fallback("windfarms")


def fetch_sensitive_areas() -> dict[str, Any]:
    """Return sensitive-area features in the dashboard GeoJSON schema."""
    return _fetch_or_fallback("sensitive_areas")

