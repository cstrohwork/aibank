import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from check_capitalsignal import check


class CacheHealthTests(unittest.TestCase):
    def fixture(self, root, labelled=True):
        def write(path, data):
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(data))

        write('13f/index.json', {'managers': [{
            'manager_cik': '0000000001', 'report_date': '2026-06-30',
            'file': 'manager.json', 'holdings_count': 1}]})
        write('13f/manager.json', {'holdings': [{'value_thousands': 1}]})
        entry = {'fund_id': 'S000000001', 'series_id': 'S000000001',
                 'report_date': '2026-06-30', 'file': 'fund.json', 'holdings_count': 0}
        fund = {'holdings': [], 'reported_position_count': 0}
        if labelled:
            entry['position_coverage'] = 'sec_reported_no_investment_positions'
            fund['position_coverage'] = 'sec_reported_no_investment_positions'
        write('funds/index.json', {'funds': [entry]})
        write('funds/fund.json', fund)
        write('investor_profiles.json', {'profiles': [{'id': 'fixture'}]})
        write('fund_firms.json', {'firms': [{'id': 'fixture'}]})

    def test_source_labelled_zero_position_schedule_passes_structure_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.fixture(root)
            self.assertEqual(check(root)['status'], 'passed')

    def test_unlabelled_empty_holdings_remain_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.fixture(root, labelled=False)
            report = check(root)
            self.assertEqual(report['status'], 'failed')
            self.assertIn('fund.json: no holdings', report['errors'])
