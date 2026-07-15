"""Regression tests for daily/weekly report windows."""
import csv
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import generate_reports as reports
from events import HEADER


class ReportTests(unittest.TestCase):
    def test_daily_zero_distance_and_weekly_file_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs_data = root / "docs" / "data"
            report_dir = root / "docs" / "reports"
            canonical = root / "data" / "events"
            docs_data.mkdir(parents=True)
            report_dir.mkdir(parents=True)
            canonical.mkdir(parents=True)
            vessel = {"name":"TEST","risk_score":5,"risk_level":"Watch","nearest_infrastructure":{"distance_km":0.0},"triggered_rules":[{"rule_id":"ais_gap_6h","points":2,"evidence":"gap"}]}
            (docs_data / "data.json").write_text(json.dumps({"metadata":{},"vessels":[vessel],"sar_detections":[]}),encoding="utf-8")
            (docs_data / "metadata.json").write_text(json.dumps({"generated_at":"2026-07-13T05:30:00Z","source_status":{}}),encoding="utf-8")
            current_event = dict(zip(HEADER,["NBGM-20260713-0001","2026-07-13","08:30:00+00:00","Test","60","24","TEST","123","","cargo","identity_change","5","[]","","","digitraffic","low","lead"]))
            old_event = {**current_event,"event_id":"NBGM-20260706-0001","date":"2026-07-06","event_type":"ais_gap"}
            with (canonical / "events.csv").open("w",newline="",encoding="utf-8") as handle:
                writer=csv.DictWriter(handle,fieldnames=HEADER); writer.writeheader(); writer.writerows([current_event,old_event])
            (docs_data / "events.json").write_text(json.dumps({"events":[current_event,old_event]}),encoding="utf-8")
            for day in ("2026-07-13","2026-07-14"):
                (report_dir / f"{day}.json").write_text(json.dumps({"date":day,"risk_counts":{"Watch":1},"top_vessels":[vessel]}),encoding="utf-8")
            (report_dir / "2026-07-06.json").write_text(json.dumps({"date":"2026-07-06","risk_counts":{"Normal":1},"top_vessels":[]}),encoding="utf-8")
            with patch.object(reports,"ROOT",root), patch.object(reports,"DOCS_DATA",docs_data), patch.object(reports,"REPORTS",report_dir):
                daily = reports.daily_payload(date(2026,7,13))
                weekly = reports.weekly_payload(date(2026,7,14))
            self.assertEqual(len(daily["near_infrastructure"]),1)
            self.assertEqual(len(daily["identity_changes"]),1)
            self.assertEqual([item["date"] for item in weekly["risk_trend"]],["2026-07-13","2026-07-14"])
            self.assertEqual(weekly["event_type_distribution"],{"identity_change":1})
            self.assertEqual(weekly["frequent_rules"],{"ais_gap_6h":2})


if __name__ == "__main__":
    unittest.main()
