"""N-PORT report-date exclusions must precede holdings validation."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import sec_history as history


class NportCutoffTests(unittest.TestCase):
    def normalize(self, body, start='2025-09-30'):
        row = {'cik': '0000000001', 'name': 'Fixture Trust',
               'form': 'NPORT-P/A', 'filing_date': '2025-10-15',
               'accession': '0000000001-25-000001',
               'source': 'https://www.sec.gov/Archives/fixture'}
        raw = ('<SEC-DOCUMENT><DOCUMENT><TYPE>NPORT-P/A\n<XML>'
               '<edgarSubmission>' + body + '</edgarSubmission>'
               '</XML></DOCUMENT>').encode()
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            paths = history.normalize(row, raw, root, start)
            return [history.load(root / path) for path in paths]

    def test_old_zero_asset_amendment_is_excluded(self):
        # Regression shape verified against retained SEC accession
        # 0002071691-25-002515 (2025-05-31, total assets zero).
        self.assertEqual(self.normalize('<repPdDate>2025-05-31</repPdDate>'
                                       '<totAssets>0</totAssets>'), [])

    def test_old_unsupported_positions_are_not_parsed(self):
        self.assertEqual(self.normalize('<repPdDate>2025-08-31</repPdDate>'
                                       '<invstOrSec><valUSD>unknown</valUSD></invstOrSec>'), [])

    def test_missing_date_remains_an_error(self):
        with self.assertRaisesRegex(ValueError, 'Invalid/missing report date'):
            self.normalize('<totAssets>0</totAssets>')

    def test_in_scope_missing_positions_remains_an_error(self):
        with self.assertRaisesRegex(ValueError, 'No supported N-PORT positions'):
            self.normalize('<repPdDate>2025-09-30</repPdDate><totAssets>0</totAssets>')

    def test_in_scope_missing_series_remains_unknown(self):
        with self.assertRaisesRegex(ValueError, 'Missing/invalid N-PORT series identifier'):
            self.normalize('<repPdDate>2025-09-30</repPdDate><invstOrSec>'
                           '<assetCat>EC</assetCat><valUSD>100</valUSD></invstOrSec>')

    def test_cutoff_date_is_inclusive_and_keeps_source(self):
        records = self.normalize('<repPdDate>2025-09-30</repPdDate>'
                                 '<seriesId>S000000001</seriesId><invstOrSec>'
                                 '<assetCat>EC</assetCat><valUSD>100</valUSD></invstOrSec>')
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['report_date'], '2025-09-30')
        self.assertEqual(records[0]['source'], 'https://www.sec.gov/Archives/fixture')
        self.assertEqual(records[0]['accession'], '0000000001-25-000001')


if __name__ == '__main__':
    unittest.main()
