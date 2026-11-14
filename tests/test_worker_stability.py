"""Regressions for daily starvation, parallel cooldowns and poison records."""
import contextlib
import datetime as dt
import io
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import sec_history as history
import sec_worker_control as control


class StabilityTests(unittest.TestCase):
    now = dt.datetime(2026, 11, 13, 18, tzinfo=dt.timezone.utc)

    def run_record(self, result='success', updated='2026-11-12T10:00:00Z'):
        return dict(status='completed', conclusion=result, created_at=updated, updated_at=updated)

    def test_overdue_daily_precedes_more_backfill(self):
        result = control.select_worker([], [self.run_record()], {}, self.now)
        self.assertEqual(result[2], 'refresh-sec.yml')

    def test_recent_daily_allows_backfill(self):
        result = control.select_worker([], [self.run_record(updated='2026-11-13T10:00:00Z')], {}, self.now)
        self.assertEqual(result[2], 'sec-history.yml')

    def test_cancelled_refresh_does_not_satisfy_daily_completion(self):
        result = control.select_worker([], [self.run_record('cancelled', '2026-11-13T17:59:00Z')], {}, self.now)
        self.assertEqual(result[2], 'refresh-sec.yml')

    def test_queued_refresh_cannot_be_displaced_by_backfill(self):
        self.assertEqual(control.select_worker([], [{'status': 'queued'}], {}, self.now)[0], 'wait')

    def test_daily_retry_obeys_service_cooldown(self):
        status = {'next_retry_at': '2026-11-13T18:05:00Z'}
        self.assertEqual(control.select_worker([], [], status, self.now)[0], 'cooldown')

    def test_daily_failure_backoff_and_recovery(self):
        runs = [self.run_record('failure', '2026-11-13T17:59:45Z')]
        self.assertEqual(control.select_worker([], runs, {}, self.now)[0], 'cooldown')
        self.assertEqual(control.select_worker([], runs, {}, self.now + dt.timedelta(minutes=2))[2], 'refresh-sec.yml')

    def test_normalization_failure_cannot_starve_later_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = root / 'history/archive_state.json.gz'
            history.save(path, {str(i).zfill(3): dict(status='archived', form='NPORT-P',
                normalization_error='poison', raw_bytes=1) for i in range(61)})
            attempted = []
            def read(root, record):
                attempted.append(id(record))
                raise ValueError('still unsupported; preserve source')
            with mock.patch.object(history, 'catalogue', return_value=([], [])), \
                 mock.patch.object(history, 'read_original', side_effect=read), \
                 contextlib.redirect_stdout(io.StringIO()):
                for _ in range(3):
                    with self.assertRaises(SystemExit):
                        history.run(root)
            state = history.load(path)
            self.assertTrue(all(r.get('normalization_attempted_at') for r in state.values()))
            self.assertTrue(all(r['normalization_error'] == 'still unsupported; preserve source' for r in state.values()))
            self.assertEqual(len(attempted), 90)

    def test_shorter_parallel_failure_keeps_longest_cooldown(self):
        rows = [dict(cik='1', name='Fixture', form='8-K', filing_date='2026-11-13',
                     accession=str(i), source='https://www.sec.gov/' + str(i)) for i in range(2)]
        errors = [urllib.error.HTTPError('SEC', 429, 'Limited', {'Retry-After': '3600'}, None),
                  urllib.error.HTTPError('SEC', 503, 'Unavailable', {}, None)]
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            with mock.patch.object(history, 'catalogue', return_value=(rows, [])), \
                 mock.patch.object(history, 'archive_submission', side_effect=errors), \
                 mock.patch.object(history, 'as_completed', side_effect=lambda fs: iter(fs)), \
                 mock.patch.dict('os.environ', {'SEC_HISTORY_WORKERS': '2', 'SEC_HISTORY_BATCH': '2'}), \
                 contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                history.run(root)
            state = history.load(root / 'history/archive_state.json.gz')
            status = history.load(root / 'history/status.json')
            self.assertEqual(status['next_retry_at'], state['0']['retry_after'])
            self.assertEqual(status['download_failures'], 2)


if __name__ == '__main__':
    unittest.main()
