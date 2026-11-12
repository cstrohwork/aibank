import pathlib, sys, unittest, datetime as dt, shutil, subprocess, tempfile, gzip, json, contextlib, io
from unittest import mock
from html.parser import HTMLParser
from decimal import Decimal
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import build_model_data as model_module
from build_model_data import build as _build, company_model, annual_history
def build(u,r,e=None): return _build(u,r,e,checked_at=dt.datetime(2025,7,1,tzinfo=dt.timezone.utc))

def point(val,tag='Revenues',**kw):
    return dict(val=val,unit='USD',start='2024-01-01',end='2024-12-31',filed='2025-02-01',tag=tag,**kw)
def record():
    return {'cik':'0000000001','retrieved_at':'2025-07-01T00:00:00+00:00','fields':{'revenue':[point(100)],'net_income':[point(-5,'NetIncomeLoss')]}}
class ModelTests(unittest.TestCase):
    def universe(self): return {'as_of':'2025-06-30','retrieved_at':'2025-07-01T00:00:00+00:00','securities':[{'ticker':'X','cik':'0000000001'}]}
    def test_full_coverage_activates_even_loss_company(self):
        self.assertTrue(build(self.universe(),{'0000000001':record()})['activation']['ready'])
    def test_pending_blocks(self): self.assertFalse(build(self.universe(),{})['activation']['ready'])
    def test_unmapped_blocks_even_if_all_mapped_ingested(self):
        u=self.universe();u['securities'].append({'ticker':'Y','cik':None})
        self.assertFalse(build(u,{'0000000001':record()})['activation']['ready'])
    def test_no_annual_mismatch(self):
        r=record();r['fields']['net_income'][0]['end']='2024-11-30'
        self.assertFalse(company_model(r,'2025-06-30')['ready'])
    def test_no_future_restated_leak(self):
        r=record();p=point(900);p['filed']='2026-01-01';r['fields']['revenue'].append(p)
        self.assertEqual(company_model(r,'2025-06-30')['baseline']['facts']['revenue']['val'],100)
    def test_no_non_usd_or_nonfinite(self):
        r=record();r['fields']['revenue'][0]['unit']='EUR'
        self.assertFalse(company_model(r,'2025-06-30')['ready'])
        r['fields']['revenue'][0].update(unit='USD',val=float('nan'))
        self.assertFalse(company_model(r,'2025-06-30')['ready'])
    def test_stale_facts_block(self):
        r=record();r['retrieved_at']='2025-06-27T00:00:00+00:00'
        self.assertFalse(build(self.universe(),{'0000000001':r})['activation']['ready'])
    def test_stale_universe_blocks(self):
        u=self.universe();u['retrieved_at']='2025-06-27T00:00:00+00:00'
        self.assertFalse(build(u,{'0000000001':record()})['activation']['ready'])
    def test_empty_universe_blocks(self): self.assertFalse(build({'as_of':'2025-06-30','retrieved_at':'2025-07-01T00:00:00+00:00','securities':[]},{})['activation']['ready'])
    @unittest.skipUnless(shutil.which('node'), 'Node not installed')
    def test_scenarios_and_missing_fcf(self):
        core=str(pathlib.Path(__file__).resolve().parents[1]/'CapitalSignal/model/model-core.js')
        js='''const assert=require('assert'),{project}=require(process.argv[1]);
const b={end:'2024-12-31',facts:{revenue:{val:100},eps_diluted:{val:2}}},a={growth:10,margin:20,epsGrowth:5,fcfMargin:null,pe:15,ev:2,growthSpread:5,marginSpread:2};
const base=project(b,a,'base'),bull=project(b,a,'bull'),bear=project(b,a,'bear');
assert(Math.abs(base[0].revenue-110)<1e-9);assert.strictEqual(base[0].fcf,null);assert(Math.abs(base[0].netIncome-22)<1e-9);assert(bull[4].revenue>base[4].revenue&&base[4].revenue>bear[4].revenue);
b.facts.eps_diluted.val=-2;assert.strictEqual(project(b,a,'base')[4].impliedShareValue,null);
a.growth=-100;assert.throws(()=>project(b,a,'base'));a.growth=null;assert.throws(()=>project(b,a,'base'));a.growth=1e300;assert.throws(()=>project(b,a,'base'));a.growth=10;b.facts.revenue.val=1e308;assert.throws(()=>project(b,a,'base')); ''';
        subprocess.run(['node','-e',js,core],check=True,capture_output=True,text=True)
    def test_derived_margin_inputs_accept_unrounded_values(self):
        class Inputs(HTMLParser):
            def __init__(self): super().__init__(); self.inputs={}
            def handle_starttag(self, tag, attrs):
                a=dict(attrs)
                if tag=='input' and a.get('id'): self.inputs[a['id']]=a
        page=Inputs();page.feed((pathlib.Path(__file__).resolve().parents[1]/'CapitalSignal/model/index.html').read_text())
        for field, raw in [('margin',12.51543210987),('fcf-margin',19.44321987654)]:
            attrs=page.inputs[field]
            self.assertEqual(attrs['step'],'any')
            self.assertLess(float(attrs['min']),raw)
            self.assertGreater(float(attrs['max']),raw)
    def test_all_numeric_defaults_satisfy_input_constraints(self):
        class Inputs(HTMLParser):
            def __init__(self): super().__init__(); self.inputs=[]
            def handle_starttag(self, tag, attrs):
                a=dict(attrs)
                if tag=='input' and a.get('type')=='number' and 'value' in a: self.inputs.append(a)
        page=Inputs();page.feed((pathlib.Path(__file__).resolve().parents[1]/'CapitalSignal/model/index.html').read_text())
        self.assertGreater(len(page.inputs),0)
        for attrs in page.inputs:
            with self.subTest(field=attrs['id']):
                value=Decimal(attrs['value'])
                if 'min' in attrs: self.assertGreaterEqual(value,Decimal(attrs['min']))
                if 'max' in attrs: self.assertLessEqual(value,Decimal(attrs['max']))
                if attrs.get('step')!='any':
                    step=Decimal(attrs.get('step','1'));base=Decimal(attrs.get('min',attrs.get('value','0')))
                    self.assertEqual((value-base)%step,0)
    def test_generated_histories_are_lazy_and_status_published_last(self):
        with tempfile.TemporaryDirectory() as temp:
            out=pathlib.Path(temp);(out/'companyfacts').mkdir()
            (out/'universe.json').write_text(json.dumps(self.universe()))
            (out/'companyfacts/0000000001.json.gz').write_bytes(gzip.compress(json.dumps(record()).encode()))
            writes=[];real_dump=model_module.dump
            def track(path, value): writes.append(path.name);real_dump(path,value)
            with mock.patch.object(model_module,'OUT',out),mock.patch.object(model_module,'dump',side_effect=track),contextlib.redirect_stdout(io.StringIO()): model_module.main()
            index=json.loads((out/'model_data.json').read_text());status=json.loads((out/'model_status.json').read_text())
            company=json.loads((out/'model_companies/0000000001.json').read_text())
            self.assertNotIn('history',index['companies']['0000000001'])
            self.assertEqual(index['companies']['0000000001']['data_file'],'model_companies/0000000001.json')
            self.assertIn('history',company)
            self.assertEqual(company['dataset_updated_at'],index['updated_at'])
            self.assertEqual(status['updated_at'],index['updated_at'])
            self.assertEqual(writes[-1],'model_status.json')
    def test_error_blocks(self): self.assertFalse(build(self.universe(),{'0000000001':record()},[{'error':'bad'}])['activation']['ready'])
if __name__=='__main__':unittest.main()
