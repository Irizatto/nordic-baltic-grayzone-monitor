"""Regression tests for damaged published infrastructure snapshots."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import analyze_suspicious


class LayerResilienceTests(unittest.TestCase):
    def test_scoring_skips_invalid_layer_and_uses_valid_layer(self):
        with tempfile.TemporaryDirectory() as directory:
            docs_data = Path(directory)
            layers = docs_data / "layers"
            layers.mkdir()
            (layers / "cables.geojson").write_bytes(
                b'{"type":"FeatureCollection","features":[' + b"\xdb"
            )
            pipeline = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "name": "Valid pipeline",
                            "category": "pipeline",
                            "scoring_eligible": True,
                        },
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[24.0, 60.0], [24.1, 60.1]],
                        },
                    }
                ],
            }
            (layers / "pipelines.geojson").write_text(
                json.dumps(pipeline), encoding="utf-8"
            )
            with patch.object(analyze_suspicious, "DOCS_DATA", docs_data):
                features = analyze_suspicious._layers()
            self.assertEqual(len(features), 1)
            self.assertEqual(features[0]["properties"]["name"], "Valid pipeline")


if __name__ == "__main__":
    unittest.main()

