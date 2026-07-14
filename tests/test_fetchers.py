"""Regression tests for live-source schema adapters."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ais_schema import iso8601_timestamp, map_ship_type
from fetch_barentswatch_ais import fetch_barentswatch_ais
from fetch_gfw_data import _convert, _flatten_entries, _geojson_region


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FetcherTests(unittest.TestCase):
    def test_conservative_ship_type_mapping(self):
        expected = {30:"fishing",35:"naval",36:"unknown",37:"unknown",52:"tug",55:"law_enforcement",70:"cargo",80:"tanker"}
        self.assertEqual({code:map_ship_type(code) for code in expected}, expected)

    def test_timestamp_accepts_milliseconds_and_iso(self):
        instant = datetime(2026, 7, 11, tzinfo=timezone.utc)
        self.assertEqual(iso8601_timestamp(instant.timestamp()*1000), instant.isoformat())
        self.assertEqual(iso8601_timestamp("2026-07-11T03:00:00+03:00"), instant.isoformat())

    @patch("fetch_barentswatch_ais._request")
    @patch("fetch_barentswatch_ais._token", return_value="token")
    def test_barentswatch_official_fields_and_local_bbox(self, _token, request):
        request.return_value = FakeResponse([
            {"mmsi":257076860,"name":"ODD LUNDBERG","msgtime":"2026-07-11T13:18:26+00:00","speedOverGround":4.2,"courseOverGround":213.8,"shipType":30,"trueHeading":315,"callSign":"LFUO","imoNumber":9840051,"latitude":70.1,"longitude":22.5},
            {"mmsi":111,"latitude":60.0,"longitude":10.0},
            {"mmsi":None,"latitude":70.0,"longitude":20.0},
        ])
        records = fetch_barentswatch_ais()
        self.assertEqual(len(records), 1)
        vessel = records[0]
        self.assertEqual(vessel["mmsi"], "257076860")
        self.assertEqual(vessel["imo"], "9840051")
        self.assertEqual(vessel["callsign"], "LFUO")
        self.assertEqual(vessel["speed"], 4.2)
        self.assertEqual(vessel["course"], 213.8)
        self.assertEqual(vessel["heading"], 315.0)
        self.assertEqual(vessel["ship_type"], "fishing")

    def test_gfw_report_shape_conversion(self):
        payload = {"entries":[{"public-global-sar-presence:v4.0":[{"date":"2026-07-10 12:00","detections":1,"lat":59.8,"lon":24.5}]}]}
        entries = _flatten_entries(payload)
        record = _convert(entries[0], False)
        self.assertEqual(len(entries), 1)
        self.assertFalse(record["matched"])
        self.assertEqual(record["source"], "gfw_sar")
        self.assertTrue(record["detection_id"])
        self.assertEqual(_geojson_region()["type"], "MultiPolygon")


if __name__ == "__main__":
    unittest.main()
