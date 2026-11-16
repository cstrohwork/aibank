import copy
import hashlib
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
from match_fundamental_portfolios import portfolio_gates

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
  self.assertNotIn('not yet available',u['membership_basis'])
  self.assertIn('stored separately',u['membership_basis'])
  self.assertIn('not part of proxy membership',u['membership_basis'])
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

 def test_large_megacap_requires_dated_cap_us_exchange_and_sec_identity(self):
  payload={'as_of':'2026-11-12','data':{'rows':[
   {'symbol':'AAA','name':'Already proxied','marketCap':'$20B','exchange':'Nasdaq','sector':'Tech'},
   {'symbol':'ZZZ','name':'Outside issuer','marketCap':'15000000000','exchange':'NYSE','sector':'Industrials'},
   {'symbol':'OTC','name':'Wrong venue','marketCap':'$30B','exchange':'OTC','sector':'Health'},
   {'symbol':'SMOL','name':'Below floor','marketCap':'$5B','exchange':'NASDAQ','sector':'Tech'},
   {'symbol':'AMB','name':'Ambiguous','marketCap':'$12B','exchange':'NYSE','sector':'Finance'}]}}
  blob=json.dumps(payload).encode();tickers={
   '0':{'ticker':'AAA','cik_str':1},'1':{'ticker':'ZZZ','cik_str':9},'2':{'ticker':'OTC','cik_str':8},
   '3':{'ticker':'SMOL','cik_str':7},'4':{'ticker':'AMB','cik_str':5},'5':{'ticker':'AMB','cik_str':6}}
  observed='2026-11-15T12:30:00Z'
  screen=ingest.parse_large_megacap(blob,tickers,observed,enforce_safety=False)
  outside=ingest.outside_proxy_large_megacap(screen,{'securities':[{'ticker':'AAA'}]})
  self.assertEqual([s['ticker'] for s in outside['securities']],['ZZZ'])
  row=outside['securities'][0]
  self.assertEqual(row['market_cap_usd'],15_000_000_000)
  self.assertEqual(row['market_cap_as_of'],'2026-11-12')
  self.assertEqual(row['exchange'],'NYSE')
  self.assertEqual(row['cik'],'0000000009')
  self.assertEqual(row['market_cap_observed_at'],'2026-11-15T12:30:00+00:00')
  self.assertEqual(outside['source_sha256'],hashlib.sha256(blob).hexdigest())
  self.assertIn('not historical',outside['scope'])
  reasons={x['reason'] for x in outside['excluded_screen_rows']}
  self.assertIn('unverified_us_exchange_listing',reasons)
  self.assertIn('no_unique_current_sec_ticker_match',reasons)

 def test_large_megacap_rejects_nonfinite_and_conflicting_rows(self):
  self.assertIsNone(ingest.parse_market_cap('NaN'))
  self.assertIsNone(ingest.parse_market_cap('Infinity'))
  payload={'as_of':'2026-11-12','data':{'rows':[
   {'symbol':'ZZZ','name':'Outside','marketCap':'$15B','exchange':'NYSE'},
   {'symbol':'ZZZ','name':'Outside','marketCap':'$16B','exchange':'NYSE'}]}}
  with self.assertRaisesRegex(ValueError,'Conflicting large/mega-cap screener rows'):
   ingest.parse_large_megacap(json.dumps(payload).encode(),{'0':{'ticker':'ZZZ','cik_str':9}},'2026-11-15T12:30:00Z',enforce_safety=False)

 def test_ingestion_queues_verified_outside_proxy_issuer_separately(self):
  sp,iwv=self.sources();captured=[]
  screen={'as_of':'2026-11-15','retrieved_at':'2026-11-15T12:30:00+00:00','source_url':ingest.NASDAQ_SCREENER,
   'source_sha256':'b'*64,'market_cap_floor_usd':ingest.LARGE_CAP_MIN_USD,'excluded_rows':[],
   'securities':[{'ticker':'ZZZ','name':'Outside','cik':'0000000009','exchange':'NYSE','market_cap_usd':15_000_000_000,
    'market_cap_as_of':'2026-11-12','market_cap_retrieved_at':'2026-11-15T12:30:00+00:00',
    'market_cap_observed_at':'2026-11-15T12:30:00+00:00','market_cap_source_url':ingest.NASDAQ_SCREENER,
    'market_cap_source_sha256':'b'*64,'exchange_listing_source_url':ingest.NASDAQ_SCREENER,
    'exchange_listing_source_sha256':'b'*64}]}
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder)
   def queue(ciks,*args):captured.extend(ciks);return []
   with patch.object(ingest,'OUT',root),patch.object(sys,'argv',['ingest','--limit','1']),patch.object(ingest,'get',return_value=b'{}'),patch.object(ingest,'parse_universe',return_value=sp),patch.object(ingest,'parse_russell',return_value=iwv),patch.object(ingest,'fetch_large_megacap',return_value=(b'{}','2026-11-15T12:30:00+00:00')),patch.object(ingest,'parse_large_megacap',return_value=screen),patch.object(ingest,'work_queue',side_effect=queue),patch('builtins.print'):
    ingest.main()
   status=json.loads((root/'status.json').read_text())
   supplement=json.loads((root/'large_megacap_outside_proxies.json').read_text())
   self.assertIn('0000000009',captured)
   self.assertEqual(status['unique_mapped_issuers'],3)
   self.assertEqual(status['fundamental_ingestion_unique_issuers'],4)
   self.assertEqual(status['supplemental_large_megacap']['security_count'],1)
   self.assertEqual(supplement['securities'][0]['universe_memberships'],['large_megacap_outside_current_etf_proxies'])

 def test_large_megacap_fetches_each_exchange_with_dated_raw_provenance(self):
  self.assertTrue(all('marketcap=mega%7Clarge' in url for url in ingest.NASDAQ_EXCHANGE_SOURCES.values()))
  blobs={}
  for exchange,base_url in ingest.NASDAQ_EXCHANGE_SOURCES.items():
   for offset,count in ((0,2),(2,1)):
    url=f'{base_url}&limit=2&offset={offset}'
    rows=[{'symbol':f'{exchange[:2]}{offset+i}','name':exchange,'marketCap':'15000000000'} for i in range(count)]
    blobs[url]=json.dumps({'data':{'table':{'rows':rows},'totalrecords':3,
     'asof':'Last price as of Nov 12, 2026'}}).encode()
  with patch.object(ingest,'NASDAQ_PAGE_SIZE',2),patch.object(ingest,'get',side_effect=lambda url:blobs[url]),patch.object(ingest,'now',return_value='2026-11-15T12:30:00+00:00'):
   blob,observed=ingest.fetch_large_megacap()
  payload=json.loads(blob)
  self.assertEqual(observed,'2026-11-15T12:30:00+00:00')
  self.assertEqual(payload['as_of'],'2026-11-12')
  self.assertEqual(len(payload['data']['rows']),9)
  self.assertEqual(len(payload['sources']),6)
  self.assertEqual({s['exchange'] for s in payload['sources']},{'NASDAQ','NYSE','NYSE AMERICAN'})
  self.assertEqual({s['offset'] for s in payload['sources']},{0,2})
  self.assertTrue(all(s['total_records']==3 for s in payload['sources']))
  for source in payload['sources']:
   self.assertEqual(source['sha256'],hashlib.sha256(blobs[source['url']]).hexdigest())

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

 def test_portfolio_gate_publishes_separate_proxy_dates_and_blocks_misaligned_union(self):
  universe=self.universe()
  result={'current_proxy_identifier_match_value_pct':90,
   'any_fundamentals_value_coverage_pct':85,'portfolio_ratios':{}}
  gate=portfolio_gates(result,'2026-11-12',universe)['point_in_time_gate']
  self.assertEqual(gate['proxy_snapshots_as_of'],{
   'S&P1500_proxy':'2026-11-10','Russell3000_proxy':'2026-11-12'})
  self.assertIsNone(gate['common_proxy_snapshot_as_of'])
  self.assertIsNone(gate['proxy_snapshot_as_of'])
  self.assertFalse(gate['same_date_current_proxy_gate_passed'])
  self.assertEqual(gate['status'],'blocked_misaligned_current_proxy_snapshots')

 def test_portfolio_gate_requires_all_valid_provider_dates_before_same_date_pass(self):
  universe=self.universe()
  universe['proxy_snapshots']['S&P1500_proxy']['as_of']='2026-11-12'
  result={'current_proxy_identifier_match_value_pct':90,
   'any_fundamentals_value_coverage_pct':85,'portfolio_ratios':{}}
  gate=portfolio_gates(result,'2026-11-12',universe)['point_in_time_gate']
  self.assertEqual(gate['common_proxy_snapshot_as_of'],'2026-11-12')
  self.assertTrue(gate['same_date_current_proxy_gate_passed'])
  self.assertEqual(gate['status'],'current_proxy_same_date_diagnostics_only')
  universe['proxy_snapshots']['Russell3000_proxy']['as_of']='not-a-date'
  gate=portfolio_gates(result,'2026-11-12',universe)['point_in_time_gate']
  self.assertFalse(gate['all_proxy_snapshot_dates_valid'])
  self.assertFalse(gate['same_date_current_proxy_gate_passed'])
  self.assertEqual(gate['status'],'blocked_missing_or_invalid_proxy_snapshot_dates')

if __name__=='__main__' :unittest.main()
