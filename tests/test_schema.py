import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from events import HEADER

class EventSchemaTests(unittest.TestCase):
    def test_header_and_sample_row(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"events.csv"
            sample=dict(zip(HEADER,["NBGM-20260711-0001","2026-07-11","12:00:00+00:00","Gulf of Finland","59.8","24.4","Example","123","","cargo","cable_proximity","5","[]","Example cable","2.8","mock","low","Research lead only"]))
            with path.open("w",newline="",encoding="utf-8") as handle:
                writer=csv.DictWriter(handle,fieldnames=HEADER); writer.writeheader(); writer.writerow(sample)
            with path.open(newline="",encoding="utf-8") as handle:
                rows=list(csv.DictReader(handle))
            self.assertEqual(rows[0]["event_id"],"NBGM-20260711-0001")
            self.assertEqual(rows[0]["event_type"],"cable_proximity")
            self.assertEqual(list(rows[0].keys()),HEADER)

if __name__=="__main__": unittest.main()
