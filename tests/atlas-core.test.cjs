const test=require('node:test'),assert=require('node:assert/strict');
const core=require('../CapitalSignal/atlas/atlas-core.js');
const row={entity_id:'0000000001',name:'Example',report_date:'2026-09-30',security_count:1,selected_accessions:['a'],reported_matched_identifier_equity_value_usd:25};
const snapshot={manager_cik:'1',report_date:row.report_date,accession:'a',value_unit:'USD',holdings:[{cusip:'123456789',issuer:'Example',shares:2,value_usd:10},{cusip:'123456789',issuer:'Example',shares:3,value_usd:15},{cusip:'987654321',put_call:'PUT',value_usd:100}]};
test('periods, fund and manager views and duplicate identities never mix',()=>{
 const data={managers:[row,{...row,report_date:'2026-06-30',reported_matched_identifier_equity_value_usd:99}],funds:[{...row,entity_id:'S1'}]};
 assert.equal(core.rows(data,'managers',row.report_date).length,1);assert.equal(core.rows(data,'funds',row.report_date)[0].entity_id,'S1');assert.equal(core.rows(data,'managers',row.report_date,'missing').length,0);
 data.managers.push({...row});assert.equal(core.rows(data,'managers',row.report_date).length,0);
});
test('same-CUSIP positions aggregate and options do not become equity shares',()=>{const r=core.securities(snapshot,row);assert.equal(r.total,25);assert.equal(r.rows.length,1);assert.equal(r.rows[0].shares,5);});
test('unknown units, mismatched source, multi-version selections and changed summaries block',()=>{
 for(const patch of [{value_unit:null},{accession:'b'},{report_date:'2026-06-30'},{manager_cik:'2'},{amendment_review_required:true}])assert.throws(()=>core.securities({...snapshot,...patch},row));
 assert.throws(()=>core.securities(snapshot,{...row,selected_accessions:['a','b']}));assert.throws(()=>core.securities(snapshot,{...row,reported_matched_identifier_equity_value_usd:24}));assert.throws(()=>core.securities(snapshot,{...row,security_count:2}));
});
test('unknown shares stay unknown and nonfinite values do not enter chart',()=>{
 assert.equal(core.securities({...snapshot,holdings:snapshot.holdings.map((h,i)=>i? h:{...h,shares:null})},row).rows[0].shares,null);
 assert.equal(core.rows({managers:[{...row,reported_matched_identifier_equity_value_usd:Infinity}]},'managers',row.report_date).length,0);assert.equal(core.number(null),null);
});
