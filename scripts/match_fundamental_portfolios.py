#!/usr/bin/env python3
"""Begin benchmark/portfolio joins without applying current membership to history."""
import collections, datetime as dt, gzip, json, pathlib
from ingest_sp1500_fundamentals import OUT, ROOT, dump, now, snapshot

def match_positions(holdings, members, records, report_date):
 by_cusip={s['cusip']:s for s in members}
 total=matched=fundamental=0.; weighted=collections.defaultdict(float);covered=collections.defaultdict(float)
 matched_rows=[]
 for h in holdings:
  if h.get('put_call') or h.get('share_type','SH')!='SH':continue
  # Never interpret older ambiguous value_thousands as dollars here.
  value=h.get('value_usd')
  if not isinstance(value,(int,float)) or value<=0:continue
  total+=value;s=by_cusip.get(h.get('cusip'));cik=s.get('cik') if s else None
  if s: matched+=value
  facts=snapshot(records[cik],report_date) if cik in records else {}
  if facts: fundamental+=value
  matched_rows.append({'cusip':h.get('cusip'),'cik':cik,'value_usd':value,'fields_available':sorted(facts)})
  # Exposure-weighted issuer ratios; never sum full issuer financials across holdings.
  for name,numerator,denominator in [('net_margin','net_income','revenue'),('operating_margin','operating_income','revenue')]:
   a,b=facts.get(numerator),facts.get(denominator)
   if a and b and a.get('start')==b.get('start') and a['end']==b['end'] and b['val']>0:
    weighted[name]+=value*a['val']/b['val'];covered[name]+=value
 return {'eligible_reported_value_usd':total,'current_proxy_identifier_match_value_pct':100*matched/total if total else None,'any_fundamentals_value_coverage_pct':100*fundamental/total if total else None,'portfolio_ratios':{k:{'value':weighted[k]/covered[k],'coverage_pct':100*covered[k]/total,'basis':'market-value-weighted issuer annual ratio; available filings as of portfolio date'} for k in covered},'positions':matched_rows}
def main():
 universe=json.loads((OUT/'universe.json').read_text());records={}
 for path in (OUT/'companyfacts').glob('*.json.gz'):
  r=json.loads(gzip.decompress(path.read_bytes()));records[r['cik']]=r
 # Current proxy snapshot only. Missing prices/market cap are explicit factor blockers.
 field_weights=collections.Counter()
 for s in universe['securities']:
  if s.get('cik') in records:
   for field in snapshot(records[s['cik']],universe['as_of']):field_weights[field]+=s['weight_pct']
 dump(OUT/'benchmark_status.json',{'updated_at':now(),'benchmark':'S&P Composite 1500 via SPTM ETF holdings proxy','as_of':universe['as_of'],'source_url':universe['source_url'],'membership_basis':universe['membership_basis'],'field_weight_coverage_pct':{k:100*v/sum(s['weight_pct'] for s in universe['securities']) for k,v in field_weights.items()},'style_calculation_status':'blocked_missing_point_in_time_price_market_cap_sector_inputs','historical_benchmark_status':'historical_membership_not_yet_available'})
 index=json.loads((ROOT/'CapitalSignal/data/13f/index.json').read_text());latest={}
 for e in index['managers']:
  cik=e['manager_cik']
  if cik not in latest or e['report_date']>latest[cik]['report_date']:latest[cik]=e
 profiles=[];missing=0
 for e in latest.values():
  path=ROOT/'CapitalSignal/data/13f'/e['file']
  if not path.exists():missing+=1;continue
  data=json.loads(path.read_text());r=match_positions(data['holdings'],universe['securities'],records,e['report_date'])
  r.pop('positions')
  r.update(manager_cik=e['manager_cik'],report_date=e['report_date'],identifier_mapping_basis='current SPTM CUSIP to issuer map; no historical membership inferred',benchmark_comparison_status='pending_historical_benchmark' if e['report_date']!=universe['as_of'] else 'pending_prices_and_sector_data',calculated_style=None)
  profiles.append(r)
 dump(OUT/'portfolio_diagnostics.json',{'updated_at':now(),'profiles':profiles,'missing_cached_portfolio_files':missing,'status':'initial_identifier_matching_and_fundamental_ratio_diagnostics_only','production_classification_status':'pending_70pct_both_dimension_coverage_and_point_in_time_benchmark','editorial_labels':'unchanged'})
 print(f'Matched {len(profiles)} cached portfolios; {missing} files unavailable')
if __name__=='__main__':main()
