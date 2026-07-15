"""Synthetic unit tests for explainable scoring v1."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ais_schema import map_ship_type
from analyze_suspicious import risk_level_for_score, score_vessel

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
        expected={"tanker":11,"cargo":11,"LNG":11,"tug":9,"research":9,"service":9,"fishing":4,"unknown":7}
        actual={ship_type:score_vessel(vessel(ship_type=ship_type),features=FEATURES,watchlist=rows)["risk_score"] for ship_type in expected}
        self.assertEqual(actual,expected)
        self.assertEqual(map_ship_type("LNG carrier"),"tanker")

    @patch("analyze_suspicious._sensitive_bboxes", return_value=[])
    def test_two_hour_low_speed_rule_and_watch_threshold(self, _):
        prior=[vessel(timestamp="2026-07-10T21:00:00+00:00",speed=2)]
        result=score_vessel(vessel(speed=2),prior,[],FEATURES,[])
        self.assertIn("low_speed_near_infra_2h", ids(result))
        self.assertEqual(result["risk_score"],5)
        self.assertEqual(result["risk_level"],"Watch")

    def test_naval_and_law_enforcement_are_never_auto_scored(self):
        for ship_type in ("naval","law_enforcement"):
            result=score_vessel(vessel(ship_type=ship_type,suspected_sts_rendezvous=True),features=FEATURES,watchlist=[{"name":"TEST","imo":"","mmsi":"","source":"sanctions"}])
            self.assertEqual(result["risk_score"],0)
            self.assertEqual(result["triggered_rules"],[])

    def test_level_thresholds(self):
        expected={0:"Normal",4:"Normal",5:"Watch",7:"Watch",8:"High Review Priority",11:"High Review Priority",12:"Critical Review Priority",99:"Critical Review Priority"}
        self.assertEqual({score:risk_level_for_score(score) for score in expected},expected)

    def test_duplicate_watchlist_rows_do_not_multiply_one_rule(self):
        rows=[{"name":"TEST","imo":"","mmsi":"","source":"sanctions"},{"name":"TEST","imo":"","mmsi":"","source":"sanctions"}]
        result=score_vessel(vessel(),features=FEATURES,watchlist=rows)
        self.assertEqual([rule["rule_id"] for rule in result["triggered_rules"]].count("sanctions_match"),1)
        self.assertEqual(result["risk_score"],11)

    def test_every_stable_rule_id_has_exact_points(self):
        results=[
            score_vessel(vessel(),features=FEATURES,watchlist=[]),
            score_vessel(vessel(lat=60.03),features=FEATURES,watchlist=[]),
            score_vessel(vessel(lat=60.07),features=FEATURES,watchlist=[]),
            score_vessel(vessel(suspected_sts_rendezvous=True),features=FEATURES,watchlist=[{"name":"TEST","imo":"","mmsi":"","source":"sanctions"},{"name":"TEST","imo":"","mmsi":"","source":"shadow_fleet"}]),
        ]
        with patch("analyze_suspicious._sensitive_bboxes",return_value=[(59.9,60.1,23.9,24.3)]):
            history=[vessel(timestamp="2026-07-10T00:00:00+00:00",speed=2,course=0),vessel(timestamp="2026-07-10T03:00:00+00:00",speed=2,course=100),vessel(timestamp="2026-07-10T06:00:00+00:00",speed=2,course=200),vessel(timestamp="2026-07-10T09:00:00+00:00",speed=2,course=300)]
            results.append(score_vessel(vessel(speed=2,course=40),history,[],FEATURES,[]))
        with patch("analyze_suspicious._sensitive_bboxes",return_value=[]):
            results.append(score_vessel(vessel(speed=2),[vessel(timestamp="2026-07-10T21:00:00+00:00",speed=2)],[],FEATURES,[]))
            results.append(score_vessel(vessel(),[vessel(name="OLD",timestamp="2026-07-09T00:00:00+00:00")],[{"lat":60.0,"lon":24.0,"timestamp":"2026-07-10T23:00:00+00:00","matched":False}],FEATURES,[]))
        points={rule["rule_id"]:rule["points"] for result in results for rule in result["triggered_rules"]}
        self.assertEqual(points,{
            "infra_proximity_10km":1,"infra_proximity_5km":2,"infra_proximity_1km":3,
            "low_speed_near_infra_2h":2,"low_speed_near_infra_6h":4,
            "ais_gap_6h":2,"ais_gap_18h":4,"zigzag_or_anchor_drag_proxy":2,
            "identity_change":3,"sanctions_match":8,"shadow_fleet_match":5,
            "sts_rendezvous":4,"repeat_sensitive_area_presence":2,"sar_unmatched_near_ais_gap":5,
        })

if __name__ == "__main__":
    unittest.main()
