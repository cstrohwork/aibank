import copy
import json
import gzip
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import ingest_sp1500_fundamentals as ingest
import benchmark_proxy_coverage as benchmark
from benchmark_proxy_coverage import proxy_coverage

class ProxyBenchmarkTests(unittest.TestCase):
 def sources(self):
  def source(day,rows,label):
   return {'as_of':day,'retrieved_at':'2026-11-13T12:00:00+00:00',
    'source_url':'https://example.test/'+label,'source_sha256':'a'*64,
    'membership_basis':'Current ETF holdings proxy; not official membership',
    'securities':rows,'excluded_rows':[]}
  def row(ticker,cik,weight,cusip=None):
   return {'ticker':ticker,'cik':cik,'cusip':cusip,'weight_pct':weight,'mapping_status':'unique_sec_ticker_match_current' if cik else 'unmapped_or_ambiguous'}
  return source('2026-11-10',[row('AAA','1',60,'123'),row('BBB','2',40,'456')],'sptm'), source('2026-11-12',[row('AAA','1',20),row('CCC',None,80),row('DDD','3',0)],'iwv')
 def records(self):
  return {'1':{'fields':{'revenue':[{'unit':'USD','start':'2025-01-01','end':'2025-12-31','filed':'2026-11-11','val':100,'tag':'Revenues'}]}}}
 def universe(self):return ingest.merge_proxy_universes(*self.sources())
 def test_union_deduplicates_but_keeps_weights_dates_and_provenance(self):
  sp,iwv=self.sources();before=copy.deepcopy((sp,iwv));u=ingest.merge_proxy_universes(sp,iwv)
  self.assertEqual(len(u['securities']),4)
  self.assertEqual(u['securities'][0]['universe_memberships'],['Russell3000_proxy','S&P1500_proxy'])
  self.assertEqual(u['proxy_snapshots']['S&P1500_proxy']['securities'][0]['weight_pct'],60)
  self.assertEqual(u['proxy_snapshots']['Russell3000_proxy']['securities'][0]['weight_pct'],20)
  self.assertEqual((sp,iwv),before)
  self.assertIn('not point-in-time index constituents',u['membership_basis'])
 def test_conflicting_cik_or_cusip_is_not_silently_merged(self):
  for conflict in ({'cik':'9'},{'cusip':'999'}):
   sp,iwv=self.sources();iwv['securities'][0].update(conflict)
   with self.assertRaisesRegex(ValueError,'Conflicting proxy identity'):ingest.merge_proxy_universes(sp,iwv)
 def test_own_denominators_and_filing_date_cutoffs(self):
  r=proxy_coverage(self.universe(),self.records(),'2026-11-12')
  sp=r['benchmarks']['S&P1500_proxy'];iwv=r['benchmarks']['Russell3000_proxy']
  self.assertEqual(sp['field_weight_coverage_pct']['revenue'],0)
  self.assertEqual(iwv['field_weight_coverage_pct']['revenue'],20)
  self.assertEqual(iwv['mapped_provider_weight_coverage_pct'],20)
  self.assertEqual(iwv['security_count'],3) # rounded zero remains represented
  self.assertEqual(sp['fact_cutoff'],'2026-11-10')
  self.assertIsNone(r['calculated_style'])
 def test_future_proxy_snapshot_is_blocked(self):
  r=proxy_coverage(self.universe(),self.records(),'2026-11-10')
  self.assertEqual(r['benchmarks']['Russell3000_proxy']['status'],'blocked_provider_snapshot_after_cutoff')
  self.assertIsNone(r['benchmarks']['Russell3000_proxy']['field_weight_coverage_pct'])
 def test_legacy_union_cannot_reconstruct_lost_provider_weights(self):
  u=self.universe();u.pop('proxy_snapshots')
  self.assertEqual(proxy_coverage(u,self.records())['status'],'blocked_missing_separate_provider_snapshots')
 def test_invalid_weights_are_blocked_without_renormalization(self):
  for weight in (float('nan'),float('inf'),-1,True,None):
   u=self.universe();u['proxy_snapshots']['S&P1500_proxy']['securities'][1]['weight_pct']=weight
   r=proxy_coverage(u,self.records(),'2026-11-12')
   self.assertEqual(r['benchmarks']['S&P1500_proxy']['status'],'blocked_invalid_provider_weights')
 def test_zero_weights_and_missing_source_stay_blocked(self):
  u=self.universe()
  for member in u['proxy_snapshots']['S&P1500_proxy']['securities']:member['weight_pct']=0
  u['proxy_snapshots']['Russell3000_proxy']['source_sha256']=None
  r=proxy_coverage(u,self.records(),'2026-11-12')
  self.assertEqual(r['benchmarks']['S&P1500_proxy']['status'],'blocked_zero_provider_weight')
  self.assertEqual(r['benchmarks']['Russell3000_proxy']['status'],'blocked_missing_source_provenance')
 def test_share_classes_weight_separately_but_issuer_counts_deduplicate(self):
  u=self.universe();sp=u['proxy_snapshots']['S&P1500_proxy'];sp['securities'][1]['cik']='1'
  records=self.records();records['1']['fields']['revenue'][0]['filed']='2026-11-09'
  r=proxy_coverage(u,records,'2026-11-12')['benchmarks']['S&P1500_proxy']
  self.assertEqual(r['unique_mapped_issuers'],1)
  self.assertEqual(r['field_issuer_coverage']['revenue'],1)
  self.assertEqual(r['field_weight_coverage_pct']['revenue'],100)
 def test_ingestion_main_persists_provider_snapshots_without_network(self):
  sp,iwv=self.sources()
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder)
   with patch.object(ingest,'OUT',root),patch.object(sys,'argv',['ingest','--limit','1']),patch.object(ingest,'get',return_value=b'{}'),patch.object(ingest,'parse_universe',return_value=sp),patch.object(ingest,'parse_russell',return_value=iwv),patch.object(ingest,'work_queue',return_value=[]),patch('builtins.print'):
    ingest.main()
   current=json.loads((root/'universe.json').read_text())
   self.assertEqual(current['proxy_snapshots']['Russell3000_proxy']['source_url'],iwv['source_url'])
   self.assertEqual(json.loads((root/'universes/2026-11-10.json').read_text()),current)
   self.assertEqual(json.loads((root/'status.json').read_text())['status'],'partial')

 def test_benchmark_cli_writes_separate_reports(self):
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);(root/'companyfacts').mkdir()
   (root/'universe.json').write_text(json.dumps(self.universe()))
   for cik,record in self.records().items():
    (root/'companyfacts'/(cik+'.json.gz')).write_bytes(gzip.compress(json.dumps(dict(record,cik=cik)).encode()))
   with patch.object(benchmark,'OUT',root),patch.object(sys,'argv',['benchmark','--as-of','2026-11-12']),patch('builtins.print'):
    benchmark.main()
   report=json.loads((root/'proxy_benchmark_coverage.json').read_text())
   self.assertEqual(report['benchmarks']['Russell3000_proxy']['field_weight_coverage_pct']['revenue'],20)
   self.assertEqual(report['benchmarks']['S&P1500_proxy']['field_weight_coverage_pct']['revenue'],0)
   self.assertIsNone(report['calculated_style'])

if __name__=='__main__' :unittest.main()
