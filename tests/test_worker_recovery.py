"""Recover transient service failures without changing SEC identities or periods."""
import contextlib
import hashlib
import io
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import sec_history as history
from rebuild_history import rebuild
from refresh_funds import parse


class RecoveryTests(unittest.TestCase):
    def test_short_deadline_does_not_exceed_retry_budget(self):
        req = history.urllib.request.Request('https://www.sec.gov/Archives/test')
        error = urllib.error.HTTPError(req.full_url, 503, 'Unavailable', {}, None)
        with mock.patch.object(history.urllib.request, 'urlopen', side_effect=error) as opened, \
             mock.patch.object(history.time, 'sleep'), \
             mock.patch.object(history.time, 'monotonic', return_value=100):
            with self.assertRaises(urllib.error.HTTPError):
                history.open_sec(req, deadline=160)
        self.assertEqual(opened.call_count, 1)

    def test_batch_limit_defers_and_stops_without_marking_source_failed(self):
        rows = [dict(cik='0000000001', name='Fixture', form='8-K', filing_date='2025-09-30',
                     accession=str(i), source='https://www.sec.gov/Archives/' + str(i)) for i in range(3)]
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            with mock.patch.object(history, 'catalogue', return_value=(rows, [])), \
                 mock.patch.object(history, 'archive_submission', side_effect=[
                     dict(sha256='fixture', raw_bytes=1, archive_bytes=1),
                     history.BatchBudgetExceeded('SEC submission exceeds remaining compressed archive budget')]) as archive, \
                 mock.patch.dict('os.environ', {'SEC_HISTORY_WORKERS': '1', 'SEC_HISTORY_BATCH': '3'}), \
                 contextlib.redirect_stdout(io.StringIO()):
                history.run(root)
            state = history.load(root / 'history/archive_state.json.gz')
            self.assertEqual(archive.call_count, 2)
            self.assertEqual(state['0']['status'], 'archived')
            self.assertEqual(state['1']['status'], 'deferred')
            self.assertNotIn('retry_after', state['1'])
            self.assertNotIn('2', state)
            status = history.load(root / 'history/status.json')
            self.assertEqual(status['download_failures'], 0)
            self.assertEqual(status['deferred_filings'], 1)
            self.assertEqual(status['batch_deferral']['accession'], '1')

    def test_old_capacity_failures_are_resumable_with_evidence_preserved(self):
        row = dict(cik='0000000001', name='Fixture', form='8-K', filing_date='2025-09-30',
                   accession='0', source='https://www.sec.gov/Archives/0')
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = root / 'history/archive_state.json.gz'
            history.save(path, {'0': dict(row, status='failed', error='SEC submission exceeded batch time budget', retry_after='2999-01-01')})
            with mock.patch.object(history, 'catalogue', return_value=([row], [])), \
                 mock.patch.object(history, 'archive_submission', side_effect=history.BatchBudgetExceeded('SEC submission exceeded batch time budget')) as archive, \
                 contextlib.redirect_stdout(io.StringIO()):
                history.run(root)
            self.assertEqual(archive.call_count, 1)
            result = history.load(path)['0']
            self.assertEqual(result['status'], 'deferred')
            self.assertNotIn('retry_after', result)
            self.assertEqual(result['prior_failure']['retry_after'], '2999-01-01')

    def test_transient_503_recovers_original_and_checksum(self):
        url = 'https://www.sec.gov/Archives/test'
        raw = b'<SEC-DOCUMENT>complete original after brief outage'
        response = io.BytesIO(raw)
        response.headers = {'Content-Length': str(len(raw))}
        errors = [urllib.error.HTTPError(url, 503, 'Unavailable', {}, None) for _ in range(2)]
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(history.urllib.request, 'urlopen', side_effect=errors + [response]) as opened, \
             mock.patch.object(history.time, 'sleep') as sleep, \
             contextlib.redirect_stdout(io.StringIO()):
            path = pathlib.Path(directory) / 'source.gz'
            meta = history.archive_submission(url, path, 10000)
            self.assertEqual(meta['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(opened.call_count, 3)
            self.assertIn(mock.call(15), sleep.call_args_list)
            self.assertIn(mock.call(45), sleep.call_args_list)
            self.assertEqual(history.gzip.decompress(path.read_bytes()), raw)

    def test_retry_after_longer_than_worker_budget_stops(self):
        req = history.urllib.request.Request('https://www.sec.gov/Archives/test')
        error = urllib.error.HTTPError(req.full_url, 503, 'Unavailable', {'Retry-After': '3600'}, None)
        with mock.patch.object(history.urllib.request, 'urlopen', side_effect=error) as opened, \
             mock.patch.object(history.time, 'sleep'):
            with self.assertRaises(urllib.error.HTTPError):
                history.open_sec(req)
        self.assertEqual(opened.call_count, 1)

    def test_retry_after_is_respected(self):
        req = history.urllib.request.Request('https://www.sec.gov/Archives/test')
        error = urllib.error.HTTPError(req.full_url, 503, 'Unavailable', {'Retry-After': '90'}, None)
        with mock.patch.object(history.urllib.request, 'urlopen', side_effect=[error, 'response']), \
             mock.patch.object(history.time, 'sleep') as sleep, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(history.open_sec(req), 'response')
        self.assertIn(mock.call(90), sleep.call_args_list)

    def test_old_size_failure_retries_but_access_cooldown_does_not(self):
        rows = [dict(cik='0000000001', name='Fixture', form='8-K', filing_date='2025-09-30',
                     accession=str(i), source='https://www.sec.gov/Archives/' + str(i)) for i in range(3)]
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            state_path = root / 'history/archive_state.json.gz'
            history.save(state_path, {
                '0': dict(rows[0], status='failed', error='Response exceeds configured byte limit; requires larger archive storage', retry_after='2999-01-01'),
                '1': dict(rows[1], status='failed', error='HTTP Error 503: Service Unavailable', retry_after='2999-01-01')})
            with mock.patch.object(history, 'catalogue', return_value=(rows, [])), \
                 mock.patch.object(history, 'archive_submission', return_value=dict(sha256='fixture', raw_bytes=1, archive_bytes=1)) as archive, \
                 mock.patch.dict('os.environ', {'SEC_HISTORY_WORKERS': '1', 'SEC_HISTORY_BATCH': '3'}), \
                 contextlib.redirect_stdout(io.StringIO()):
                history.run(root)
            self.assertEqual([c.args[0] for c in archive.call_args_list], [rows[2]['source'], rows[0]['source']])
            self.assertEqual(history.load(state_path)['1']['retry_after'], '2999-01-01')

    def test_new_priority_filings_precede_legacy_retries(self):
        rows = [dict(cik='0000000001', name='Fixture', form='ABS-EE' if i == 0 else 'N-PX',
                     filing_date='2025-09-30', accession=str(i),
                     source='https://www.sec.gov/Archives/' + str(i)) for i in range(5)]
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            history.save(root / 'history/archive_state.json.gz', {
                '0': dict(rows[0], status='failed', error='Response exceeds configured byte limit; requires larger archive storage', retry_after='2999-01-01')})
            with mock.patch.object(history, 'catalogue', return_value=(rows, [])), \
                 mock.patch.object(history, 'archive_submission', return_value=dict(sha256='fixture', raw_bytes=1, archive_bytes=1)) as archive, \
                 mock.patch.dict('os.environ', {'SEC_HISTORY_WORKERS': '1', 'SEC_HISTORY_BATCH': '5'}), \
                 contextlib.redirect_stdout(io.StringIO()):
                history.run(root)
            self.assertEqual(archive.call_args_list[0].args[0], rows[1]['source'])
            self.assertEqual(archive.call_count, 5)


class StandaloneIdentityTests(unittest.TestCase):
    def xml(self, cik='1', name='Standalone Fund', series_name='Standalone Fund', series_lei='549300IRIJ5TBU8V3T78'):
        return (f'<edgarSubmission><regCik>{cik}</regCik><regName>{name}</regName>'
                '<regLei>549300IRIJ5TBU8V3T78</regLei>'
                f'<seriesName>{series_name}</seriesName><seriesLei>{series_lei}</seriesLei>'
                '<repPdDate>2025-09-30</repPdDate><invstOrSec>'
                '<assetCat>EC</assetCat><valUSD>100</valUSD></invstOrSec></edgarSubmission>').encode()

    def test_matched_lei_keeps_series_unknown(self):
        fund = parse(self.xml(), 'SEC original')
        self.assertIsNone(fund['series_id'])
        self.assertEqual(fund['fund_id'], 'CIK0000000001')
        self.assertEqual(fund['identity_basis'], 'matching_registrant_series_lei_and_name')

    def test_explicit_na_uses_registrant_name(self):
        fund = parse(self.xml(series_name='N/A', series_lei='N/A'), 'SEC original')
        self.assertEqual(fund['fund_name'], 'Standalone Fund')
        self.assertIsNone(fund['series_id'])

    def test_name_alone_or_disagreeing_lei_does_not_invent_identity(self):
        for args in ({'series_lei': ''}, {'series_lei': '529900TOB3V09W4JX713'}, {'series_name': 'Another Fund'}):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, 'series identifier'):
                parse(self.xml(**args), 'SEC original')

    def test_two_standalone_funds_and_periods_do_not_collapse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for cik, amount in [('1', 100), ('2', 200)]:
                for date in ('2025-09-30', '2025-12-31'):
                    fund = parse(self.xml(cik=cik), 'SEC original')
                    fund.update(registrant_cik=cik.zfill(10), registrant_name='Standalone Fund',
                                report_date=date, filing_date='2026-01-31', accession=cik+date)
                    fund['holdings'][0]['reported_value_usd'] = amount
                    history.save(root / 'history/normalized/funds' / (cik+date+'.json.gz'), fund)
            with contextlib.redirect_stdout(io.StringIO()):
                rebuild(root)
                rebuild(root)
            self.assertEqual(len(history.load(root / 'funds/history_index.json')['funds']), 4)
            self.assertEqual(len(history.load(root / 'funds/index.json')['funds']), 2)
            firms = history.load(root / 'history/registrants/2025-12-31.json')['firms']
            self.assertEqual(sorted(f['equity_assets_usd'] for f in firms), [100, 200])

    def test_standalone_catalogue_cik_mismatch_fails(self):
        row = dict(cik='0000000002', name='Other', form='NPORT-P', filing_date='2025-10-01',
                   accession='fixture', source='SEC original')
        raw = b'<DOCUMENT><TYPE>NPORT-P\n<XML>' + self.xml() + b'</XML></DOCUMENT>'
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, 'catalogue registrant'):
            history.normalize(row, raw, pathlib.Path(directory), '2025-09-30')

