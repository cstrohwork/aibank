import json
import pathlib
import sys
import tempfile
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from build_identity_master import build, cik_id, cusip_valid, publish_sharded, read_sharded

class IdentityTests(unittest.TestCase):
    def test_identifiers(self):
        self.assertEqual(cik_id('320193'),'cik:0000320193')
        self.assertIsNone(cik_id('0'))
        self.assertIsNone(cik_id('APPLE'))
        self.assertTrue(cusip_valid('037833100'))
        self.assertFalse(cusip_valid('037833101'))

    def test_conflicts_history_roles_and_no_fuzzy_parent(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            def write(p,d):
                path=root/p;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(d))
            write('fundamentals/universe.json',{'as_of':'2026-01-01','securities':[{'cusip':'037833100','name':'APPLE','cik':'320193','ticker':'AAPL'}, {'cusip':'037833100','name':'CONFLICT','cik':'1'}]})
            write('13f/index.json',{'managers':[{'manager_cik':'320193','manager_name':'APPLE','report_date':'2025-09-30','file':'a.json'}]})
            write('13f/a.json',{'holdings':[{'cusip':'037833100','issuer':'Apple shares','class':'COM'},{'cusip':'NOTVALID!','issuer':'Other'}]})
            write('funds/index.json',{'funds':[{'series_id':'S000000001','fund_name':'APPLE INDEX','registrant_cik':'2','registrant_name':'APPLE','report_date':'2025-09-30','file':'missing.json'}]})
            result=build(root)
            apple=next(e for e in result['entities'] if e['id']=='cik:0000320193')
            self.assertEqual(apple['roles'],['13f_manager','issuer'])
            self.assertEqual(result['ambiguous_security_issuer_mappings']['cusip:037833100'],['cik:0000000001','cik:0000320193'])
            self.assertTrue(all(m['valid_from'] is None and m['resolution_status']=='quarantined_conflicting_issuer' for m in result['security_issuer_observations']))
            self.assertEqual(result['relationships'][0]['parent_id'],'cik:0000000002')
            self.assertEqual(result['relationships'][0]['relationship'],'registered_under')
            self.assertEqual(len(result['relationships']),1)
            self.assertEqual(len(result['missing_cached_files']),1)
            self.assertTrue(any(q['reason']=='invalid_or_missing_cusip' for q in result['quarantine']))
            self.assertEqual(result,build(root))

    def test_share_classes_stay_distinct(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);(root/'fundamentals').mkdir()
            (root/'fundamentals/universe.json').write_text(json.dumps({'as_of':'2026-01-01','securities':[{'cusip':'02079K305','cik':'1652044','ticker':'GOOGL'},{'cusip':'02079K107','cik':'1652044','ticker':'GOOG'}]}))
            result=build(root)
            self.assertEqual(len(result['entities']),1)
            self.assertEqual(len(result['securities']),2)

    def test_source_series_lei_creates_distinct_fund_entity(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);(root/'funds').mkdir()
            lei='529900TOB3V09W4JX713'
            (root/'funds/index.json').write_text(json.dumps({'funds':[{
                'fund_id':'LEI'+lei,'series_id':None,
                'identity_basis':'sec_series_lei_without_series_id',
                'fund_name':'Named Portfolio','registrant_cik':'2',
                'registrant_name':'Registrant','report_date':'2025-09-30',
                'source':'SEC original','file':'missing.json'}]}))
            result=build(root)
            fund=next(e for e in result['entities'] if e['id']=='fund:lei:'+lei)
            self.assertEqual(fund['roles'],['fund'])
            self.assertEqual(result['relationships'][0]['child_id'],'fund:lei:'+lei)
            self.assertEqual(result['relationships'][0]['parent_id'],'cik:0000000002')
            self.assertFalse(any(q['reason']=='unverified_fund_identity' for q in result['quarantine']))

    def test_matching_name_zero_series_lei_basis_keeps_registrant_scoped_fund(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);(root/'funds').mkdir()
            (root/'funds/index.json').write_text(json.dumps({'funds':[{
                'fund_id':'CIK0002059105','series_id':None,
                'identity_basis':'matching_registrant_series_name_zero_placeholder_series_lei',
                'fund_name':'StepStone Private Credit Co-Investment Fund',
                'registrant_cik':'0002059105','registrant_name':'StepStone Private Credit Co-Investment Fund',
                'report_date':'2026-06-30','source':'SEC original','file':'missing.json'}]}))
            result=build(root)
            self.assertTrue(any(e['id']=='fund:registrant:0002059105' for e in result['entities']))
            self.assertFalse(any(q['reason']=='unverified_fund_identity' for q in result['quarantine']))

    def test_sharded_publication_round_trip_checksum_and_size_bound(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);(root/'fundamentals').mkdir()
            rows=[]
            for number in range(40):
                rows.append({'cusip':'037833100','cik':'320193','ticker':'AAPL',
                             'name':'APPLE '+('X'*number)})
            (root/'fundamentals/universe.json').write_text(json.dumps({'as_of':'2026-01-01','securities':rows}))
            result=build(root);result['generated_at']='2026-11-14T13:00:00+00:00'
            result['quarantine']=[{'reason':'explicit_fixture_gap','identifier':str(i),
                                   'source':'fixture','observation_count':1} for i in range(100)]
            out=root/'intelligence';out.mkdir()
            manifest=publish_sharded(result,out,target_bytes=5000)
            rebuilt=read_sharded(out/'identity_master.json')
            self.assertEqual(rebuilt,result)
            shards=[s for group in manifest['collections'].values() for s in group['shards']]
            self.assertTrue(all(s['bytes']<=5000 for s in shards))
            self.assertGreater(len(shards),len(manifest['collections']))
            self.assertLess((out/'identity_master.json').stat().st_size,100_000)
            first=out/shards[0]['path']
            first.write_bytes(first.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'checksum/size mismatch'):
                read_sharded(out/'identity_master.json')

if __name__=='__main__':unittest.main()
