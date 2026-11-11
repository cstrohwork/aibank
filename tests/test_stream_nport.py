import contextlib
import gzip
import hashlib
import io
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import sec_history as history
import stream_nport as stream


class StreamingNportTests(unittest.TestCase):
    def original(self, date='2025-09-30', count=2):
        xml = ('<?xml version="1.0"?><edgarSubmission xmlns="urn:fixture">'
               '<genInfo><seriesId>S000000001</seriesId><seriesName>Fixture Fund</seriesName>'
               f'<repPdDate>{date}</repPdDate></genInfo><fundInfo><totAssets>123</totAssets>'
               '</fundInfo><invstOrSecs>' + ''.join(
               '<invstOrSec><name>Issuer</name><assetCat>EC</assetCat><valUSD>100</valUSD>'
               '<cusip>123456789</cusip></invstOrSec>' for _ in range(count)) +
               '</invstOrSecs></edgarSubmission>')
        return ('<SEC-DOCUMENT>\n<DOCUMENT><TYPE>EX-99\n<TEXT>plain exhibit</TEXT></DOCUMENT>'
                '<DOCUMENT><TYPE>NPORT-P\n<TEXT><XML>\n' + xml +
                '\n</XML></TEXT></DOCUMENT>trailing source material').encode()

    def record(self, root, raw):
        path = root / 'history/raw/fixture.gz'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(raw))
        return dict(cik='0000000001', name='Registrant', form='NPORT-P', accession='fixture',
                    filing_date='2025-10-01', source='SEC original',
                    raw_file=str(path.relative_to(root)), raw_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

    def test_streaming_matches_regular_parser_and_full_source_checksum(self):
        raw = self.original()
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            record = self.record(root, raw)
            paths = history.normalize(record, raw, root, '2025-09-30')
            expected = history.load(root / paths[0])
            result = stream.normalize(root, record, '2025-09-30')
            self.assertEqual(history.load(root / result[0]), expected)
            record['sha256'] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                stream.normalize(root, record, '2025-09-30')
            self.assertEqual(history.load(root / result[0]), expected)

    def test_every_marker_can_cross_read_boundaries(self):
        raw = self.original()
        class TinyReader(io.BytesIO):
            def read(self, size=-1):
                if not 0 < size <= 64 * 1024:
                    raise AssertionError('unbounded read')
                return super().read(min(3, size))
        output = io.BytesIO()
        stream.extract_xml(TinyReader(raw), output, hashlib.sha256(raw).hexdigest())
        self.assertTrue(output.getvalue().startswith(b'<?xml'))
        self.assertTrue(output.getvalue().rstrip().endswith(b'</edgarSubmission>'))

    def test_position_limit_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'primary.xml'
            with path.open('wb') as output:
                raw = self.original(count=3)
                stream.extract_xml(io.BytesIO(raw), output, hashlib.sha256(raw).hexdigest())
            with self.assertRaisesRegex(ValueError, 'position limit'):
                stream.parse_xml(path, '2025-09-30', max_positions=2)

    def test_old_report_is_excluded_and_truncated_xml_is_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            record = self.record(root, self.original(date='2025-08-31'))
            self.assertEqual(stream.normalize(root, record, '2025-09-30'), [])
            raw = self.original().replace(b'</XML>', b'')
            record = self.record(root, raw)
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                stream.normalize(root, record, '2025-09-30')

    def test_large_nport_dispatch_avoids_whole_original_reads(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            raw = self.original()
            record = self.record(root, raw)
            digest = hashlib.sha256(raw)
            block = b' ' * 65536
            with gzip.open(root / record['raw_file'], 'wb') as packed:
                packed.write(raw)
                for _ in range(1240):
                    packed.write(block)
                    digest.update(block)
            record.update(raw_bytes=len(raw) + 1240 * len(block), sha256=digest.hexdigest(),
                          status='archived', normalization_error='old parser limit')
            history.save(root / 'history/archive_state.json.gz', {'fixture': record})
            with mock.patch.object(history, 'catalogue', return_value=([record], [])), \
                 mock.patch.object(history, 'read_original', side_effect=AssertionError('whole source loaded')), \
                 contextlib.redirect_stdout(io.StringIO()):
                history.run(root)
            state = history.load(root / 'history/archive_state.json.gz')['fixture']
            self.assertNotIn('normalization_error', state)
            self.assertEqual(len(history.load(root / state['normalized_files'][0])['holdings']), 2)
