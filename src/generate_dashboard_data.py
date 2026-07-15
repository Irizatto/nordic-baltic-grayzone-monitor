"""Merge AIS/SAR sources into safe, size-bounded static dashboard data."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from analyze_suspicious import (
    history_for_vessel,
    load_infrastructure_features,
    score_vessel,
    update_history,
)
from config import DOCS_DATA, USE_MOCK_DATA
from events import record_events
from fetch_barentswatch_ais import fetch_barentswatch_ais, write_latest as write_barentswatch
from fetch_digitraffic_ais import fetch_digitraffic_ais, write_latest as write_digitraffic
from fetch_gfw_data import fetch_gfw_sar, write_latest as write_gfw_sar

PRIORITY_LEVELS = {"Watch", "High Review Priority", "Critical Review Priority"}
PUBLISH_LIMIT = 150


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _record_time(record: dict) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(record.get("timestamp", "")).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _merge_newest(records: list[dict]) -> list[dict]:
    newest = {}
    for record in records:
        key = str(record.get("mmsi") or "").strip()
        if key and (key not in newest or _record_time(record) > _record_time(newest[key])):
            newest[key] = record
    return list(newest.values())


def _previous_by_source(previous: dict, source: str) -> list[dict]:
    return [dict(record) for record in previous.get("vessels", []) if record.get("source") == source]


def _safe_error(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"[:500]


def _preserve_status(previous_metadata: dict, source_status: dict, source: str) -> None:
    old = previous_metadata.get("source_status", {}).get(source)
    if isinstance(old, dict):
        source_status[source] = dict(old)


def _fetch_ais(previous: dict, previous_metadata: dict, source_status: dict, fetch_ais: bool) -> tuple[list[dict], dict[str, int]]:
    fetched_counts: dict[str, int] = {}
    if not fetch_ais:
        for source in ("digitraffic", "barentswatch"):
            _preserve_status(previous_metadata, source_status, source)
        records = [dict(record) for record in previous.get("vessels", [])]
        return records, fetched_counts

    records = _previous_by_source(previous, "mock")
    fetched_counts["mock"] = len(records)

    if USE_MOCK_DATA:
        source_status["digitraffic"] = {"status":"credentials_missing_fallback_mock","timestamp":_now(),"detail":"USE_MOCK_DATA is enabled"}
    else:
        try:
            digitraffic = fetch_digitraffic_ais()
            if not digitraffic:
                raise ValueError("Digitraffic returned no valid records; retaining its previous published snapshot")
            write_digitraffic(digitraffic)
            records.extend(digitraffic)
            fetched_counts["digitraffic"] = len(digitraffic)
            source_status["digitraffic"] = {"status":"ok","timestamp":_now(),"records_fetched":len(digitraffic)}
        except Exception as error:
            retained = _previous_by_source(previous, "digitraffic")
            records.extend(retained)
            fetched_counts["digitraffic"] = 0
            source_status["digitraffic"] = {"status":"error_kept_old_data","timestamp":_now(),"records_fetched":0,"records_reused":len(retained),"detail":_safe_error(error)}

    if USE_MOCK_DATA:
        source_status["barentswatch"] = {"status":"credentials_missing_fallback_mock","timestamp":_now(),"detail":"USE_MOCK_DATA is enabled"}
    else:
        try:
            barentswatch = fetch_barentswatch_ais()
            if barentswatch is None:
                source_status["barentswatch"] = {"status":"credentials_missing_fallback_mock","timestamp":_now(),"detail":"BARENTSWATCH_CLIENT_ID / BARENTSWATCH_CLIENT_SECRET unavailable"}
            elif not barentswatch:
                raise ValueError("BarentsWatch returned no valid records; retaining its previous published snapshot")
            else:
                write_barentswatch(barentswatch)
                records.extend(barentswatch)
                fetched_counts["barentswatch"] = len(barentswatch)
                source_status["barentswatch"] = {"status":"ok","timestamp":_now(),"records_fetched":len(barentswatch)}
        except Exception as error:
            retained = _previous_by_source(previous, "barentswatch")
            records.extend(retained)
            fetched_counts["barentswatch"] = 0
            source_status["barentswatch"] = {"status":"error_kept_old_data","timestamp":_now(),"records_fetched":0,"records_reused":len(retained),"detail":_safe_error(error)}
    return records, fetched_counts


def _fetch_sar(previous: dict, previous_metadata: dict, source_status: dict, fetch_sar: bool) -> tuple[list[dict], int]:
    if not fetch_sar:
        _preserve_status(previous_metadata, source_status, "gfw_sar")
        return [dict(record) for record in previous.get("sar_detections", [])], 0

    try:
        detections, status, detail = fetch_gfw_sar()
    except Exception as error:
        detections = [dict(record) for record in previous.get("sar_detections", [])]
        status = "error_kept_old_data"
        detail = "Unexpected GFW adapter error; previous detections retained: " + _safe_error(error)
    fetched_count = len(detections) if status == "ok" else 0
    if status == "ok":
        write_gfw_sar(detections)
    elif status == "error_kept_old_data":
        retained = [dict(record) for record in previous.get("sar_detections", [])]
        if retained:
            detections = retained
            detail += f" Reused {len(retained)} previous detections."
    source_status["gfw_sar"] = {"status":status,"timestamp":_now(),"records_fetched":fetched_count,"records_published":len(detections),"detail":detail}
    return detections, fetched_count


def _cap_vessels(vessels: list[dict]) -> list[dict]:
    priority = sorted((v for v in vessels if v.get("risk_level") in PRIORITY_LEVELS), key=lambda v:v.get("risk_score", 0), reverse=True)
    remainder = sorted((v for v in vessels if v.get("risk_level") not in PRIORITY_LEVELS), key=lambda v:v.get("risk_score", 0), reverse=True)
    return priority + remainder[:max(0, PUBLISH_LIMIT-len(priority))]


def run(*, fetch_ais: bool = True, fetch_sar: bool = True) -> dict:
    """Refresh selected sources, rescore, retain safe fallbacks, and publish atomically sized JSON."""
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    previous = _read(DOCS_DATA / "data.json", {"metadata":{},"vessels":[],"sar_detections":[]})
    previous_metadata = _read(DOCS_DATA / "metadata.json", previous.get("metadata", {}))
    infrastructure_metadata = _read(DOCS_DATA / "infrastructure_metadata.json", {})
    helcom_metadata = _read(DOCS_DATA / "helcom_metadata.json", {})
    source_status: dict[str, dict] = {}

    source_records, fetched_counts = _fetch_ais(previous, previous_metadata, source_status, fetch_ais)
    sar_detections, sar_fetched = _fetch_sar(previous, previous_metadata, source_status, fetch_sar)
    if isinstance(infrastructure_metadata, dict) and infrastructure_metadata:
        source_status["emodnet"] = {
            "status": infrastructure_metadata.get("status", "error_kept_old_data"),
            "timestamp": infrastructure_metadata.get("generated_at", _now()),
            "records_fetched": infrastructure_metadata.get("records_fetched", 0),
            "records_published": infrastructure_metadata.get("records_published", 0),
            "detail": infrastructure_metadata.get(
                "detail", "EMODnet infrastructure snapshot metadata is incomplete."
            ),
        }
    if isinstance(helcom_metadata, dict) and helcom_metadata:
        source_status["helcom"] = {
            "status": helcom_metadata.get("status", "error_kept_old_data"),
            "timestamp": helcom_metadata.get("generated_at", _now()),
            "records_fetched": helcom_metadata.get("records_fetched", 0),
            "records_published": helcom_metadata.get("records_published", 0),
            "detail": helcom_metadata.get(
                "detail", "HELCOM MPA snapshot metadata is incomplete."
            ),
        }
    vessels = _merge_newest(source_records)
    history_index = update_history(vessels)
    infrastructure_features = load_infrastructure_features()
    scored = [
        score_vessel(
            vessel,
            history_for_vessel(history_index, vessel),
            sar_detections,
            features=infrastructure_features,
        )
        for vessel in vessels
    ]
    record_events(scored, sar_detections)
    published = _cap_vessels(scored)

    for source in sorted({str(v.get("source") or "unknown") for v in scored} - {"mock"}):
        status = source_status.setdefault(source, {"status":"ok","timestamp":_now()})
        status.setdefault("records_fetched", fetched_counts.get(source, 0))
        status["records_published"] = sum(v.get("source") == source for v in published)
    if "gfw_sar" in source_status:
        source_status["gfw_sar"]["records_fetched"] = sar_fetched
        source_status["gfw_sar"]["records_published"] = len(sar_detections)

    published_sources = {str(v.get("source") or "unknown") for v in published}
    published_sources.update(str(d.get("source") or "unknown") for d in sar_detections)
    all_mock = not published_sources or published_sources <= {"mock"}
    mode = "mock" if all_mock else ("mixed" if "mock" in published_sources else "live")
    infrastructure_fallbacks = infrastructure_metadata.get("fallbacks", []) if isinstance(infrastructure_metadata, dict) else []
    helcom_fallbacks = helcom_metadata.get("fallbacks", []) if isinstance(helcom_metadata, dict) else []
    metadata = {
        "generated_at":_now(),
        "mode":mode,
        "sources":sorted(published_sources),
        "source_status":source_status,
        "fallbacks":["Mock records remain clearly labelled when a live source or credential is unavailable."] + list(infrastructure_fallbacks) + list(helcom_fallbacks),
    }
    output = {"metadata":metadata,"vessels":published,"sar_detections":sar_detections}
    (DOCS_DATA / "data.json").write_text(json.dumps(output,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (DOCS_DATA / "metadata.json").write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return output


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ais-only", action="store_true", help="Refresh AIS and preserve the published SAR snapshot.")
    mode.add_argument("--sar-only", action="store_true", help="Refresh SAR and reuse the published AIS snapshot.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _arguments()
    result = run(fetch_ais=not args.sar_only, fetch_sar=not args.ais_only)
    print("Dashboard records:", len(result["vessels"]))
