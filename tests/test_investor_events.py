import gzip,hashlib,json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from parse_investor_events import parse_submission,read_body,run

def submission(xml):return ('<DOCUMENT><FILENAME>primary.xml\n<TEXT><XML>'+xml+'</XML></TEXT></DOCUMENT>').encode()
class EventsTests(unittest.TestCase):
 def test_joint_amendment_not_summed(self):
  xml='<r xmlns="urn:sec"><issuerCIK>123</issuerCIK><issuerName>Issuer</issuerName><transactionPurpose>May consider discussions.</transactionPurpose>'+''.join('<reportingPersonInfo><reportingPersonName>'+n+'</reportingPersonName><aggregateAmountOwned>1,000</aggregateAmountOwned><percentOfClass>5.1</percentOfClass></reportingPersonInfo>' for n in ['Fund','Manager'])+'</r>'
  d=parse_submission(submission(xml),{'form':'SCHEDULE 13D/A','accession':'a'})
  self.assertEqual(len(d['ownership']),2);self.assertEqual(d['ownership'][0]['beneficial_shares'],1000);self.assertTrue(d['ownership'][0]['is_amendment']);self.assertIsNone(d['ownership'][0]['activist_intent'])
 def test_split_votes_keep_record_shares(self):
  d=parse_submission(submission('<proxyVoteTable xmlns="urn:sec"><proxyTable><issuerName>A</issuerName><meetingDate>05/01/2025</meetingDate><sharesVoted>100</sharesVoted><vote><voteRecord><howVoted>FOR</howVoted><sharesVoted>60</sharesVoted></voteRecord><voteRecord><howVoted>AGAINST</howVoted><sharesVoted>40</sharesVoted></voteRecord></vote></proxyTable></proxyVoteTable>'),{'form':'N-PX','accession':'a'})
  self.assertEqual([v['shares_voted'] for v in d['votes']],[60,40]);self.assertEqual(d['votes'][0]['meeting_date'],'05/01/2025')
 def test_checksum_and_bounded_gzip(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);raw=b'a'*100;(root/'a.gz').write_bytes(gzip.compress(raw));r={'raw_file':'a.gz','sha256':hashlib.sha256(raw).hexdigest()}
   self.assertEqual(read_body(root,r,{},200),raw)
   with self.assertRaisesRegex(ValueError,'budget'):read_body(root,r,{},10)
   r['sha256']='bad'
   with self.assertRaisesRegex(ValueError,'checksum'):read_body(root,r,{},200)
 def test_missing_body_not_empty_success(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);(root/'history').mkdir();(root/'history/archive_state.json.gz').write_bytes(gzip.compress(json.dumps({'a':{'accession':'a','form':'N-PX','status':'archived','raw_file':'missing.gz'}}).encode()))
   d=run(root);self.assertEqual(d['status'],'partial');self.assertEqual(d['summary']['unavailable_filings'],1);self.assertEqual(d['summary']['parsed_filings'],0)
 def test_checkpoint_preserves_records_and_advances(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);(root/'history').mkdir();state={}
   for accession in ('a','b'):
    raw=submission('<r><reportingPersonInfo><reportingPersonName>Fund</reportingPersonName><aggregateAmountOwned>10</aggregateAmountOwned></reportingPersonInfo></r>')
    (root/(accession+'.gz')).write_bytes(gzip.compress(raw));state[accession]={'accession':accession,'form':'SCHEDULE 13D','status':'archived','raw_file':accession+'.gz','sha256':hashlib.sha256(raw).hexdigest()}
   (root/'history/archive_state.json.gz').write_bytes(gzip.compress(json.dumps(state).encode()))
   first=run(root,limit=1);self.assertEqual(first['summary']['parsed_filings'],1)
   (root/'intelligence').mkdir();(root/'intelligence/parsed_events.json').write_text(json.dumps(first))
   second=run(root,limit=1)
   self.assertEqual(second['summary']['previously_parsed_filings'],1)
   self.assertEqual(second['summary']['parsed_filings'],2)
   self.assertEqual(len(second['beneficial_ownership']),2)
   self.assertEqual({f['accession'] for f in second['filings']},{'a','b'})
   (root/'intelligence/parsed_events.json').write_text(json.dumps(second))
   third=run(root,limit=1)
   self.assertEqual(third['status'],'parsed_cached_candidates')
   self.assertEqual(third['summary']['selected_filings'],0)
 def test_unchanged_unsupported_is_retained_without_reacquisition(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);(root/'history').mkdir();(root/'intelligence').mkdir()
   r={'accession':'a','form':'N-PX','status':'archived','raw_file':'missing.gz','sha256':'abc'}
   (root/'history/archive_state.json.gz').write_bytes(gzip.compress(json.dumps({'a':r}).encode()))
   old={'filings':[{'accession':'a','parse_status':'unsupported_or_no_extracted_records','parser_version':1,'source_sha256':'abc'}]}
   (root/'intelligence/parsed_events.json').write_text(json.dumps(old))
   result=run(root)
   self.assertEqual(result['summary']['selected_filings'],0)
   self.assertEqual(result['summary']['unsupported_filings'],1)
   self.assertEqual(result['status'],'partial')
if __name__=='__main__':unittest.main()
