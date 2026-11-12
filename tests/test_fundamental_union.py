import pathlib
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from match_fundamental_portfolios import benchmark_diagnostics, match_positions
from market_inputs import audit_universe, acquire
import tempfile

class UnionTests(unittest.TestCase):
 def universe(self):
  return {'as_of':'2026-11-10','source_url':'https://example.test/sptm',
   'membership_basis':'current ETF holdings proxies, not official index membership',
   'universe_sources':[{'name':'SPTM','as_of':'2026-11-10'},{'name':'IWV','as_of':'2026-11-09'}],
   'securities':[{'cusip':'123','ticker':'AAA','cik':'1','weight_pct':60,'currency':'USD'},
                 {'cusip':None,'ticker':'BBB','cik':'2','weight_pct':80,'currency':'USD'}]}
 def test_union_does_not_mix_provider_weights(self):
  u=self.universe()
  with patch('match_fundamental_portfolios.snapshot',return_value={'revenue':{}}):
   r=benchmark_diagnostics(u,{'1':{},'2':{}})
  self.assertIsNone(r['field_weight_coverage_pct'])
  self.assertEqual(r['field_issuer_coverage'],{'revenue':2})
  self.assertEqual(r['universe_sources'],u['universe_sources'])
  self.assertIn('IWV',r['benchmark'])
 def test_single_proxy_coverage_includes_missing_fundamentals(self):
  u=self.universe();u.pop('universe_sources')
  with patch('match_fundamental_portfolios.snapshot',return_value={'revenue':{}}):
   r=benchmark_diagnostics(u,{'1':{}})
  self.assertAlmostEqual(r['field_weight_coverage_pct']['revenue'],100*60/140)
 def test_issuer_counts_do_not_double_count_share_classes(self):
  u=self.universe();u['securities'].append(dict(u['securities'][0],cusip='456'))
  with patch('match_fundamental_portfolios.snapshot',return_value={'revenue':{}}):
   r=benchmark_diagnostics(u,{'1':{}})
  self.assertEqual(r['unique_mapped_issuers'],2)
  self.assertEqual(r['field_issuer_coverage']['revenue'],1)
 def test_null_cusips_never_match(self):
  r=match_positions([{'cusip':None,'value_usd':100}],self.universe()['securities'],{},'2026-11-10')
  self.assertEqual(r['current_proxy_identifier_match_value_pct'],0)
  self.assertIsNone(r['positions'][0]['cik'])
 def test_conflicting_cusips_never_choose_last_issuer(self):
  members=[{'cusip':'123','cik':'1'},{'cusip':'123','cik':'2'}]
  r=match_positions([{'cusip':'123','value_usd':100}],members,{},'2026-11-10')
  self.assertEqual(r['current_proxy_identifier_match_value_pct'],0)
 def test_market_audit_retains_missing_identifier_without_matching_null_data(self):
  u=self.universe()
  r=audit_universe(u,{'prices':[{'security_id':None}]},u['as_of'])
  self.assertEqual(len(r),2)
  self.assertEqual(r[1]['blockers'],['missing_provider_sourced_cusip'])
  self.assertIsNone(r[1]['market_cap_usd'])
  self.assertIsNone(r[1]['security_id'])
 def test_acquisition_skips_missing_identifier_without_request(self):
  u=self.universe();u['securities']=u['securities'][1:]
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d)
   with patch('market_inputs.OUT',root),patch('market_inputs.ROOT',root.parent),patch('market_inputs.urllib.request.urlopen',side_effect=RuntimeError('offline')),patch('market_inputs.fetch_stooq_response') as fetch:
    r=acquire(u)
   fetch.assert_not_called()
   self.assertEqual(r['attempted_this_run'],0)
 def test_nonfinite_position_values_excluded(self):
  r=match_positions([{'value_usd':float('nan')},{'value_usd':True}],[],{},'2026-11-10')
  self.assertEqual(r['eligible_reported_value_usd'],0)
