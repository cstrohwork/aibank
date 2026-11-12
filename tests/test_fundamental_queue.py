import datetime as dt
import gzip
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from ingest_sp1500_fundamentals import work_queue

class FundamentalQueueTests(unittest.TestCase):
    def test_missing_precedes_stale_and_fresh_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for cik, age in [('1', 48), ('2', 1)]:
                record = {'cik': cik, 'fields': {}, 'retrieved_at': (dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=age)).isoformat()}
                (root/(cik+'.json.gz')).write_bytes(gzip.compress(json.dumps(record).encode()))
            self.assertEqual(work_queue(['1','2','3'], root, 24), ['3','1'])

    def test_corrupt_wrong_identity_and_unknown_timestamp_are_reacquired(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root/'1.json.gz').write_bytes(b'broken')
            for cik, record in [('2', {'cik':'wrong','fields':{}}), ('3', {'cik':'3','fields':{},'retrieved_at':'2026-01-01'})]:
                (root/(cik+'.json.gz')).write_bytes(gzip.compress(json.dumps(record).encode()))
            self.assertEqual(work_queue(['1','2','3'], root, 24), ['1','2','3'])
