"""Regression tests for history deduplication and distance boundaries."""
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analyze_suspicious import score_vessel, update_history


class HistoryTests(unittest.TestCase):
    def test_identical_snapshot_is_not_appended_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.jsonl"
            now = datetime(2026,7,15,tzinfo=timezone.utc)
            vessel = {"mmsi":"123","timestamp":now.isoformat(),"source":"digitraffic"}
            update_history([vessel],path,now)
            grouped = update_history([vessel],path,now)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()),1)
            self.assertEqual(grouped,{})

    @patch("analyze_suspicious.point_to_linestring_distance_km", return_value=1.04)
    def test_proximity_band_uses_unrounded_distance(self, _distance):
        feature = [{"properties":{"name":"Cable","category":"cable"},"geometry":{"coordinates":[[24,60],[25,60]]}}]
        vessel = {"mmsi":"123","imo":None,"name":"TEST","callsign":None,"flag":None,"ship_type":"cargo","lat":60.0,"lon":24.0,"speed":10,"course":0,"heading":0,"timestamp":"2026-07-15T00:00:00+00:00"}
        result = score_vessel(vessel,features=feature,watchlist=[])
        self.assertEqual([rule["rule_id"] for rule in result["triggered_rules"]],["infra_proximity_5km"])


if __name__ == "__main__":
    unittest.main()
