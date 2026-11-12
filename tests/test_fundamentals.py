import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from ingest_sp1500_fundamentals import snapshot,extract
from match_fundamental_portfolios import match_positions
class FundamentalsTests(unittest.TestCase):
 def record(self):
  return {'fields':{'revenue':[{'val':100,'start':'2024-01-01','end':'2024-12-31','filed':'2025-02-01','unit':'USD','tag':'Revenues'},{'val':900,'start':'2024-01-01','end':'2024-12-31','filed':'2026-02-01','unit':'USD','tag':'Revenues'},{'val':25,'start':'2025-01-01','end':'2025-03-31','filed':'2025-05-01','unit':'USD','tag':'Revenues'}]}}
 def test_no_future_or_quarter_as_annual(self):
  self.assertEqual(snapshot(self.record(),'2025-06-30')['revenue']['val'],100)
 def test_restatement_available_only_after_filing(self):
  self.assertEqual(snapshot(self.record(),'2026-06-30')['revenue']['val'],900)
 def test_missing_unit_is_not_converted(self):
  r=self.record();r['fields']['revenue'][0]['unit']='EUR'
  self.assertEqual(snapshot(r,'2025-03-01'),{})
 def test_option_and_ambiguous_value_excluded(self):
  h=[{'cusip':'123','value_usd':100,'put_call':'PUT'},{'cusip':'123','value_thousands':100}]
  self.assertEqual(match_positions(h,[],{},'2025-06-30')['eligible_reported_value_usd'],0)
 def test_coverage_uses_all_eligible_value(self):
  h=[{'cusip':'123','value_usd':30},{'cusip':'456','value_usd':70}]
  r=match_positions(h,[{'cusip':'123','cik':'1'}],{'1':self.record()},'2025-06-30')
  self.assertEqual(r['any_fundamentals_value_coverage_pct'],30)
 def test_mismatched_periods_do_not_create_ratio(self):
  r=self.record();r['fields']['net_income']=[dict(r['fields']['revenue'][0],val=10,tag='NetIncomeLoss',end='2024-11-30')]
  h=[{'cusip':'123','value_usd':100}]
  self.assertEqual(match_positions(h,[{'cusip':'123','cik':'1'}],{'1':r},'2025-06-30')['portfolio_ratios'],{})
if __name__=='__main__':unittest.main()
