(function(root){
  'use strict';
  function number(v){if(v===null||v===''||typeof v==='boolean')return null;const n=Number(v);return Number.isFinite(n)&&n>=0?n:null;}
  function rows(data,kind,period,query=''){
    const seen=new Set(), duplicates=new Set(), q=query.trim().toLowerCase();
    const candidates=(data[kind]||[]).filter(r=>r.report_date===period);
    for(const r of candidates){if(seen.has(r.entity_id))duplicates.add(r.entity_id);seen.add(r.entity_id);}
    return candidates.filter(r=>!duplicates.has(r.entity_id)&&r.entity_id&&
        number(r.reported_matched_identifier_equity_value_usd)!==null&&number(r.security_count)!==null&&
        (!q||String(r.name||r.entity_id).toLowerCase().includes(q)||String(r.entity_id).includes(q)))
      .sort((a,b)=>b.reported_matched_identifier_equity_value_usd-a.reported_matched_identifier_equity_value_usd||String(a.entity_id).localeCompare(String(b.entity_id)));
  }
  function securities(snapshot,row){
    if(row.selected_accessions?.length!==1||snapshot.accession!==row.selected_accessions[0]||
       snapshot.report_date!==row.report_date||String(snapshot.manager_cik).padStart(10,'0')!==String(row.entity_id).padStart(10,'0')||
       snapshot.value_unit!=='USD'||snapshot.amendment_review_required||!Array.isArray(snapshot.holdings))
      throw Error('Source version, period, units or amendment gate is unmet. Open the SEC sources below.');
    const grouped=new Map();
    for(const h of snapshot.holdings){
      if(h.put_call||(h.share_type||'SH')!=='SH')continue;
      const cusip=String(h.cusip||'').trim().toUpperCase(),value=number(h.value_usd);
      if(!/^[A-Z0-9]{9}$/.test(cusip)||value===null)continue;
      const r=grouped.get(cusip)||{cusip,name:h.issuer||cusip,value:0,shares:0};
      r.value+=value;const shares=number(h.shares);r.shares=r.shares===null||shares===null?null:r.shares+shares;grouped.set(cusip,r);
    }
    const result=[...grouped.values()].sort((a,b)=>b.value-a.value),total=result.reduce((s,r)=>s+r.value,0);
    if(result.length!==row.security_count||Math.abs(total-row.reported_matched_identifier_equity_value_usd)>.011)
      throw Error('Holdings and summary generations differ. Reload after the next completed publication.');
    return {rows:result,total};
  }
  const api={rows,securities,number};if(typeof module!=='undefined')module.exports=api;else root.AtlasCore=api;
})(typeof window==='undefined'?globalThis:window);
