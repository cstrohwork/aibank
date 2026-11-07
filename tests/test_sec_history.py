import gzip
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import sec_history as history
from rebuild_history import choose_13f, rebuild

class HistoryTests(unittest.TestCase):
    def test_catalogue_cutoff_dedup_and_all_forms(self):
        raw = b'CIK|Company Name|Form Type|Date Filed|Filename\n1|A|4|2025-09-29|edgar/data/1/0000000001-25-000001.txt\n1|A|4|2025-09-30|edgar/data/1/0000000001-25-000002.txt\n1|A|4|2025-09-30|edgar/data/1/0000000001-25-000002.txt\n'
        rows = history.parse_master(raw, '2025-09-30')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['form'], '4')

    def test_quarter_boundary(self):
        import datetime
        self.assertEqual(list(history.quarters('2025-09-30', datetime.date(2026, 1, 1))), [(2025, 3), (2025, 4), (2026, 1)])

    def test_old_submission_pages_are_loaded(self):
        sub = {'filings': {'recent': {'accessionNumber': ['new']}, 'files': [
            {'name': 'old.json', 'filingTo': '2025-11-01'}, {'name': 'excluded.json', 'filingTo': '2024-01-01'}]}}
        calls = []
        def reader(url):
            calls.append(url)
            return b'{"accessionNumber":["old"],"form":["13F-HR"]}'
        rows = history.submission_rows(sub, reader, '2025-09-30')
        self.assertEqual({r['accessionNumber'] for r in rows}, {'new', 'old'})
        self.assertEqual(len(calls), 1)

    def version(self, accession, kind, form='13F-HR/A'):
        return {'accession': accession, 'filing_date': '2025-11-14', 'form': form,
                'amendment_type': kind, 'source': accession, 'holdings': [accession]}

    def test_restatement_replaces_and_additions_append(self):
        versions = [self.version('1', '', '13F-HR'), self.version('2', 'RESTATEMENT'), self.version('3', 'NEW HOLDINGS')]
        self.assertEqual(choose_13f(versions)['holdings'], ['2', '3'])

    def test_unknown_amendments_require_review(self):
        item = choose_13f([self.version('1', '', '13F-HR'), self.version('2', 'UNKNOWN')])
        self.assertEqual(item['holdings'], ['1'])
        self.assertTrue(item['amendment_review_required'])
        self.assertIsNone(choose_13f([self.version('2', 'NEW HOLDINGS')]))

    def test_13f_sgml_dollars_and_report_cutoff(self):
        row = {'cik': '0000000001', 'name': 'Manager', 'form': '13F-HR', 'filing_date': '2025-11-14',
               'accession': '0000000001-25-000001', 'source': 'https://www.sec.gov/test'}
        raw = b'<SEC-DOCUMENT>\n<DOCUMENT><TYPE>13F-HR\n<XML><edgarSubmission><periodOfReport>09-30-2025</periodOfReport><filingManager><name>Manager</name><address><city>Boston</city><stateOrCountry>MA</stateOrCountry></address></filingManager></edgarSubmission></XML></DOCUMENT><DOCUMENT><TYPE>INFORMATION TABLE\n<XML><informationTable><infoTable><nameOfIssuer>Issuer</nameOfIssuer><cusip>123456789</cusip><value>1000</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable></informationTable></XML></DOCUMENT>'
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            paths = history.normalize(row, raw, root, '2025-09-30')
            result = history.load(root / paths[0])
            self.assertEqual(result['holdings'][0]['value_usd'], 1000)
            self.assertEqual(result['city'], 'Boston')
            self.assertEqual(result['report_date'], '2025-09-30')
            self.assertEqual(history.normalize(row, raw, root, '2025-12-31'), [])

    def test_fund_history_does_not_sum_different_periods(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            for date, accession, amount in [('2025-09-30', '1', 100), ('2025-12-31', '2', 200), ('2025-12-31', '3', 250)]:
                record = {'series_id': 'S000000001', 'fund_name': 'Example Index Fund', 'report_date': date,
                    'registrant_cik': '0000000001', 'registrant_name': 'Trust', 'filing_date': '2026-01-0'+accession,
                    'accession': accession, 'source': accession,
                    'holdings': [{'asset_category': 'EC', 'reported_value_usd': amount, 'cusip': '123456789'}]}
                history.save(root / 'history' / 'normalized' / 'funds' / (accession+'.json.gz'), record)
            rebuild(root)
            self.assertEqual(len(history.load(root/'funds'/'history_index.json')['funds']), 2)
            self.assertEqual(len(history.load(root/'funds'/'index.json')['funds']), 1)
            firms = history.load(root/'history'/'registrants'/'2025-12-31.json')['firms']
            self.assertEqual(firms[0]['equity_assets_usd'], 250)
            self.assertEqual(firms[0]['passive_pct_of_disclosed_sample_equity_assets'], 100)
            rebuild(root)
            self.assertEqual(history.load(root/'history'/'registrants'/'2025-12-31.json')['firms'][0]['equity_assets_usd'], 250)

    def test_profile_history_equity_and_turnover(self):
        with tempfile.TemporaryDirectory() as folder:
            project = pathlib.Path(folder)
            scripts = project/'scripts'
            scripts.mkdir()
            (scripts/'build_investor_profiles.py').write_text((SCRIPTS/'build_investor_profiles.py').read_text())
            root = project/'CapitalSignal'/'data'
            entries = []
            for date, shares in [('2025-09-30', 10), ('2025-12-31', 20)]:
                data = {'manager_cik': '1', 'manager_name': 'Manager', 'report_date': date, 'source': 'SEC',
                    'holdings': [{'cusip': '123456789', 'shares': shares, 'value_thousands': shares*10, 'share_type': 'SH'},
                                 {'cusip': '987654321', 'shares': 1, 'value_thousands': 9999, 'put_call': 'CALL'}]}
                history.save(root/'13f'/(date+'.json'), data)
                entries.append({'manager_cik': '1', 'report_date': date, 'file': date+'.json'})
            history.save(root/'13f'/'index.json', {'managers': entries})
            subprocess.run([sys.executable, str(scripts/'build_investor_profiles.py')], check=True, capture_output=True)
            p = history.load(root/'history'/'investor_profiles'/'2025-09-30.json')['profiles'][0]
            self.assertEqual(p['equity_aum_usd'], 100)
            self.assertEqual(p['reported_13f_value_usd'], 10099)
            self.assertIsNone(p['annualized_turnover_proxy_pct'])
            self.assertIsNone(p['investor_style'])
            self.assertIsNone(p['active_pct_of_total_institution_equity_aum'])

if __name__ == '__main__':
    unittest.main()
