"""Regression tests for live-source schema adapters."""
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import fetch_gfw_data
from ais_schema import iso8601_timestamp, map_ship_type
from fetch_barentswatch_ais import fetch_barentswatch_ais
from fetch_gfw_data import _convert, _flatten_entries, _geojson_region, _records_from_payload, _request_report


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


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
        payload = {"entries":[{"public-global-sar-presence:v4.0":[{"date":"2026-07-10 12:00","detections":2,"lat":59.8,"lon":24.5}]}]}
        entries = _flatten_entries(payload)
        record = _convert(entries[0], False)
        self.assertEqual(len(entries), 1)
        self.assertFalse(record["matched"])
        self.assertEqual(record["source"], "gfw_sar")
        self.assertTrue(record["detection_id"])
        self.assertEqual(_geojson_region()["type"], "MultiPolygon")
        expanded = _records_from_payload(payload,False)
        self.assertEqual(len(expanded),2)
        self.assertEqual(len({item["detection_id"] for item in expanded}),2)
        self.assertEqual(set(expanded[0]),{"detection_id","lat","lon","timestamp","matched","matched_mmsi","confidence","length_m","source"})

    def test_gfw_same_vessel_cells_keep_distinct_detections(self):
        payload={"entries":[{"dataset":[
            {"date":"2026-07-10 12:00","detections":1,"lat":59.8,"lon":24.5,"vesselId":"same"},
            {"date":"2026-07-10 13:00","detections":1,"lat":59.9,"lon":24.6,"vesselId":"same"},
        ]}]}
        records=_records_from_payload(payload,True)
        self.assertEqual(len(records),2)
        self.assertEqual(len({record["detection_id"] for record in records}),2)

    def test_gfw_baltic_bbox_includes_bornholm(self):
        rings=_geojson_region()["coordinates"]
        self.assertTrue(any(min(point[1] for point in polygon[0]) <= 55.2 <= max(point[1] for point in polygon[0]) and min(point[0] for point in polygon[0]) <= 15.9 <= max(point[0] for point in polygon[0]) for polygon in rings))

    def test_gfw_missing_token_and_permission_are_expected_mock_fallbacks(self):
        with patch.object(fetch_gfw_data,"GFW_API_TOKEN",None):
            records,status,_detail=fetch_gfw_data.fetch_gfw_sar()
        self.assertEqual(status,"credentials_missing_fallback_mock")
        self.assertTrue(records and all(record["source"]=="mock" for record in records))
        with patch.object(fetch_gfw_data,"GFW_API_TOKEN","token"), patch("fetch_gfw_data.requests.post",return_value=FakeResponse({},403)):
            records,status,_detail=fetch_gfw_data.fetch_gfw_sar()
        self.assertEqual(status,"credentials_missing_fallback_mock")
        self.assertTrue(records and all(record["source"]=="mock" for record in records))

    @patch("fetch_gfw_data.time.sleep")
    @patch("fetch_gfw_data.requests.get")
    @patch("fetch_gfw_data.requests.post")
    def test_gfw_524_recovers_last_report(self,post,get,_sleep):
        post.return_value=FakeResponse({},524)
        get.side_effect=[FakeResponse({"status":"running"}),FakeResponse({"entries":[]})]
        self.assertEqual(_request_report({},{}),{"entries":[]})

    def test_gfw_query_uses_seven_day_window(self):
        with patch.object(fetch_gfw_data,"GFW_API_TOKEN","token"), patch("fetch_gfw_data._request_report",return_value={"entries":[]}) as request:
            _records,status,_detail=fetch_gfw_data.fetch_gfw_sar()
        self.assertEqual(status,"ok")
        date_range=request.call_args_list[0].args[0]["date-range"]
        start,end=(date.fromisoformat(value) for value in date_range.split(","))
        self.assertEqual((end-start).days,7)


if __name__ == "__main__":
    unittest.main()
