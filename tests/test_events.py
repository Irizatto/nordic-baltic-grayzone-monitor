"""Regression tests for append-only event typing and deduplication."""
import csv
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


if __name__ == "__main__":
    unittest.main()
