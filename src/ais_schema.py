"""Shared normalization helpers for the unified AIS schema."""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any


def map_ship_type(value: Any) -> str:
    """Map AIS numeric or descriptive ship types to the project's conservative enum."""
    if isinstance(value, str) and not value.strip().isdigit():
        label = value.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "cargo": "cargo",
            "carrier": "cargo",
            "tanker": "tanker",
            "fishing": "fishing",
            "research": "research",
            "research_vessel": "research",
            "tug": "tug",
            "towing": "tug",
            "service": "service",
            "support": "service",
            "naval": "naval",
            "military": "naval",
            "military_operations": "naval",
            "law_enforcement": "law_enforcement",
        }
        return aliases.get(label, "unknown")
    try:
        code = int(value)
    except (TypeError, ValueError):
        return "unknown"
    if code == 30:
        return "fishing"
    if code in {31, 32, 52}:
        return "tug"
    if code in {33, 34, 50, 51, 53, 54, 58, 59}:
        return "service"
    if code == 35:
        return "naval"
    if code == 55:
        return "law_enforcement"
    if 70 <= code <= 79:
        return "cargo"
    if 80 <= code <= 89:
        return "tanker"
    return "unknown"


def optional_string(value: Any) -> str | None:
    """Return a trimmed string, or ``None`` for missing/blank values."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def finite_float(value: Any, default: float = 0.0) -> float:
    """Return a finite float so JSON output never contains NaN or infinity."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if isfinite(number) else default


def iso8601_timestamp(value: Any, fallback: datetime | None = None) -> str:
    """Normalize Unix seconds/milliseconds or an ISO-8601 value to UTC."""
    fallback = fallback or datetime.now(timezone.utc)
    if value is None or value == "":
        return fallback.astimezone(timezone.utc).isoformat()

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = None
    if numeric is not None and isfinite(numeric):
        if numeric > 10_000_000_000:
            numeric /= 1000
        if numeric > 1_000_000_000:
            try:
                return datetime.fromtimestamp(numeric, timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                pass

    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return fallback.astimezone(timezone.utc).isoformat()


def in_bbox(lat: float, lon: float, bbox: dict[str, float]) -> bool:
    """Return whether a point is inside a configured latitude/longitude box."""
    return bbox["lat_min"] <= lat <= bbox["lat_max"] and bbox["lon_min"] <= lon <= bbox["lon_max"]
