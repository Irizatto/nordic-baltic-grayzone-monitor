"""Generate static daily and weekly research-lead reports."""
from __future__ import annotations
import csv, json
from collections import Counter
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path

from config import DOCS_DATA, ROOT

REPORTS = DOCS_DATA.parent / "reports"
LIMITATIONS = "Data may be incomplete, delayed, schematic, mock, or unavailable. Review leads require human assessment."
DISCLAIMER = "Risk scores are review priorities, not legal or attribution determinations."

def load_json(path, default):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError): return default

def page(title, body):
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title><style>body{{margin:0;padding:24px;background:#07111f;color:#e6f1ff;font:14px system-ui,sans-serif}}main{{max-width:1100px;margin:auto}}h1,h2{{color:#00e5ff}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #203448;color:#c9d8ea}}.muted{{color:#91a4bd}}.notice{{padding:12px;border-left:3px solid #00e5ff;background:#0a1628}}a{{color:#00e5ff}}</style><main><p><a href="../reports.html">← Reports / 报告</a></p><h1>{escape(title)}</h1>{body}</main></html>"""

def daily_payload(today=None):
    data=load_json(DOCS_DATA/"data.json",{"metadata":{},"vessels":[],"sar_detections":[]})
    metadata=load_json(DOCS_DATA/"metadata.json",data.get("metadata",{}))
    vessels=data.get("vessels",[]); sar=data.get("sar_detections",[])
    counts=Counter(v.get("risk_level","Normal") for v in vessels)
    near=[v for v in vessels if (v.get("nearest_infrastructure",{}).get("distance_km") or 9999)<=10]
    top=sorted(vessels,key=lambda v:v.get("risk_score",0),reverse=True)[:10]
    events=[]
    path=ROOT/"data"/"events"/"events.csv"
    if path.exists():
        with path.open(newline="",encoding="utf-8") as handle: events=[row for row in csv.DictReader(handle) if row.get("date")==str(today or date.today())]
    return {"date":str(today or date.today()),"metadata":metadata,"total_vessels":len(vessels),"risk_counts":dict(counts),"sar_unmatched":sum(not d.get("matched",False) for d in sar),"near_infrastructure":near,"top_vessels":top,"identity_changes":[v for v in vessels if any(r.get("rule_id")=="identity_change" for r in v.get("triggered_rules",[]))],"sts_events":[v for v in vessels if any(r.get("rule_id")=="sts_rendezvous" for r in v.get("triggered_rules",[]))],"new_events":events}

def daily_html(report):
    top="".join(f"<tr><td>{escape(str(v.get('name') or 'Unknown'))}</td><td>{v.get('risk_score',0)}</td><td>{escape(v.get('risk_level','Normal'))}</td><td>{escape('; '.join(r.get('rule_id','') for r in v.get('triggered_rules',[])))}</td></tr>" for v in report["top_vessels"]) or "<tr><td colspan=4>No vessels in this window.</td></tr>"
    statuses="".join(f"<li>{escape(name)}: {escape(str(info.get('status')))} — {escape(str(info.get('timestamp','')))}</li>" for name,info in report["metadata"].get("source_status",{}).items()) or "<li>No source status supplied.</li>"
    body=f"<p class=muted>Data updated: {escape(str(report['metadata'].get('generated_at','not supplied')))}</p><h2>Source status / 数据源状态</h2><ul>{statuses}</ul><h2>Window summary / 窗口摘要</h2><p>Total vessels: {report['total_vessels']} · SAR unmatched: {report['sar_unmatched']} · Near infrastructure: {len(report['near_infrastructure'])}</p><p>Risk counts: {escape(json.dumps(report['risk_counts']))}</p><h2>Top review priorities / 最高审查优先级</h2><table><tr><th>Vessel</th><th>Score</th><th>Level</th><th>Triggered rules / 触发规则</th></tr>{top}</table><h2>New leads / 新线索</h2><p>Identity changes: {len(report['identity_changes'])} · STS leads: {len(report['sts_events'])} · New event records: {len(report['new_events'])}</p><p class=notice>{LIMITATIONS}</p><p class=notice>{DISCLAIMER}</p>"
    return page("Daily research-lead report / 每日研究线索报告",body)

def weekly_payload(today=None):
    today=today or date.today(); year,week,_=today.isocalendar(); files=sorted(REPORTS.glob(f"{year}-W{week:02d}*.json"))
    daily=[load_json(file,{}) for file in files if file.name[0:10]!=f"{year}-W{week:02d}"]
    events=load_json(DOCS_DATA/"events.json",{"events":[]}).get("events",[])
    return {"year":year,"week":week,"risk_trend":[{"date":x.get("date"),"counts":x.get("risk_counts",{})} for x in daily],"regional_distribution":dict(Counter(e.get("region","Unknown") for e in events)),"event_type_distribution":dict(Counter(e.get("event_type","unknown") for e in events)),"frequent_rules":dict(Counter(r.get("rule_id") for x in daily for v in x.get("top_vessels",[]) for r in v.get("triggered_rules",[]))),"shortlist":sorted([e for e in events if e.get("confidence") in {"medium","high"}],key=lambda e:float(e.get("risk_score",0)),reverse=True)[:10]}

def weekly_html(report):
    return page(f"Weekly research-lead report / 每周研究线索报告 {report['year']}-W{report['week']:02d}",f"<h2>Risk trend / 风险趋势</h2><pre>{escape(json.dumps(report['risk_trend'],indent=2))}</pre><h2>Regional distribution / 区域分布</h2><pre>{escape(json.dumps(report['regional_distribution'],indent=2))}</pre><h2>Event types / 事件类型</h2><pre>{escape(json.dumps(report['event_type_distribution'],indent=2))}</pre><h2>Frequently triggered rules / 高频触发规则</h2><pre>{escape(json.dumps(report['frequent_rules'],indent=2))}</pre><h2>Candidates for human review / process-tracing</h2><pre>{escape(json.dumps(report['shortlist'],indent=2))}</pre><p class=notice>{LIMITATIONS}</p><p class=notice>{DISCLAIMER}</p>")

def write_report(name,payload,html):
    REPORTS.mkdir(parents=True,exist_ok=True)
    (REPORTS/(name+".json")).write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (REPORTS/(name+".html")).write_text(html,encoding="utf-8")

def index_reports():
    items=sorted(REPORTS.glob("*.html"),reverse=True)
    links="".join(f"<li><a href='reports/{escape(item.name)}'>{escape(item.stem)}</a></li>" for item in items)
    (DOCS_DATA.parent/"reports.html").write_text(page("Reports / 报告",f"<h1>Reports / 报告</h1><ul>{links or '<li>No reports yet. / 暂无报告。</li>'}</ul><p class=notice>{DISCLAIMER}</p>"),encoding="utf-8")

def main():
    report=daily_payload(); write_report(report["date"],report,daily_html(report))
    if datetime.now().weekday()==0:
        week=weekly_payload(); write_report(f"{week['year']}-W{week['week']:02d}",week,weekly_html(week))
    index_reports()

if __name__=="__main__": main()
