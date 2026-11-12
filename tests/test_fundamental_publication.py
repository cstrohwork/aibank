import datetime as dt
import gzip
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from publish_fundamental_checkpoint import DATA, merge_inputs, publish
from match_fundamental_portfolios import match_positions
from unittest import mock

def record(root, cik, age=0):
    path=root/'companyfacts'/(cik+'.json.gz');path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps({'cik':cik,'fields':{},'retrieved_at':(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=age)).isoformat()}).encode()))

def universe(root, ciks):
    root.mkdir(parents=True,exist_ok=True)
    (root/'universe.json').write_text(json.dumps({'as_of':'2026-11-10','retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat(),'securities':[{'cik':c} for c in ciks]}))

def git(root,*args):
    return subprocess.run(['git',*args],cwd=root,check=True,capture_output=True,text=True).stdout

class PublicationTests(unittest.TestCase):
    def test_snapshot_reused_across_portfolios_but_not_dates(self):
        cache={};holdings=[{'cusip':'same','value_usd':10}];members=[{'cusip':'same','cik':'1'}]
        with mock.patch('match_fundamental_portfolios.snapshot',return_value={}) as select:
            match_positions(holdings,members,{'1':{}},'2026-06-30',cache)
            match_positions(holdings,members,{'1':{}},'2026-06-30',cache)
            match_positions(holdings,members,{'1':{}},'2026-09-30',cache)
            self.assertEqual(select.call_count,2)

    def test_cache_union_keeps_newer_remote_and_excludes_analytics(self):
        with tempfile.TemporaryDirectory() as directory:
            source=pathlib.Path(directory)/'source';target=pathlib.Path(directory)/'target'
            record(source,'0000000001',5);record(target,'0000000001',1);record(source,'0000000002')
            (source/'benchmark_status.json').write_text('{"stale":true}')
            newer=(target/'companyfacts/0000000001.json.gz').read_bytes()
            merge_inputs(source,target)
            self.assertEqual(newer,(target/'companyfacts/0000000001.json.gz').read_bytes())
            self.assertTrue((target/'companyfacts/0000000002.json.gz').exists())
            self.assertFalse((target/'benchmark_status.json').exists())

    def test_publication_preserves_competing_writer_without_rebase(self):
        with tempfile.TemporaryDirectory() as directory:
            base=pathlib.Path(directory);remote=base/'origin.git';worker=base/'worker';other=base/'other';checkpoint=base/'saved'
            git(base,'init','--bare',str(remote));git(base,'clone',str(remote),str(worker))
            git(worker,'checkout','-b','main');git(worker,'config','user.name','Test');git(worker,'config','user.email','test@example.com')
            universe(worker/DATA,['0000000001','0000000002']);record(worker/DATA,'0000000001',1)
            (worker/DATA/'benchmark_status.json').write_text('{"version":1}')
            git(worker,'add','.');git(worker,'commit','-m','base');git(worker,'push','origin','main')
            universe(checkpoint,['0000000001','0000000002']);record(checkpoint,'0000000001',5);record(checkpoint,'0000000002')
            (checkpoint/'benchmark_status.json').write_text('{"version":"stale artifact"}')
            git(base,'clone','--branch','main',str(remote),str(other));git(other,'config','user.name','Other');git(other,'config','user.email','other@example.com')
            (other/DATA/'benchmark_status.json').write_text('{"version":2}')
            git(other,'add','.');git(other,'commit','-m','competing analytics');git(other,'push','origin','main')
            # Publishing begins with a stale checkout, precisely the failed cloud case.
            report=publish(worker,checkpoint)
            self.assertEqual(report['ingested_issuers'],2)
            self.assertEqual(json.loads((worker/DATA/'benchmark_status.json').read_text()),{'version':2})
            self.assertFalse((worker/'.git/rebase-merge').exists())
            self.assertEqual(git(worker,'rev-parse','HEAD'),git(worker,'rev-parse','origin/main'))

    def test_invalid_cache_rejected_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            source=pathlib.Path(directory)/'source';target=pathlib.Path(directory)/'target'
            record(source,'0000000001');path=source/'companyfacts/0000000001.json.gz'
            path.write_bytes(gzip.compress(b'{"cik":"wrong","fields":{}}'))
            with self.assertRaises(ValueError):merge_inputs(source,target)
