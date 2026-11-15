import json
import pathlib
import sys
import tempfile
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from build_skunkworks import build

class SkunkworksTests(unittest.TestCase):
    def test_exact_versions_deduplicated_securities_and_failed_candidate_exclusion(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp); data=root/'CapitalSignal/data';(data/'atlas').mkdir(parents=True);(data/'13f').mkdir()
            period='2026-09-30'
            row={'entity_id':'0000000001','name':'A','report_date':period,'selected_accessions':['a'],'versions':[{'source':'https://www.sec.gov/example'}],'reported_matched_identifier_equity_value_usd':100,'security_count':1}
            bad=dict(row,entity_id='0000000002',selected_accessions=['wrong'])
            (data/'atlas/manifest.json').write_text(json.dumps({'updated_at':'now','lenses':{'managers':[{'report_date':period,'file':'managers.json'}]}}))
            (data/'atlas/managers.json').write_text(json.dumps({'managers':[row,bad]}))
            snapshot={'accession':'a','report_date':period,'value_unit':'USD','manager_cik':'0000000001','holdings':[{'cusip':'123456789','issuer':'X','value_usd':60,'shares':6},{'cusip':'123456789','issuer':'X','value_usd':40,'shares':4}]}
            (data/'13f/0000000001-2026-09-30.json').write_text(json.dumps(snapshot));(data/'13f/0000000002-2026-09-30.json').write_text(json.dumps(dict(snapshot,manager_cik='0000000002')))
            result=build(root)
            self.assertEqual(result['validated_count'],1);self.assertEqual(result['skipped'],['0000000002'])
            self.assertEqual(len(result['securities']),1);self.assertEqual(len(result['securities'][0]['holders']),1)
            self.assertEqual(result['portfolios'][0]['top1'],1);self.assertEqual(result['portfolios'][0]['hhi'],1)
            snapshot['value_unit']='thousands';(data/'13f/0000000001-2026-09-30.json').write_text(json.dumps(snapshot))
            self.assertEqual(build(root)['validated_count'],0)
