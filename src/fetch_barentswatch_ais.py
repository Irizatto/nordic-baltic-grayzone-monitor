"""BarentsWatch Live AIS client using OAuth2 client credentials."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

from ais_schema import finite_float, in_bbox, iso8601_timestamp, map_ship_type, optional_string
from config import BARENTSWATCH_AIS_URL, BARENTSWATCH_BBOX, BARENTSWATCH_CLIENT_ID, BARENTSWATCH_CLIENT_SECRET, BARENTSWATCH_TOKEN_URL, PROCESSED_DATA


def _request(method: str, url: str, **kwargs) -> requests.Response:
    for attempt in range(3):
        try:
            response = requests.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def _token() -> str | None:
    """Return a bearer token, or None when credentials are deliberately absent."""
    if not BARENTSWATCH_CLIENT_ID or not BARENTSWATCH_CLIENT_SECRET:
        return None
    response = _request("POST", BARENTSWATCH_TOKEN_URL, data={"client_id":BARENTSWATCH_CLIENT_ID,"client_secret":BARENTSWATCH_CLIENT_SECRET,"scope":"ais","grant_type":"client_credentials"}, headers={"Content-Type":"application/x-www-form-urlencoded"})
    return response.json()["access_token"]


def fetch_barentswatch_ais() -> list[dict] | None:
    """Fetch latest BarentsWatch positions in the configured region, or None without credentials."""
    token = _token()
    if not token:
        return None
    payload = _request("GET", BARENTSWATCH_AIS_URL + "/v1/latest/combined", headers={"Authorization":"Bearer " + token,"Accept":"application/json"}).json()
    items = payload if isinstance(payload,list) else payload.get("items",payload.get("data",[]))
    records = []
    for item in items:
        mmsi = optional_string(item.get("mmsi"))
        try:
            lat = float(item.get("latitude", item.get("lat")))
            lon = float(item.get("longitude", item.get("lon")))
        except (TypeError, ValueError):
            continue
        if not mmsi or not in_bbox(lat, lon, BARENTSWATCH_BBOX):
            continue
        records.append({
            "mmsi": mmsi,
            "imo": optional_string(item.get("imoNumber", item.get("imo"))),
            "name": optional_string(item.get("name")),
            "callsign": optional_string(item.get("callSign", item.get("callsign"))),
            "flag": optional_string(item.get("countryCode", item.get("flag"))),
            "ship_type": map_ship_type(item.get("shipType", item.get("shipTypeCode"))),
            "lat": lat,
            "lon": lon,
            "speed": finite_float(item.get("speedOverGround", item.get("sog", item.get("speed")))),
            "course": finite_float(item.get("courseOverGround", item.get("cog", item.get("course")))),
            "heading": finite_float(item.get("trueHeading", item.get("heading"))),
            "timestamp": iso8601_timestamp(item.get("msgtime", item.get("timestamp", item.get("time")))),
            "source": "barentswatch",
        })
    return records


def write_latest(records: list[dict]) -> Path:
    """Write a new dated snapshot rather than destroying prior data."""
    PROCESSED_DATA.mkdir(parents=True, exist_ok=True)
    base = PROCESSED_DATA / "ais_latest_barentswatch.json"
    path = base if not base.exists() else PROCESSED_DATA / ("ais_latest_barentswatch_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return path
