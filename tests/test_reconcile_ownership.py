import json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from reconcile_ownership import aggregate, build


class ReconciliationTests(unittest.TestCase):
    def test_units_and_options_excluded(self):
        p,excluded=aggregate([{'cusip':'123456789','shares':'5','value_usd':50}, {'cusip':'123456789','shares':'2','value_usd':20}, {'cusip':'123456789','value_usd':100,'put_call':'Put'}, {'cusip':'999999999','value_thousands':12}])
        self.assertEqual(p['123456789']['shares'],7)
        self.assertEqual(p['123456789']['value_usd'],70)
        self.assertEqual(excluded['missing_or_invalid_dollar_value'],1)
    def test_fund_balance_is_not_assumed_shares(self):
        p,_=aggregate([{'cusip':'123456789','asset_category':'EC','reported_value_usd':10,'balance':'100'}],True)
        self.assertIsNone(p['123456789']['shares'])
    def test_two_views_never_added_even_with_same_cik(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory)
            for kind,key in [('13f','managers'),('funds','funds')]:
                (root/kind).mkdir()
                row={'accession':kind,'report_date':'2025-09-30','filing_date':'2025-10-01','file':'row.json'}
                if kind=='13f': row.update(manager_cik='0000000001',manager_name='Manager',holdings=[{'cusip':'123456789','value_usd':100,'shares':'10'}])
                else: row.update(registrant_cik='0000000001',fund_id='S1',fund_name='Fund',holdings=[{'cusip':'123456789','reported_value_usd':60,'asset_category':'EC','balance':'6'}])
                (root/kind/'index.json').write_text(json.dumps({key:[row]}));(root/kind/'row.json').write_text(json.dumps(row))
            r=build(root)
            self.assertEqual(r['counts']['potential_overlap_pairs'],1)
            self.assertIsNone(r['combined_ownership_value_usd'])
            self.assertIsNone(r['potential_overlaps'][0]['verified_overlap_value_usd'])
            self.assertEqual(r['managers'][0]['reported_matched_identifier_equity_value_usd'],100)
            self.assertEqual(r['funds'][0]['reported_matched_identifier_equity_value_usd'],60)
            historical=build(root,'2025-12-01')
            self.assertEqual(historical['counts']['fund_periods'],0)
            self.assertEqual(historical['counts']['manager_periods'],1)
