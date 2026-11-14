"""Concurrency, cooldown and durable recovery safeguards for the SEC worker."""
import contextlib
import datetime as dt
import gzip
import hashlib
import io
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import sec_history as history
import sec_worker_control as control


class ParallelRecoveryTests(unittest.TestCase):
    def test_three_downloads_overlap_and_every_completion_is_retained_once(self):
        barrier = threading.Barrier(3)
        seen = []
        lock = threading.Lock()
        rows = [dict(cik='1', name='Fixture', form='8-K', filing_date='2026-11-12',
                     accession=str(i), source='https://www.sec.gov/' + str(i)) for i in range(6)]
        def download(url, path, *args, **kwargs):
            with lock:
                seen.append(url)
            barrier.wait(timeout=5)
            raw = b'<SEC-DOCUMENT>' + url.encode()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(raw))
            return dict(sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw), archive_bytes=path.stat().st_size)
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            with mock.patch.object(history, 'catalogue', return_value=(rows, [])), \
                 mock.patch.object(history, 'archive_submission', side_effect=download) as archive, \
                 mock.patch.dict('os.environ', {'SEC_HISTORY_WORKERS': '3', 'SEC_HISTORY_BATCH': '6'}), \
                 contextlib.redirect_stdout(io.StringIO()):
                history.run(root)
                history.run(root)
            state = history.load(root / 'history/archive_state.json.gz')
            self.assertEqual(archive.call_count, 6)
            self.assertEqual(set(seen), {r['source'] for r in rows})
            self.assertEqual(len(state), 6)
            self.assertTrue(all(r['status'] == 'archived' for r in state.values()))
            for record in state.values():
                self.assertTrue(history.read_original(root, record).startswith(b'<SEC-DOCUMENT>'))

    def test_open_request_stops_before_network_when_peer_reports_block(self):
        stopped = threading.Event()
        stopped.set()
        request = history.urllib.request.Request('https://www.sec.gov/test')
        with mock.patch.object(history.urllib.request, 'urlopen') as opened:
            with self.assertRaises(history.BatchBudgetExceeded):
                history.open_sec(request, stop_event=stopped)
        opened.assert_not_called()

    def test_network_timeout_retries_and_recovers(self):
        request = history.urllib.request.Request('https://www.sec.gov/test')
        with mock.patch.object(history.urllib.request, 'urlopen', side_effect=[TimeoutError(), urllib.error.URLError('reset'), 'ok']) as opened, \
             mock.patch.object(history.time, 'sleep'):
            self.assertEqual(history.open_sec(request), 'ok')
        self.assertEqual(opened.call_count, 3)

    def test_cooldowns_are_minutes_and_respect_retry_after(self):
        now = dt.datetime(2026, 11, 12, 12, tzinfo=dt.timezone.utc)
        error = urllib.error.HTTPError('SEC', 503, 'Unavailable', {}, None)
        self.assertEqual(history.retry_at(error, now), '2026-11-12T12:05:00+00:00')
        error.headers = {'Retry-After': '3600'}
        self.assertEqual(history.retry_at(error, now), '2026-11-12T13:00:00+00:00')
        self.assertFalse(history.retry_due('2026-11-12T12:05:00+00:00', now))
        self.assertTrue(history.retry_due('2026-11-12', now))

    def test_atomic_checkpoint_failure_keeps_previous_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'archive_state.json.gz'
            history.save(path, {'retained': 1})
            with mock.patch.object(pathlib.Path, 'replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    history.save(path, {'lost': 2})
            self.assertEqual(history.load(path), {'retained': 1})
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_shared_budget_includes_footer_and_releases_failed_staging(self):
        raw = b'<SEC-DOCUMENT>original'
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(history.time, 'sleep'):
            root = pathlib.Path(directory)
            budget = history.ArchiveBudget(1000)
            for i in range(3):
                response = io.BytesIO(raw); response.headers = {}
                with mock.patch.object(history.urllib.request, 'urlopen', return_value=response):
                    history.archive_submission('https://www.sec.gov/test', root / str(i), 1000, budget=budget)
            self.assertEqual(budget.used, sum(p.stat().st_size for p in root.iterdir()))
            used = budget.used
            budget.limit = used + 1
            response = io.BytesIO(raw); response.headers = {}
            with mock.patch.object(history.urllib.request, 'urlopen', return_value=response):
                with self.assertRaises(history.BatchBudgetExceeded):
                    history.archive_submission('https://www.sec.gov/test', root / 'failed', 1000, budget=budget)
            self.assertEqual(budget.used, used)
            self.assertFalse((root / 'failed').exists())


class SupervisorTests(unittest.TestCase):
    now = dt.datetime(2026, 11, 12, 12, tzinfo=dt.timezone.utc)

    def run_record(self, **changes):
        return dict(status='completed', conclusion='success', created_at='2026-11-12T11:50:00Z',
                    updated_at='2026-11-12T11:59:30Z', **changes)

    def test_active_run_prevents_duplicate_dispatch(self):
        self.assertEqual(control.decision([{'status': 'in_progress'}], {}, self.now)[0], 'wait')

    def test_productive_batch_dispatches_without_waiting_for_schedule(self):
        status = {'checked_at': '2026-11-12T12:01:00Z', 'downloaded_this_run': 10, 'pending_filings': 50}
        with mock.patch.object(control, 'load', return_value=status), \
             mock.patch.object(control, 'api', side_effect=[{'workflow_runs': [{'id': 1, 'status': 'in_progress'}]}, {'workflow_runs': []}]), \
             mock.patch.object(control, 'gh') as dispatch, \
             mock.patch.dict('os.environ', {'GITHUB_REPOSITORY': 'cstrohwork/aibank', 'GITHUB_RUN_ID': '1', 'SEC_RUN_STARTED_AT': '2026-11-12T12:00:00Z'}):
            control.continue_batch()
        self.assertEqual(dispatch.call_count, 1)
        self.assertIn('POST', dispatch.call_args.args)

    def test_stale_checkpoint_and_sec_cooldown_prevent_immediate_dispatch(self):
        for status in [
            {'checked_at': '2026-11-12T11:00:00Z', 'downloaded_this_run': 10, 'pending_filings': 50},
            {'checked_at': '2026-11-12T12:01:00Z', 'downloaded_this_run': 10, 'pending_filings': 50, 'next_retry_at': '2999-01-01T00:00:00Z'}]:
            with self.subTest(status=status), mock.patch.object(control, 'load', return_value=status), \
                 mock.patch.object(control, 'api') as api, mock.patch.object(control, 'gh') as dispatch, \
                 mock.patch.dict('os.environ', {'SEC_RUN_STARTED_AT': '2026-11-12T12:00:00Z'}):
                control.continue_batch()
            api.assert_not_called()
            dispatch.assert_not_called()

    def test_immediate_continuation_does_not_duplicate_an_existing_queue(self):
        status = {'checked_at': '2026-11-12T12:01:00Z', 'downloaded_this_run': 10, 'pending_filings': 50}
        with mock.patch.object(control, 'load', return_value=status), \
             mock.patch.object(control, 'api', return_value={'workflow_runs': [{'id': 1, 'status': 'in_progress'}, {'id': 2, 'status': 'queued'}]}), \
             mock.patch.object(control, 'gh') as dispatch, \
             mock.patch.dict('os.environ', {'GITHUB_REPOSITORY': 'cstrohwork/aibank', 'GITHUB_RUN_ID': '1', 'SEC_RUN_STARTED_AT': '2026-11-12T12:00:00Z'}):
            control.continue_batch()
        dispatch.assert_not_called()

    def test_failed_run_resumes_after_backoff_even_without_progress(self):
        run = self.run_record()
        run['conclusion'] = 'failure'
        self.assertEqual(control.decision([run], {}, self.now)[0], 'cooldown')
        self.assertEqual(control.decision([run], {}, self.now + dt.timedelta(minutes=2))[0], 'dispatch')

    def test_sec_retry_after_and_storage_block_override_restart(self):
        self.assertEqual(control.decision([], {'next_retry_at': '2026-11-12T13:00:00Z'}, self.now)[0], 'cooldown')
        self.assertEqual(control.decision([], {'storage_blocked': True}, self.now)[0], 'blocked')
        self.assertEqual(control.decision([], {}, self.now)[0], 'dispatch')

    def test_recovery_validates_sources_and_preserves_newer_committed_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory) / 'data'
            folder = pathlib.Path(directory) / 'artifact'
            raw = b'<SEC-DOCUMENT>verified original'
            rel = 'history/raw/2026/1/accession.txt.gz'
            file = folder / 'raw/2026/1/accession.txt.gz'
            file.parent.mkdir(parents=True)
            file.write_bytes(gzip.compress(raw))
            record = dict(status='archived', raw_file=rel, sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw))
            history.save(folder / 'archive_state.json.gz', {'accession': record})
            self.assertEqual(control.recover_folder(root, folder), 1)
            self.assertEqual(history.read_original(root, history.load(root / 'history/archive_state.json.gz')['accession']), raw)
            state = history.load(root / 'history/archive_state.json.gz')
            state['accession']['retained_newer_metadata'] = True
            history.save(root / 'history/archive_state.json.gz', state)
            self.assertEqual(control.recover_folder(root, folder), 0)
            self.assertTrue(history.load(root / 'history/archive_state.json.gz')['accession']['retained_newer_metadata'])
            file.write_bytes(gzip.compress(b'corrupt source'))
            self.assertEqual(control.recover_folder(root.parent / 'other', folder), 0)
