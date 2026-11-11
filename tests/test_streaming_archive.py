import gzip
import hashlib
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import sec_history as history


class Response(io.BytesIO):
    def __init__(self, payload, length=None):
        super().__init__(payload)
        self.headers = {} if length is None else {'Content-Length': str(length)}

    def read(self, size=-1):
        if size < 0 or size > 65536:
            raise AssertionError('Unbounded read')
        return super().read(size)


class StreamingArchiveTests(unittest.TestCase):
    def archive(self, response, path, **kwargs):
        with mock.patch.object(history.urllib.request, 'urlopen', return_value=response), mock.patch.object(history.time, 'sleep'):
            return history.archive_submission('https://www.sec.gov/Archives/test', path, **kwargs)

    def test_round_trip_digest_and_bounded_reads(self):
        raw = b'<SEC-DOCUMENT>' + b'original SEC evidence' * 10000
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'original.gz'
            result = self.archive(Response(raw, len(raw)), path, archive_limit=1000000)
            self.assertEqual(gzip.decompress(path.read_bytes()), raw)
            self.assertEqual(result, {'sha256': hashlib.sha256(raw).hexdigest(),
                'raw_bytes': len(raw), 'archive_bytes': path.stat().st_size})
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_original_over_old_80mb_limit_streams(self):
        class LargeResponse:
            headers = {'Content-Length': str(81_000_000)}
            remaining = 81_000_000
            digest = hashlib.sha256()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, size):
                chunk = b'x' * min(size, self.remaining)
                if self.remaining == 81_000_000:
                    chunk = b'<SEC-DOCUMENT>' + chunk[14:]
                self.remaining -= len(chunk)
                self.digest.update(chunk)
                return chunk
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'large.gz'
            response = LargeResponse()
            result = self.archive(response, path, archive_limit=1_000_000)
            self.assertEqual(result['raw_bytes'], 81_000_000)
            self.assertEqual(result['sha256'], response.digest.hexdigest())
            with gzip.open(path, 'rb') as archived:
                self.assertTrue(archived.read(100).startswith(b'<SEC-DOCUMENT>'))

    def test_failures_remove_partial_and_preserve_existing(self):
        cases = [
            (b'<SEC-DOCUMENT>' + b'x' * 100, {}, {'raw_limit': 20}, 'raw byte limit'),
            (b'<SEC-DOCUMENT>' + b'x' * 100, {}, {'archive_limit': 10}, 'compressed archive budget'),
            (b'<SEC-DOCUMENT>', {'length': 999}, {}, 'Content-Length mismatch'),
            (b'<html>access denied</html>', {}, {}, 'not a complete SEC'),
            (b'<SEC-DOCUMENT>', {}, {'deadline': 0}, 'time budget'),
        ]
        for raw, response_options, options, error in cases:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                path = pathlib.Path(directory) / 'original.gz'
                path.write_bytes(b'existing evidence')
                with self.assertRaisesRegex((ValueError, TimeoutError), error):
                    self.archive(Response(raw, **response_options), path,
                        **dict({'archive_limit': 1000000}, **options))
                self.assertEqual(path.read_bytes(), b'existing evidence')
                self.assertEqual(list(path.parent.iterdir()), [path])

    def test_interrupted_response_cleans_staging(self):
        response = Response(b'<SEC-DOCUMENT>' + b'x' * 100000)
        original_read = response.read
        response.read = mock.Mock(side_effect=[original_read(65536), OSError('connection lost')])
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'original.gz'
            with self.assertRaisesRegex(OSError, 'connection lost'):
                self.archive(response, path, archive_limit=1000000)
            self.assertEqual(list(path.parent.iterdir()), [])

    def test_http_503_propagates_without_staging(self):
        import urllib.error
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'original.gz'
            with mock.patch.object(history.urllib.request, 'urlopen',
                    side_effect=urllib.error.HTTPError('SEC', 503, 'Unavailable', {}, None)), mock.patch.object(history.time, 'sleep'):
                with self.assertRaises(urllib.error.HTTPError):
                    history.archive_submission('https://www.sec.gov/test', path, 1000000)
            self.assertEqual(list(path.parent.iterdir()), [])

    def test_run_retains_large_original_and_explicit_unknown_normalization(self):
        row = {'accession': 'test', 'cik': '1', 'filing_date': '2025-10-01',
               'form': '13F-HR', 'source': 'https://www.sec.gov/test'}
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            with mock.patch.object(history, 'catalogue', return_value=([row], [])), mock.patch.object(
                    history, 'archive_submission', return_value={
                        'sha256': 'source-digest', 'raw_bytes': 81_000_000, 'archive_bytes': 100000}), mock.patch.object(history, 'normalize') as normalize:
                history.run(root)
            record = history.load(root / 'history/archive_state.json.gz')['test']
            self.assertEqual(record['status'], 'archived')
            self.assertEqual(record['source'], row['source'])
            self.assertEqual(record['sha256'], 'source-digest')
            self.assertIn('Normalization deferred', record['normalization_error'])
            self.assertEqual(history.load(root / 'history/status.json')['normalization_failures'], 1)
            self.assertEqual(history.load(root / 'history/status.json')['status'], 'in_progress')
            normalize.assert_not_called()
            with mock.patch.object(history, 'catalogue', return_value=([row], [])), mock.patch.object(
                    history, 'read_original') as read_original:
                history.run(root)
            read_original.assert_not_called()


if __name__ == '__main__':
    unittest.main()
