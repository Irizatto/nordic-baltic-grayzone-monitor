"""Regression tests for fallback retention and publish size controls."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import generate_dashboard_data as pipeline


def vessel(mmsi, source, score=0, level="Normal"):
    return {"mmsi":str(mmsi),"imo":None,"name":"TEST","callsign":None,"flag":None,"ship_type":"cargo","lat":60.0,"lon":24.0,"speed":10.0,"course":0.0,"heading":0.0,"timestamp":"2026-07-11T00:00:00+00:00","source":source,"risk_score":score,"risk_level":level,"triggered_rules":[],"nearest_infrastructure":{"name":"x","type":"cable","distance_km":20}}


class PipelineTests(unittest.TestCase):
    def test_source_error_reuses_previous_real_records_and_sar(self):
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory) / "docs" / "data"
            docs.mkdir(parents=True)
            old_sar = {"detection_id":"old","lat":60.0,"lon":24.0,"timestamp":"2026-07-11T00:00:00+00:00","matched":False,"matched_mmsi":None,"confidence":0.5,"length_m":None,"source":"gfw_sar"}
            previous = {"metadata":{},"vessels":[vessel(1,"digitraffic"),vessel(2,"mock"),vessel(3,"barentswatch")],"sar_detections":[old_sar]}
            (docs / "data.json").write_text(json.dumps(previous),encoding="utf-8")
            (docs / "metadata.json").write_text(json.dumps({"source_status":{}}),encoding="utf-8")
            shared_features = [{"test": "shared"}]
            seen_features = []
            def scorer(item, *_args, **kwargs):
                seen_features.append(kwargs.get("features"))
                return {**item,"risk_score":0,"risk_level":"Normal","triggered_rules":[],"nearest_infrastructure":{"name":"x","type":"cable","distance_km":20}}
            with patch.object(pipeline,"DOCS_DATA",docs), patch.object(pipeline,"USE_MOCK_DATA",False), patch.object(pipeline,"fetch_digitraffic_ais",side_effect=requests.RequestException("offline")), patch.object(pipeline,"fetch_barentswatch_ais",return_value=None), patch.object(pipeline,"fetch_gfw_sar",return_value=([{"detection_id":"new-mock","lat":0,"lon":0,"timestamp":"2026-07-11T00:00:00Z","matched":False,"source":"mock"}],"error_kept_old_data","offline")), patch.object(pipeline,"update_history",return_value={}), patch.object(pipeline,"load_infrastructure_features",return_value=shared_features) as loader, patch.object(pipeline,"score_vessel",side_effect=scorer), patch.object(pipeline,"record_events"), patch.object(pipeline,"write_digitraffic"), patch.object(pipeline,"write_barentswatch"), patch.object(pipeline,"write_gfw_sar"):
                result = pipeline.run()
            by_source = {item["source"] for item in result["vessels"]}
            self.assertIn("digitraffic", by_source)
            self.assertIn("mock", by_source)
            self.assertNotIn("barentswatch", by_source)
            self.assertEqual(result["sar_detections"], [old_sar])
            self.assertEqual(result["metadata"]["source_status"]["digitraffic"]["records_reused"], 1)
            loader.assert_called_once_with()
            self.assertTrue(seen_features)
            self.assertTrue(all(features is shared_features for features in seen_features))

    def test_publish_cap_keeps_all_priorities(self):
        normal = [vessel(index,"digitraffic",score=index) for index in range(200)]
        self.assertEqual(len(pipeline._cap_vessels(normal)), 150)
        priority = [vessel(index,"digitraffic",score=12,level="Critical Review Priority") for index in range(151)]
        self.assertEqual(len(pipeline._cap_vessels(priority+normal)), 151)


if __name__ == "__main__":
    unittest.main()
