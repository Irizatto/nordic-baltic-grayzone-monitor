"""BarentsWatch Live AIS client using OAuth2 client credentials."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

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


def _ship_type(value: Any) -> str:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return "unknown"
    if 70 <= code <= 79: return "cargo"
    if 80 <= code <= 89: return "tanker"
    if code == 30: return "fishing"
    if code in {31,32}: return "tug"
    if code in {33,34,35}: return "service"
    if code == 36: return "naval"
    if code == 55: return "law_enforcement"
    if code in {37,57,97}: return "research"
    return "unknown"


def fetch_barentswatch_ais() -> list[dict] | None:
    """Fetch latest BarentsWatch positions in the configured region, or None without credentials."""
    token = _token()
    if not token:
        return None
    params = {"north":BARENTSWATCH_BBOX["lat_max"],"south":BARENTSWATCH_BBOX["lat_min"],"east":BARENTSWATCH_BBOX["lon_max"],"west":BARENTSWATCH_BBOX["lon_min"]}
    payload = _request("GET", BARENTSWATCH_AIS_URL + "/v1/latest/combined", params=params, headers={"Authorization":"Bearer " + token,"Accept":"application/json"}).json()
    items = payload if isinstance(payload,list) else payload.get("items",payload.get("data",[]))
    records = []
    for item in items:
        lat, lon = item.get("latitude",item.get("lat")), item.get("longitude",item.get("lon"))
        try: lat, lon = float(lat), float(lon)
        except (TypeError,ValueError): continue
        records.append({"mmsi":str(item.get("mmsi")),"imo":item.get("imo"),"name":item.get("name"),"callsign":item.get("callsign"),"flag":item.get("flag"),"ship_type":_ship_type(item.get("shipType",item.get("shipTypeCode"))),"lat":lat,"lon":lon,"speed":float(item.get("sog",item.get("speed",0)) or 0),"course":float(item.get("cog",item.get("course",0)) or 0),"heading":float(item.get("heading",0) or 0),"timestamp":str(item.get("timestamp",item.get("time",datetime.now(timezone.utc).isoformat()))),"source":"barentswatch"})
    return records


def write_latest(records: list[dict]) -> Path:
    """Write a new dated snapshot rather than destroying prior data."""
    PROCESSED_DATA.mkdir(parents=True, exist_ok=True)
    base = PROCESSED_DATA / "ais_latest_barentswatch.json"
    path = base if not base.exists() else PROCESSED_DATA / ("ais_latest_barentswatch_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    return path
