"""Unit tests for the live EMODnet adapter and its keep-old-data fallback."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import fetch_emodnet_layers as emodnet


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class StaticSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


class FailingSession:
    def get(self, *_args, **_kwargs):
        raise requests.ConnectionError("offline for test")


class EmodnetLayerTests(unittest.TestCase):
    def test_invalid_utf8_snapshot_is_treated_as_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "truncated.geojson"
            path.write_bytes(b'{"type":"FeatureCollection","features":[' + b"\xdb")
            self.assertIsNone(emodnet._read_json(path, None))

    def test_multilines_are_exploded_into_unified_schema(self):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "pipelines.7",
                    "properties": {"name": "Test route", "status": "Operational"},
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [
                            [[24.0, 60.0], [24.1, 60.1]],
                            [[24.1, 60.1], [24.2, 60.2]],
                        ],
                    },
                }
            ],
        }
        session = StaticSession(payload)
        retrieved = datetime(2026, 7, 15, tzinfo=timezone.utc)
        features = emodnet._fetch_type(
            session,
            "emodnet:pipelines",
            "pipeline",
            retrieved,
            bboxes=[("test", (20.0, 55.0, 30.0, 65.0))],
        )
        self.assertEqual(len(features), 2)
        for feature in features:
            self.assertEqual(feature["geometry"]["type"], "LineString")
            properties = feature["properties"]
            self.assertEqual(properties["category"], "pipeline")
            self.assertEqual(properties["source"], "emodnet_human_activities")
            self.assertEqual(properties["route_precision"], "published_open_data")
            self.assertEqual(properties["last_updated"], "2026-07-15")
            self.assertTrue(properties["scoring_eligible"])
        self.assertEqual(session.calls[0][1]["params"]["typeNames"], "emodnet:pipelines")
        self.assertEqual(session.calls[0][1]["headers"]["User-Agent"], "NBGM-research/1.0")

    def test_non_operational_route_is_visible_but_not_scoring_eligible(self):
        feature = {
            "type": "Feature",
            "id": "cable.1",
            "properties": {"name": "Planned cable", "status": "Planned"},
            "geometry": {"type": "LineString", "coordinates": [[10, 60], [11, 61]]},
        }
        normalised = emodnet._normalise_feature(
            feature,
            feature["geometry"],
            "cable",
            "emodnet:test",
            datetime(2026, 7, 15, tzinfo=timezone.utc),
            1,
        )
        self.assertFalse(normalised["properties"]["scoring_eligible"])
        feature["properties"]["status"] = "Application submitted"
        normalised = emodnet._normalise_feature(
            feature,
            feature["geometry"],
            "cable",
            "emodnet:test",
            datetime(2026, 7, 15, tzinfo=timezone.utc),
            1,
        )
        self.assertFalse(normalised["properties"]["scoring_eligible"])

    def test_network_failure_keeps_every_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layers = root / "layers"
            layers.mkdir()
            original = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Existing", "source": "manual_schematic"},
                        "geometry": {"type": "Point", "coordinates": [24, 60]},
                    }
                ],
            }
            before = json.dumps(original, indent=2)
            for layer_name in emodnet.LAYER_SPECS:
                (layers / f"{layer_name}.geojson").write_text(before, encoding="utf-8")
            metadata_path = root / "infrastructure_metadata.json"
            with (
                patch.object(emodnet, "LAYERS_DIR", layers),
                patch.object(emodnet, "INFRASTRUCTURE_METADATA_PATH", metadata_path),
                patch.object(emodnet, "RAW_ARCHIVE_DIR", root / "raw"),
                patch.object(emodnet.requests, "Session", return_value=FailingSession()),
                patch.object(emodnet.time, "sleep", return_value=None),
            ):
                result = emodnet.run(force=True)
            self.assertEqual(result["status"], "error_kept_old_data")
            for layer_name in emodnet.LAYER_SPECS:
                self.assertEqual((layers / f"{layer_name}.geojson").read_text(encoding="utf-8"), before)
            self.assertTrue(result["fallbacks"])


if __name__ == "__main__":
    unittest.main()

