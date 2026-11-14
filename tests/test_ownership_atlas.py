import pathlib
import sys
import tempfile
import unittest
import json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from build_ownership_atlas import publish


class AtlasPublicationTests(unittest.TestCase):
    def test_exact_periods_separate_lenses_and_source_evidence(self):
        a = {'entity_id': '1', 'report_date': '2026-09-30', 'selected_accessions': ['original'],
             'versions': [{'accession': 'original', 'source': 'https://www.sec.gov/example'}],
             'reported_matched_identifier_equity_value_usd': 100, 'security_count': 2}
        source = {'updated_at': '2026-11-14T12:00:00Z', 'managers': [a, dict(a, report_date='2026-06-30')],
                  'funds': [dict(a, entity_id='S1')], 'blocked_selections': [
                      {'view': 'funds', 'report_date': '2026-09-30', 'reason': 'unknown amendment'}]}
        with tempfile.TemporaryDirectory() as folder:
            manifest = publish(source, folder)
            self.assertEqual(len(manifest['lenses']['managers']), 2)
            self.assertEqual(manifest['lenses']['funds'][0]['count'], 1)
            report = json.loads((pathlib.Path(folder)/'managers-2026-09-30.json').read_text())
            self.assertEqual(report['managers'][0]['versions'], a['versions'])
            self.assertEqual(report['blocked_selections'], [])
            self.assertNotIn('combined_value_usd', manifest)

    def test_invalid_date_cannot_escape_output_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                publish({'updated_at': 'x', 'managers': [{'report_date': '../escape'}], 'funds': []}, folder)
