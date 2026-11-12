import contextlib
import datetime as dt
import gzip
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import refresh_funds as funds
import stream_nport
from reconcile_ownership import aggregate


class FundEvidenceTests(unittest.TestCase):
    def position(self,units='NS',currency='EUR'):
        return ET.fromstring('<invstOrSec><name>Equity</name><cusip>123456789</cusip><assetCat>EC</assetCat><valUSD>123</valUSD><balance>7</balance>'+ (f'<units>{units}</units>' if units else '') +(f'<curCd>{currency}</curCd>' if currency else '') +'</invstOrSec>')
    def test_actual_units_and_currency_retained(self):
        row=funds.parse_position(self.position())
        self.assertEqual(row['balance_units'],'NS');self.assertEqual(row['currency_code'],'EUR')
        self.assertEqual(row['reported_value_usd'],123)
        positions,_=aggregate([row],True)
        self.assertEqual(positions['123456789']['shares'],7)
    def test_missing_other_and_principal_units_do_not_become_shares(self):
        for unit in ('','PA','OU','NC'):
            row=funds.parse_position(self.position(unit,''))
            self.assertIsNone(row['currency_code'])
            self.assertEqual(row['balance_units'],unit or None)
            p,_=aggregate([row],True)
            self.assertIsNone(p['123456789']['shares'])
    def test_nested_derivative_units_do_not_supply_position_units(self):
        n=self.position('','');nested=ET.SubElement(n,'derivativeInfo');ET.SubElement(nested,'units').text='NS';ET.SubElement(nested,'curCd').text='USD'
        row=funds.parse_position(n)
        self.assertIsNone(row['balance_units']);self.assertIsNone(row['currency_code'])
    def test_mixed_known_and_unknown_units_remain_unknown(self):
        a=funds.parse_position(self.position());b=funds.parse_position(self.position(''))
        for rows in ([a,b],[b,a]):
            p,_=aggregate(rows,True);self.assertIsNone(p['123456789']['shares'])
    def test_download_capture_separates_retrieval_and_ingestion(self):
        record={'report_date':'2025-09-30','filing_date':'2025-10-02'}
        result=funds.capture_download_evidence(record,'2026-11-12T01:00:00+00:00')
        self.assertNotIn('ingested_at',record)
        self.assertEqual(result['retrieved_at'],'2026-11-12T01:00:00+00:00')
        self.assertEqual(result['public_observed_at'],result['retrieved_at'])
        self.assertIsNotNone(dt.datetime.fromisoformat(result['ingested_at']).tzinfo)
        self.assertNotIn('public_available_at',result)
    def test_streaming_preserves_evidence_without_redating_old_originals(self):
        position=ET.tostring(self.position(),encoding='unicode')
        xml='<edgarSubmission><genInfo><seriesId>S000000001</seriesId><seriesName>Fund</seriesName><repPdDate>2025-09-30</repPdDate></genInfo><invstOrSecs>'+position+'</invstOrSecs></edgarSubmission>'
        raw=('<DOCUMENT><TYPE>NPORT-P\n<XML>'+xml+'</XML></DOCUMENT>').encode()
        @contextlib.contextmanager
        def source(root,record):
            yield io.BytesIO(raw)
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            record=dict(cik='0000000001',name='Trust',accession='test',form='NPORT-P',filing_date='2025-10-02',source='sec',sha256=hashlib.sha256(raw).hexdigest())
            with mock.patch.object(stream_nport,'original_stream',source):
                paths=stream_nport.normalize(root,record,'2025-09-30')
                fund=json.loads(gzip.decompress((root/paths[0]).read_bytes()))
                self.assertNotIn('retrieved_at',fund);self.assertNotIn('ingested_at',fund)
                self.assertEqual(fund['holdings'][0]['balance_units'],'NS')
                record.update(retrieved_at='2026-01-02T12:00:00+00:00',ingested_at='2026-01-02T12:00:01+00:00')
                paths=stream_nport.normalize(root,record,'2025-09-30')
                fund=json.loads(gzip.decompress((root/paths[0]).read_bytes()))
                self.assertEqual(fund['retrieved_at'],record['retrieved_at']);self.assertEqual(fund['ingested_at'],record['ingested_at'])
