#!/usr/bin/env python3
"""Begin benchmark/portfolio joins without applying current membership to history."""
import collections, datetime as dt, gzip, json, pathlib, math
from ingest_sp1500_fundamentals import OUT, ROOT, dump, now, snapshot

def match_positions(holdings, members, records, report_date, fact_cache=None):
 # A missing or conflicting identifier is not evidence of an issuer match.
 candidates=collections.defaultdict(list)
 for member in members:
  if member.get('cusip'):candidates[member['cusip']].append(member)
 by_cusip={cusip:rows[0] for cusip,rows in candidates.items()
           if len({r.get('cik') for r in rows})==1}
 total=matched=fundamental=0.; weighted=collections.defaultdict(float);covered=collections.defaultdict(float)
 matched_rows=[]
 for h in holdings:
  if h.get('put_call') or h.get('share_type','SH')!='SH':continue
  # Never interpret older ambiguous value_thousands as dollars here.
  value=h.get('value_usd')
  if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:continue
  total+=value;s=by_cusip.get(h.get('cusip'));cik=s.get('cik') if s else None
  if s: matched+=value
  if cik in records:
   if fact_cache is None:facts=snapshot(records[cik],report_date)
   else:
    cache_key=(cik,report_date)
    if cache_key not in fact_cache:fact_cache[cache_key]=snapshot(records[cik],report_date)
    facts=fact_cache[cache_key]
  else:facts={}
  if facts: fundamental+=value
  matched_rows.append({'cusip':h.get('cusip'),'cik':cik,'value_usd':value,'fields_available':sorted(facts)})
  # Exposure-weighted issuer ratios; never sum full issuer financials across holdings.
  for name,numerator,denominator in [('net_margin','net_income','revenue'),('operating_margin','operating_income','revenue')]:
   a,b=facts.get(numerator),facts.get(denominator)
   if a and b and a.get('start')==b.get('start') and a['end']==b['end'] and b['val']>0:
    weighted[name]+=value*a['val']/b['val'];covered[name]+=value
 return {'eligible_reported_value_usd':total,'current_proxy_identifier_match_value_pct':100*matched/total if total else None,'any_fundamentals_value_coverage_pct':100*fundamental/total if total else None,'portfolio_ratios':{k:{'value':weighted[k]/covered[k],'coverage_pct':100*covered[k]/total,'basis':'market-value-weighted issuer annual ratio; available filings as of portfolio date'} for k in covered},'positions':matched_rows}
def benchmark_diagnostics(universe,records):
 """A union's first-provider weights cannot define a combined benchmark."""
 union=bool(universe.get('universe_sources'))
 issuers={s['cik'] for s in universe['securities'] if s.get('cik')}
 field_counts=collections.Counter()
 for cik in issuers:
  if cik in records:field_counts.update(snapshot(records[cik],universe['as_of']).keys())
 weights=collections.Counter();total=0.
 if not union:
  for member in universe['securities']:
   weight=member.get('weight_pct')
   if isinstance(weight,bool) or not isinstance(weight,(int,float)) or not math.isfinite(weight) or weight<=0:continue
   total+=weight
   if member.get('cik') in records:
    for field in snapshot(records[member['cik']],universe['as_of']):weights[field]+=weight
 return {'updated_at':now(),
  'benchmark':'Current SPTM and IWV ETF holdings proxy union' if union else 'S&P Composite 1500 via SPTM ETF holdings proxy',
  'as_of':universe['as_of'],'source_url':universe['source_url'],
  'universe_sources':universe.get('universe_sources',[]),
  'membership_basis':universe['membership_basis'],
  'unique_mapped_issuers':len(issuers),'field_issuer_coverage':dict(field_counts),
  'field_weight_coverage_pct':None if union else {k:100*v/total for k,v in weights.items()} if total else {},
  'weight_coverage_status':'blocked_union_has_no_common_benchmark_weights' if union else 'single_proxy_weights',
  'style_calculation_status':'blocked_missing_point_in_time_price_market_cap_sector_inputs',
  'historical_benchmark_status':'historical_membership_not_yet_available'}

def main():
 universe=json.loads((OUT/'universe.json').read_text());records={}
 for path in (OUT/'companyfacts').glob('*.json.gz'):
  r=json.loads(gzip.decompress(path.read_bytes()));records[r['cik']]=r
 dump(OUT/'benchmark_status.json',benchmark_diagnostics(universe,records))
 index=json.loads((ROOT/'CapitalSignal/data/13f/index.json').read_text());latest={}
 for e in index['managers']:
  cik=e['manager_cik']
  if cik not in latest or e['report_date']>latest[cik]['report_date']:latest[cik]=e
 profiles=[];missing=0;fact_cache={}
 for e in latest.values():
  path=ROOT/'CapitalSignal/data/13f'/e['file']
  if not path.exists():missing+=1;continue
  data=json.loads(path.read_text());r=match_positions(data['holdings'],universe['securities'],records,e['report_date'],fact_cache)
  r.pop('positions')
  r.update(manager_cik=e['manager_cik'],report_date=e['report_date'],identifier_mapping_basis='current proxy union with provider-sourced CUSIPs only; missing/conflicting identifiers unmatched; no historical membership inferred',benchmark_comparison_status='pending_historical_benchmark' if e['report_date']!=universe['as_of'] else 'pending_prices_and_sector_data',calculated_style=None)
  profiles.append(r)
 dump(OUT/'portfolio_diagnostics.json',{'updated_at':now(),'profiles':profiles,'missing_cached_portfolio_files':missing,'status':'initial_identifier_matching_and_fundamental_ratio_diagnostics_only','production_classification_status':'pending_70pct_both_dimension_coverage_and_point_in_time_benchmark','editorial_labels':'unchanged'})
 print(f'Matched {len(profiles)} cached portfolios; {missing} files unavailable')
if __name__=='__main__':main()
