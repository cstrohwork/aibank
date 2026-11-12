import datetime as dt
import gzip
import json
import pathlib
import sys
import tempfile
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from ingest_sp1500_fundamentals import TAGS
from intelligence_health import age_hours, build_events, build_health, file_exists

NOW = dt.datetime(2026, 11, 12, tzinfo=dt.timezone.utc)


def write(root, path, value):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value).encode()
    p.write_bytes(gzip.compress(raw) if p.suffix == '.gz' else raw)


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        write(self.root, 'fundamentals/status.json', {'updated_at': NOW.isoformat(), 'status': 'complete', 'ingested_issuers': 1})
        write(self.root, 'fundamentals/universe.json', {'as_of': '2026-11-10', 'securities': [{'cik': '0000000001', 'ticker': 'A'}]})
        write(self.root, 'history/status.json', {'updated_at': NOW.isoformat(), 'status': 'complete', 'pending_filings': 0})
        write(self.root, 'history/archive_state.json.gz', {})
        write(self.root, 'fundamentals/benchmark_status.json', {'historical_benchmark_status': 'complete', 'style_calculation_status': 'complete'})
        write(self.root, '13f/index.json', {'managers': []})
        write(self.root, 'funds/index.json', {'funds': []})

    def tearDown(self):
        self.tmp.cleanup()

    def facts(self, timestamp=None, income=True):
        fields = {
            'revenue': [{'start': '2025-01-01', 'end': '2025-12-31', 'filed': '2026-02-01', 'unit': 'USD', 'val': 100}],
            'shares_outstanding': [{'end': '2026-09-30', 'filed': '2026-11-01', 'unit': 'shares', 'val': 10}],
        }
        if income:
            fields['net_income'] = [{'start': '2025-01-01', 'end': '2025-12-31', 'filed': '2026-02-01', 'unit': 'USD', 'val': 10}]
        for field, points in fields.items():
            for point in points:
                point['tag'] = TAGS[field][0]
        write(self.root, 'fundamentals/companyfacts/0000000001.json.gz', {'cik': '0000000001', 'fields': fields, 'retrieved_at': timestamp or NOW.isoformat()})

    def test_success_status_cannot_substitute_for_actual_cache(self):
        health, _ = build_health(self.root, NOW)
        self.assertFalse(health['readiness']['fundamentals_ingestion_complete'])
        self.assertFalse(health['readiness']['model_ready'])
        self.assertFalse(health['fundamentals']['reported_count_matches_cache'])

    def test_complete_facts_open_only_model_gate(self):
        self.facts()
        write(self.root, 'history/status.json', {'updated_at': NOW.isoformat(), 'status': 'in_progress', 'pending_filings': 500})
        health, _ = build_health(self.root, NOW)
        self.assertFalse(health['readiness']['model_ready'])
        self.assertTrue(health['readiness']['fundamentals_ingestion_complete'])
        self.assertFalse(health['readiness']['production_style_ready'])

    def test_complete_cache_with_missing_income_does_not_enable_model(self):
        self.facts(income=False)
        health, _ = build_health(self.root, NOW)
        self.assertTrue(health['readiness']['fundamentals_ingestion_complete'])
        self.assertFalse(health['readiness']['model_ready'])
        self.assertEqual(health['readiness']['model_missing_field_issuers']['net_income'], 1)

    def test_stale_and_future_timestamps_do_not_pass(self):
        for stamp in ['2026-11-01T00:00:00+00:00', '2026-11-13T00:00:00+00:00']:
            self.facts(timestamp=stamp)
            health, _ = build_health(self.root, NOW)
            self.assertFalse(health['readiness']['model_ready'])

    def test_events_metadata_only_deduplicated_bounded(self):
        rows = [{'accession': str(i), 'form': 'SCHEDULE 13D', 'filing_date': '2026-11-10', 'cik': '1', 'source': 'https://www.sec.gov/x'} for i in range(4)]
        rows += [rows[0], {'accession': 'future', 'form': '4', 'filing_date': '2026-12-01'}]
        write(self.root, 'history/catalogue/a.json.gz', rows)
        events = build_events(self.root, {}, NOW, limit=2)
        self.assertEqual(len(events['events']), 2)
        self.assertEqual(events['streams']['beneficial_ownership_13d']['catalogued_filings'], 4)
        self.assertEqual(events['streams']['insider_disclosure']['future_or_missing_filing_date'], 1)
        self.assertIsNone(events['events'][0]['activist_intent'])
        self.assertEqual(events['events'][0]['evidence_level'], 'filing_metadata_only')

    def test_missing_cached_filing_and_path_traversal_flagged(self):
        write(self.root, '13f/index.json', {'managers': [{'file': '../../outside.json', 'report_date': '2026-09-30'}]})
        health, _ = build_health(self.root, NOW)
        self.assertEqual(health['ownership']['13f']['cached_snapshots'], 0)
        self.assertFalse(file_exists(self.root, '../outside'))

    def test_pipeline_in_progress_not_circular_blocker(self):
        self.facts()
        write(self.root, 'intelligence/pipeline_status.json', {'status': 'running'})
        health, _ = build_health(self.root, NOW)
        self.assertNotIn('previous_pipeline_failed', health['blocking_reasons'])
        self.assertFalse(health['readiness']['model_ready'])

    def test_canonical_model_gate_is_observed(self):
        write(self.root, 'fundamentals/model_status.json', {'activation': {'ready': True}})
        health, _ = build_health(self.root, NOW)
        self.assertTrue(health['readiness']['model_ready'])
        self.assertTrue(health['readiness']['model_status_observed'])

    def test_age_requires_timezone(self):
        self.assertIsNone(age_hours('2026-11-12', NOW))
        self.assertEqual(age_hours(NOW.isoformat(), NOW), 0)


if __name__ == '__main__':
    unittest.main()
