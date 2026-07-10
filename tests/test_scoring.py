"""Synthetic unit tests for explainable scoring v1."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analyze_suspicious import score_vessel

NOW = "2026-07-11T00:00:00+00:00"
FEATURES = [{"properties":{"name":"Test cable","category":"cable"},"geometry":{"coordinates":[[24.0,60.0],[24.2,60.0]]}}]

def vessel(**extra):
    base={"mmsi":"123","imo":None,"name":"TEST","callsign":"TST","flag":"FI","ship_type":"cargo","lat":60.0,"lon":24.0,"speed":10,"course":0,"heading":0,"timestamp":NOW}
    base.update(extra); return base

def ids(result): return {rule["rule_id"] for rule in result["triggered_rules"]}

class ScoringTests(unittest.TestCase):
    def test_proximity_bands_are_exclusive(self):
        near=score_vessel(vessel(),features=FEATURES,watchlist=[])
        mid=score_vessel(vessel(lat=60.03),features=FEATURES,watchlist=[])
        far=score_vessel(vessel(lat=60.07),features=FEATURES,watchlist=[])
        self.assertEqual(ids(near),{"infra_proximity_1km"})
        self.assertEqual(ids(mid),{"infra_proximity_5km"})
        self.assertEqual(ids(far),{"infra_proximity_10km"})

    @patch("analyze_suspicious._sensitive_bboxes", return_value=[(59.9,60.1,23.9,24.3)])
    def test_history_rules(self, _):
        previous=[vessel(timestamp="2026-07-10T00:00:00+00:00",speed=2,course=0),vessel(timestamp="2026-07-10T03:00:00+00:00",speed=2,course=100),vessel(timestamp="2026-07-10T06:00:00+00:00",speed=2,course=200),vessel(timestamp="2026-07-10T09:00:00+00:00",speed=2,course=300)]
        result=score_vessel(vessel(timestamp="2026-07-11T00:00:00+00:00",speed=2,course=40),previous,[],FEATURES,[])
        self.assertTrue({"low_speed_near_infra_6h","ais_gap_6h","zigzag_or_anchor_drag_proxy","repeat_sensitive_area_presence"} <= ids(result))

    @patch("analyze_suspicious._sensitive_bboxes", return_value=[])
    def test_identity_and_sar_gap_rules(self, _):
        prior=[vessel(name="OLD",timestamp="2026-07-09T00:00:00+00:00")]
        sar=[{"lat":60.0,"lon":24.0,"timestamp":"2026-07-10T23:00:00+00:00","matched":False}]
        result=score_vessel(vessel(),prior,sar,FEATURES,[])
        self.assertTrue({"ais_gap_18h","identity_change","sar_unmatched_near_ais_gap"} <= ids(result))

    def test_watchlist_and_sts_rules(self):
        rows=[{"name":"TEST","imo":"","mmsi":"","source":"sanctions"},{"name":"TEST","imo":"","mmsi":"","source":"shadow_fleet"}]
        result=score_vessel(vessel(suspected_sts_rendezvous=True),features=FEATURES,watchlist=rows)
        self.assertTrue({"sanctions_match","shadow_fleet_match","sts_rendezvous"} <= ids(result))

    def test_multipliers_and_levels(self):
        rows=[{"name":"TEST","imo":"","mmsi":"","source":"sanctions"}]
        fishing=score_vessel(vessel(ship_type="fishing"),features=FEATURES,watchlist=rows)
        cargo=score_vessel(vessel(ship_type="cargo"),features=FEATURES,watchlist=rows)
        self.assertEqual(fishing["risk_score"],4)
        self.assertEqual(cargo["risk_score"],11)
        self.assertEqual(cargo["risk_level"],"High Review Priority")

    def test_naval_is_never_auto_scored(self):
        result=score_vessel(vessel(ship_type="naval",suspected_sts_rendezvous=True),features=FEATURES,watchlist=[{"name":"TEST","imo":"","mmsi":"","source":"sanctions"}])
        self.assertEqual(result["risk_score"],0)
        self.assertEqual(result["triggered_rules"],[])

    def test_level_thresholds(self):
        rows=[{"name":"TEST","imo":"","mmsi":"","source":"sanctions"},{"name":"TEST","imo":"","mmsi":"","source":"shadow_fleet"}]
        result=score_vessel(vessel(suspected_sts_rendezvous=True),features=FEATURES,watchlist=rows)
        self.assertEqual(result["risk_score"],20)
        self.assertEqual(result["risk_level"],"Critical Review Priority")

if __name__ == "__main__":
    unittest.main()
