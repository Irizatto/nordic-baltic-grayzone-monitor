"""Tests for the public HELCOM MADS adapter."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import fetch_helcom_layers as helcom


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


def sample_payload():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "OBJECTID": 7,
                    "Name": "Test MPA",
                    "MPA_ID": "DK-7",
                    "Country": "DK",
                    "MPA_status": "Designated and managed",
                    "Year_est": "2009",
                    "Site_link": "https://example.invalid/mpa/7",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[12.0, 55.0], [12.1, 55.0], [12.1, 55.1], [12.0, 55.0]]],
                },
            }
        ],
    }


class HelcomLayerTests(unittest.TestCase):
    def test_request_and_schema_are_public_and_unscored(self):
        session = StaticSession(sample_payload())
        payload = helcom._request_geojson(session)
        feature = helcom._normalise_feature(
            payload["features"][0], datetime(2026, 7, 16, tzinfo=timezone.utc)
        )
        self.assertEqual(feature["properties"]["source"], "helcom_mads")
        self.assertEqual(feature["properties"]["category"], "protected_area")
        self.assertFalse(feature["properties"]["scoring_eligible"])
        self.assertEqual(feature["properties"]["established_year"], 2009)
        self.assertEqual(session.calls[0][1]["headers"]["User-Agent"], "NBGM-research/1.0")
        self.assertNotIn("token", session.calls[0][1]["params"])

    def test_network_failure_keeps_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layer_path = root / "helcom_mpas.geojson"
            metadata_path = root / "helcom_metadata.json"
            previous = sample_payload()
            before = json.dumps(previous)
            layer_path.write_text(before, encoding="utf-8")
            with (
                patch.object(helcom, "LAYER_PATH", layer_path),
                patch.object(helcom, "METADATA_PATH", metadata_path),
                patch.object(helcom, "RAW_ARCHIVE_DIR", root / "raw"),
                patch.object(helcom.time, "sleep", return_value=None),
            ):
                result = helcom.run(FailingSession())
            self.assertEqual(result["status"], "error_kept_old_data")
            self.assertEqual(layer_path.read_text(encoding="utf-8"), before)
            self.assertEqual(result["records_published"], 1)


if __name__ == "__main__":
    unittest.main()
