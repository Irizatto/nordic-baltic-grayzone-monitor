"""Generate static daily and weekly research-lead reports."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from config import DOCS_DATA, ROOT

REPORTS = DOCS_DATA.parent / "reports"
HELSINKI = ZoneInfo("Europe/Helsinki")
LIMITATIONS = "Data may be incomplete, delayed, schematic, mock, or unavailable. Review leads require human assessment. / 数据可能不完整、延迟、为示意数据、模拟数据或暂时不可用；所有线索均需人工评估。"
DISCLAIMER = "Risk scores are review priorities, not legal or attribution determinations. / 风险分数仅表示审查优先级，不构成法律或归因结论。"


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def page(title: str, body: str, back_href: str | None = None, back_label: str = "Reports / 报告") -> str:
    back = f'<p><a href="{escape(back_href, quote=True)}">← {escape(back_label)}</a></p>' if back_href else ""
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>body{{margin:0;padding:24px;background:#07111f;color:#e6f1ff;font:14px system-ui,sans-serif}}main{{max-width:1100px;margin:auto}}h1,h2{{color:#00e5ff}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #203448;color:#c9d8ea;vertical-align:top}}.muted{{color:#91a4bd}}.notice{{padding:12px;border-left:3px solid #00e5ff;background:#0a1628}}a{{color:#00e5ff}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;color:#c9d8ea}}</style></head>
<body><main>{back}<h1>{escape(title)}</h1>{body}</main></body></html>
"""


def _today_helsinki(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(HELSINKI).date()


def _event_rows() -> list[dict]:
    path = ROOT / "data" / "events" / "events.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def daily_payload(today: date | None = None) -> dict:
    today = today or _today_helsinki()
    data = load_json(DOCS_DATA / "data.json", {"metadata":{},"vessels":[],"sar_detections":[]})
    metadata = load_json(DOCS_DATA / "metadata.json", data.get("metadata", {}))
    vessels = data.get("vessels", []) if isinstance(data.get("vessels"), list) else []
    sar = data.get("sar_detections", []) if isinstance(data.get("sar_detections"), list) else []
    counts = Counter(v.get("risk_level", "Normal") for v in vessels)
    near = []
    for vessel in vessels:
        distance = (vessel.get("nearest_infrastructure") or {}).get("distance_km")
        if isinstance(distance, (int, float)) and distance <= 10:
            near.append(vessel)
    top = sorted(vessels, key=lambda v:v.get("risk_score", 0), reverse=True)[:10]
    events = [row for row in _event_rows() if row.get("date") == today.isoformat()]
    return {
        "date":today.isoformat(),
        "metadata":metadata,
        "total_vessels":len(vessels),
        "risk_counts":dict(counts),
        "sar_unmatched":sum(not bool(d.get("matched")) for d in sar),
        "near_infrastructure":near,
        "top_vessels":top,
        "identity_changes":[event for event in events if event.get("event_type") == "identity_change"],
        "sts_events":[event for event in events if event.get("event_type") == "sts_rendezvous"],
        "new_events":events,
    }


def daily_html(report: dict) -> str:
    top_rows = []
    for vessel in report["top_vessels"]:
        rules = vessel.get("triggered_rules") if isinstance(vessel.get("triggered_rules"), list) else []
        rule_text = "; ".join(f"{rule.get('rule_id','')} (+{rule.get('points',0)}): {rule.get('evidence','')}" for rule in rules)
        top_rows.append(f"<tr><td>{escape(str(vessel.get('name') or 'Unknown'))}</td><td>{escape(str(vessel.get('risk_score',0)))}</td><td>{escape(str(vessel.get('risk_level','Normal')))}</td><td>{escape(rule_text)}</td></tr>")
    top = "".join(top_rows) or '<tr><td colspan="4">No vessels in this window. / 此时间窗内无船舶。</td></tr>'
    statuses = "".join(f"<li>{escape(str(name))}: {escape(str(info.get('status','unknown')))} — {escape(str(info.get('timestamp','not supplied')))}</li>" for name,info in report["metadata"].get("source_status", {}).items()) or "<li>No source status supplied. / 未提供数据源状态。</li>"
    body = (
        f'<p class="muted">Data updated / 数据更新时间: {escape(str(report["metadata"].get("generated_at", "not supplied")))}</p>'
        f'<h2>Source status / 数据源状态</h2><ul>{statuses}</ul>'
        f'<h2>Window summary / 时间窗摘要</h2><p>Total vessels / 船舶总数: {report["total_vessels"]} · SAR unmatched / 未匹配 SAR: {report["sar_unmatched"]} · Near infrastructure / 临近基础设施: {len(report["near_infrastructure"])}</p>'
        f'<p>Risk counts / 风险等级计数: {escape(json.dumps(report["risk_counts"], ensure_ascii=False))}</p>'
        f'<h2>Top review priorities / 最高审查优先级</h2><table><tr><th>Vessel / 船舶</th><th>Score / 分数</th><th>Level / 等级</th><th>Triggered rules and evidence / 触发规则与证据</th></tr>{top}</table>'
        f'<h2>New leads / 新线索</h2><p>Identity changes / 身份变化: {len(report["identity_changes"])} · STS leads / 船对船线索: {len(report["sts_events"])} · New event records / 新事件记录: {len(report["new_events"])}</p>'
        f'<p class="notice">{escape(LIMITATIONS)}</p><p class="notice">{escape(DISCLAIMER)}</p>'
    )
    return page("Daily research-lead report / 每日研究线索报告", body, "../reports.html")


def _daily_reports_for_week(year: int, week: int) -> list[dict]:
    result = []
    for file in REPORTS.glob("????-??-??.json"):
        try:
            report_date = date.fromisoformat(file.stem)
        except ValueError:
            continue
        iso = report_date.isocalendar()
        if (iso.year, iso.week) == (year, week):
            payload = load_json(file, {})
            if payload:
                result.append(payload)
    return sorted(result, key=lambda item:item.get("date", ""))


def weekly_payload(today: date | None = None) -> dict:
    today = today or _today_helsinki()
    year, week, _ = today.isocalendar()
    daily = _daily_reports_for_week(year, week)
    events = []
    for event in load_json(DOCS_DATA / "events.json", {"events":[]}).get("events", []):
        try:
            event_iso = date.fromisoformat(str(event.get("date"))).isocalendar()
        except ValueError:
            continue
        if (event_iso.year, event_iso.week) == (year, week):
            events.append(event)
    rule_counts = Counter()
    for report in daily:
        for vessel in report.get("top_vessels", []):
            for rule in vessel.get("triggered_rules", []):
                if rule.get("rule_id"):
                    rule_counts[rule["rule_id"]] += 1
    confidence_rank = {"high":2,"medium":1,"low":0}
    shortlist = sorted((event for event in events if event.get("confidence") in {"medium","high"}), key=lambda event:(confidence_rank.get(event.get("confidence"),0),float(event.get("risk_score") or 0)), reverse=True)[:10]
    return {
        "year":year,"week":week,
        "risk_trend":[{"date":item.get("date"),"counts":item.get("risk_counts",{})} for item in daily],
        "regional_distribution":dict(Counter(event.get("region", "Unknown") for event in events)),
        "event_type_distribution":dict(Counter(event.get("event_type", "unknown") for event in events)),
        "frequent_rules":dict(rule_counts),
        "shortlist":shortlist,
    }


def weekly_html(report: dict) -> str:
    body = (
        f'<h2>Risk trend / 风险趋势</h2><pre>{escape(json.dumps(report["risk_trend"],indent=2,ensure_ascii=False))}</pre>'
        f'<h2>Regional distribution / 区域分布</h2><pre>{escape(json.dumps(report["regional_distribution"],indent=2,ensure_ascii=False))}</pre>'
        f'<h2>Event types / 事件类型</h2><pre>{escape(json.dumps(report["event_type_distribution"],indent=2,ensure_ascii=False))}</pre>'
        f'<h2>Frequently triggered rules / 高频触发规则</h2><pre>{escape(json.dumps(report["frequent_rules"],indent=2,ensure_ascii=False))}</pre>'
        f'<h2>Candidates for human review / process-tracing / 人工复核候选</h2><pre>{escape(json.dumps(report["shortlist"],indent=2,ensure_ascii=False))}</pre>'
        f'<p class="notice">{escape(LIMITATIONS)}</p><p class="notice">{escape(DISCLAIMER)}</p>'
    )
    return page(f'Weekly research-lead report / 每周研究线索报告 {report["year"]}-W{report["week"]:02d}', body, "../reports.html")


def write_report(name: str, payload: dict, html: str) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / (name + ".json")).write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (REPORTS / (name + ".html")).write_text(html,encoding="utf-8")


def _report_sort_key(path: Path) -> tuple[date, int]:
    try:
        return date.fromisoformat(path.stem), 1
    except ValueError:
        match = re.fullmatch(r"(\d{4})-W(\d{2})", path.stem)
        if match:
            return date.fromisocalendar(int(match.group(1)),int(match.group(2)),7), 0
    return date.min, -1


def index_reports() -> None:
    items = sorted(REPORTS.glob("*.html"), key=_report_sort_key, reverse=True)
    links = "".join(f'<li><a href="reports/{escape(item.name,quote=True)}">{escape(item.stem)}</a></li>' for item in items)
    body = f'<ul>{links or "<li>No reports yet. / 暂无报告。</li>"}</ul><p class="notice">{escape(DISCLAIMER)}</p>'
    (DOCS_DATA.parent / "reports.html").write_text(page("Reports / 报告", body, "index.html", "Dashboard / 仪表板"),encoding="utf-8")


def main() -> None:
    today = _today_helsinki()
    report = daily_payload(today)
    write_report(report["date"], report, daily_html(report))
    if today.weekday() == 0:
        week = weekly_payload(today)
        write_report(f'{week["year"]}-W{week["week"]:02d}', week, weekly_html(week))
    index_reports()


if __name__ == "__main__":
    main()
