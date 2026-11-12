import pathlib
import tempfile
import unittest
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from fund_ownership_index import write_ownership_index
from sec_history import load, select_download_queue


class OwnershipShardTests(unittest.TestCase):
    def test_manifest_and_shards_preserve_all_positions(self):
        securities = {'123456789': [{'value_usd': 10}], '123456780': [{'value_usd': 20}],
                      '987654321': [{'value_usd': 30}]}
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            write_ownership_index(root, securities, 'source evidence')
            manifest = load(root / 'ownership_by_cusip.json')
            self.assertEqual(manifest['security_count'], 3)
            restored = {}
            for shard in manifest['shards']:
                restored.update(load(root / shard['file'])['securities'])
            self.assertEqual(restored, securities)
            self.assertEqual(len(manifest['shards']), 2)
            self.assertLess((root / 'ownership_by_cusip.json').stat().st_size, 1000)

    def test_requested_quarter_sequence(self):
        rows = [dict(accession=str(i), form='13F-HR', filing_date=date) for i, date in
                enumerate(['2026-11-12', '2026-08-14', '2025-11-14', '2026-02-14', '2026-05-14'])]
        state = {}
        for target, row in zip(['2026-09-30', '2026-06-30', '2025-09-30', '2025-12-31', '2026-03-31'], rows):
            available = [r for r in rows if r['accession'] not in state]
            queue, plan = select_download_queue(rows, state, available, 10)
            self.assertEqual(plan['active_target_report_date'], target)
            self.assertEqual(queue, [row])
            state[row['accession']] = {'status': 'archived'}
