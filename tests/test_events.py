"""Regression tests for append-only event typing and deduplication."""
import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import events


class EventTests(unittest.TestCase):
    def test_multiple_rule_types_and_distinct_sar_detections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "data" / "reference"
            reference.mkdir(parents=True)
            (reference / "sensitive_areas.csv").write_text("name,lat_min,lat_max,lon_min,lon_max\nTest,59,61,23,25\n",encoding="utf-8")
            csv_path = root / "data" / "events" / "events.csv"
            export_path = root / "docs" / "data" / "events.json"
            static_path = root / "docs" / "data" / "events.csv"
            timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            vessel = {"mmsi":"123","imo":"456","name":"TEST","ship_type":"cargo","lat":60.0,"lon":24.0,"timestamp":timestamp,"source":"digitraffic","risk_score":11,"risk_level":"High Review Priority","nearest_infrastructure":{"name":"Cable","type":"cable","distance_km":12},"triggered_rules":[{"rule_id":"identity_change","points":3,"evidence":"changed"},{"rule_id":"sanctions_match","points":8,"evidence":"matched"}]}
            detections = [
                {"detection_id":"sar-a","lat":60.0,"lon":24.0,"timestamp":timestamp,"matched":False,"source":"mock"},
                {"detection_id":"sar-b","lat":60.1,"lon":24.1,"timestamp":timestamp,"matched":False,"source":"mock"},
            ]
            with patch.object(events,"ROOT",root), patch.object(events,"CSV_PATH",csv_path), patch.object(events,"EXPORT_PATH",export_path), patch.object(events,"STATIC_CSV",static_path):
                events.record_events([vessel],detections)
                events.record_events([vessel],detections)
            with csv_path.open(newline="",encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 4)
            self.assertEqual({row["event_type"] for row in rows},{"identity_change","sanctions_match","sar_unmatched"})
            self.assertEqual(sum(row["event_type"]=="sar_unmatched" for row in rows),2)
            self.assertEqual(len({row["event_id"] for row in rows}),4)
            sanctions = next(row for row in rows if row["event_type"]=="sanctions_match")
            self.assertEqual(sanctions["confidence"],"medium")

    def test_normal_proximity_is_skipped_but_identity_is_standalone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "data" / "reference"
            reference.mkdir(parents=True)
            (reference / "sensitive_areas.csv").write_text("name,lat_min,lat_max,lon_min,lon_max\nTest,59,61,23,25\n",encoding="utf-8")
            csv_path = root / "data" / "events" / "events.csv"
            export_path = root / "docs" / "data" / "events.json"
            static_path = root / "docs" / "data" / "events.csv"
            vessel = {"mmsi":"123","imo":"456","name":"TEST","ship_type":"cargo","lat":60.0,"lon":24.0,"timestamp":"2026-07-11T00:00:00+00:00","source":"digitraffic","risk_score":4,"risk_level":"Normal","nearest_infrastructure":{"name":"Cable","type":"cable","distance_km":0.5},"triggered_rules":[{"rule_id":"infra_proximity_1km","points":3,"evidence":"near"},{"rule_id":"identity_change","points":3,"evidence":"changed"}]}
            with patch.object(events,"ROOT",root), patch.object(events,"CSV_PATH",csv_path), patch.object(events,"EXPORT_PATH",export_path), patch.object(events,"STATIC_CSV",static_path):
                events.record_events([vessel],[])
            with csv_path.open(newline="",encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["event_type"] for row in rows],["identity_change"])

    def test_higher_score_appends_same_id_revision_and_after_24h_gets_new_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "data" / "reference"
            reference.mkdir(parents=True)
            (reference / "sensitive_areas.csv").write_text("name,lat_min,lat_max,lon_min,lon_max\nTest,59,61,23,25\n",encoding="utf-8")
            csv_path = root / "data" / "events" / "events.csv"
            export_path = root / "docs" / "data" / "events.json"
            static_path = root / "docs" / "data" / "events.csv"
            base = {"mmsi":"111","imo":"456","name":"TEST","ship_type":"cargo","lat":60.0,"lon":24.0,"source":"digitraffic","nearest_infrastructure":{"name":"","type":"","distance_km":""},"triggered_rules":[{"rule_id":"identity_change","points":3,"evidence":"changed"}]}
            first = {**base,"timestamp":"2026-07-11T00:00:00+00:00","risk_score":3,"risk_level":"Normal"}
            revision = {**base,"mmsi":"222","timestamp":"2026-07-11T01:00:00+00:00","risk_score":6,"risk_level":"Watch"}
            later = {**revision,"mmsi":"333","timestamp":"2026-07-12T02:00:00+00:00","risk_score":7}
            with patch.object(events,"ROOT",root), patch.object(events,"CSV_PATH",csv_path), patch.object(events,"EXPORT_PATH",export_path), patch.object(events,"STATIC_CSV",static_path):
                events.record_events([first],[])
                events.record_events([revision],[])
                events.record_events([later],[])
            with csv_path.open(newline="",encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows),3)
            self.assertEqual(rows[0]["event_id"],rows[1]["event_id"])
            self.assertNotEqual(rows[1]["event_id"],rows[2]["event_id"])
            exported = json.loads(export_path.read_text(encoding="utf-8"))["events"]
            self.assertEqual(len(exported),2)
            self.assertEqual(max(int(row["risk_score"]) for row in exported),7)


if __name__ == "__main__":
    unittest.main()
