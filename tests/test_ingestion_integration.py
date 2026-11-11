"""Streaming, N-PORT filtering, interruption and publication work together."""
import contextlib
import gzip
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import sec_history as history
import release_history as releases


class IngestionIntegrationTests(unittest.TestCase):
    def test_filtered_original_publishes_after_access_interruption(self):
        raw = (b'<SEC-DOCUMENT><DOCUMENT><TYPE>NPORT-P/A\n<XML>'
               b'<edgarSubmission><repPdDate>2025-05-31</repPdDate>'
               b'<totAssets>0</totAssets></edgarSubmission></XML></DOCUMENT>')
        rows = [dict(cik='0000000001', name='Fixture Trust', form='NPORT-P/A',
                     filing_date='2025-10-01', accession=str(i),
                     source='https://www.sec.gov/Archives/fixture/' + str(i))
                for i in range(3)]
        response = io.BytesIO(raw)
        response.headers = {'Content-Length': str(len(raw))}
        outage = urllib.error.HTTPError(rows[1]['source'], 503, 'Unavailable', {}, None)
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            with mock.patch.object(history, 'catalogue', return_value=(rows, [])), \
                 mock.patch.object(history.urllib.request, 'urlopen', side_effect=[response, outage, outage, outage]) as request, \
                 mock.patch.object(history.time, 'sleep'), \
                 mock.patch.dict('os.environ', {'SEC_HISTORY_BATCH': '3'}), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(SystemExit, 'HTTP 503'):
                    history.run(root)
            self.assertEqual(request.call_count, 4)
            state = history.load(root / 'history/archive_state.json.gz')
            self.assertEqual(state['0']['normalized_files'], [])
            self.assertNotIn('normalization_error', state['0'])
            self.assertEqual(state['0']['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(state['1']['status'], 'failed')
            self.assertNotIn('2', state)
            status = history.load(root / 'history/status.json')
            self.assertEqual(status['pending_filings'], 2)
            self.assertEqual(status['download_interruption']['http_status'], 503)
            uploaded = {}

            def command(args, **kwargs):
                if args[2] == 'upload':
                    file = pathlib.Path(args[4])
                    uploaded['bytes'] = file.read_bytes()
                    uploaded['name'] = file.name
                if '--json' in args:
                    asset = dict(name=uploaded['name'], size=len(uploaded['bytes']),
                                 digest='sha256:' + hashlib.sha256(uploaded['bytes']).hexdigest())
                    return SimpleNamespace(returncode=0, stdout=json.dumps({'assets': [asset]}))
                return SimpleNamespace(returncode=0)

            with mock.patch.dict('os.environ', {'GITHUB_REPOSITORY': 'cstrohwork/aibank'}), \
                 mock.patch.object(releases.subprocess, 'run', side_effect=command), \
                 contextlib.redirect_stdout(io.StringIO()):
                releases.publish(root)
            state = history.load(root / 'history/archive_state.json.gz')
            self.assertFalse((root / state['0']['raw_file']).exists())
            self.assertEqual(state['0']['source'], rows[0]['source'])
            self.assertEqual(state['0']['release_asset_sha256'], hashlib.sha256(uploaded['bytes']).hexdigest())
            history.release_bytes.cache_clear()
            try:
                with mock.patch.object(history, 'fetch', return_value=uploaded['bytes']):
                    self.assertEqual(history.read_original(root, state['0']), raw)
            finally:
                history.release_bytes.cache_clear()
            published_status = history.load(root / 'history/status.json')
            self.assertEqual(published_status['git_raw_bytes'], 0)
            self.assertEqual(published_status['status'], 'in_progress')
            self.assertEqual(published_status['download_interruption'], status['download_interruption'])
            self.assertEqual(state['1']['retry_after'], status['download_interruption']['retry_after'])


if __name__ == '__main__':
    unittest.main()
