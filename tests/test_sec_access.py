"""An SEC access interruption must preserve progress and stop the batch."""
import contextlib
import io
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import sec_history as history


class SecAccessTests(unittest.TestCase):
    def rows(self):
        return [dict(cik='0000000001', name='Fixture', form='8-K',
                     filing_date='2025-09-30', accession=str(i),
                     source='https://www.sec.gov/Archives/fixture/' + str(i))
                for i in range(3)]

    def open_response(self, responses):
        responses = iter(responses)
        def open_request(request, **kwargs):
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            stream = io.BytesIO(response)
            stream.headers = {'Content-Length': str(len(response))}
            return stream
        return open_request

    def execute(self, root, responses):
        with mock.patch.object(history, 'catalogue', return_value=(self.rows(), [])), \
             mock.patch.object(history.urllib.request, 'urlopen', side_effect=self.open_response(responses)) as fetch, \
             mock.patch.object(history.time, 'sleep'), \
             mock.patch.dict('os.environ', {'SEC_HISTORY_BATCH': '3'}), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                history.run(root)
        return fetch

    def test_access_failures_stop_after_progress_and_keep_sources(self):
        raw = b'<SEC-DOCUMENT>fixture original'
        for code in (403, 429, 503):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as folder:
                root = pathlib.Path(folder)
                url = self.rows()[1]['source']
                error = urllib.error.HTTPError(url, code, 'access interrupted', {}, None)
                fetch = self.execute(root, [raw] + [error] * (3 if code == 503 else 1))
                self.assertEqual(fetch.call_count, 4 if code == 503 else 2)
                state = history.load(root / 'history/archive_state.json.gz')
                self.assertEqual(history.read_original(root, state['0']), raw)
                self.assertEqual(state['1']['status'], 'failed')
                self.assertIn('retry_after', state['1'])
                self.assertNotIn('2', state)
                status = history.load(root / 'history/status.json')
                self.assertEqual(status['downloaded_this_run'], 1)
                self.assertEqual(status['archived_filings'], 1)
                self.assertEqual(status['pending_filings'], 2)
                self.assertEqual(status['status'], 'in_progress')
                self.assertEqual(status['download_interruption']['http_status'], code)
                self.assertEqual(status['download_interruption']['accession'], '1')
                self.assertEqual(status['download_interruption']['source'], url)

    def test_503_without_progress_persists_diagnostic(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            error = urllib.error.HTTPError(self.rows()[0]['source'], 503,
                                           'Service Unavailable', {}, None)
            fetch = self.execute(root, [error, error, error])
            self.assertEqual(fetch.call_count, 3)
            status = history.load(root / 'history/status.json')
            self.assertEqual(status['pending_filings'], 3)
            self.assertEqual(status['download_interruption']['error'], str(error))

    def test_non_access_failure_can_continue_and_retains_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            error = urllib.error.HTTPError(self.rows()[0]['source'], 404, 'Not Found', {}, None)
            with mock.patch.object(history, 'catalogue', return_value=(self.rows(), [])), \
                 mock.patch.object(history.urllib.request, 'urlopen', side_effect=self.open_response([error, b'<SEC-DOCUMENT>one', b'<SEC-DOCUMENT>two'])) as fetch, \
                 mock.patch.object(history.time, 'sleep'), \
                 mock.patch.dict('os.environ', {'SEC_HISTORY_BATCH': '3'}), \
                 contextlib.redirect_stdout(io.StringIO()):
                history.run(root)
            self.assertEqual(fetch.call_count, 3)
            status = history.load(root / 'history/status.json')
            self.assertIsNone(status['download_interruption'])
            self.assertEqual(status['download_failures'], 1)
            self.assertEqual(status['archived_filings'], 2)


if __name__ == '__main__':
    unittest.main()
