#!/usr/bin/env python3
"""Build sourced annual company inputs and fail-closed Model activation manifest."""
import datetime as dt
import gzip
import json
import math
from pathlib import Path
from ingest_sp1500_fundamentals import ROOT, OUT, TAGS, INSTANT, dump, now

REQUIRED = ('revenue', 'net_income')

def annual_history(record, cutoff):
    result = {}
    for field, points in record.get('fields', {}).items():
        unit = 'shares' if field == 'shares_outstanding' else 'USD/shares' if field in ('eps_diluted', 'dividends_per_share') else 'USD'
        by_period = {}
        for p in points:
            if p.get('unit') != unit or not isinstance(p.get('val'), (float, int)) or isinstance(p['val'], bool) or not math.isfinite(p['val']):
                continue
            try:
                end = dt.date.fromisoformat(p['end']); filed = dt.date.fromisoformat(p['filed'])
                if end > dt.date.fromisoformat(cutoff) or filed > dt.date.fromisoformat(cutoff): continue
                if field not in INSTANT and not 330 <= (end - dt.date.fromisoformat(p['start'])).days <= 400: continue
            except (ValueError, KeyError, TypeError): continue
            key = (p.get('start'), p['end']) if field not in INSTANT else (None, p['end'])
            rank = (p['filed'], -TAGS.get(field, (p.get('tag'),)).index(p.get('tag'))) if p.get('tag') in TAGS.get(field, ()) else (p['filed'], -999)
            if key not in by_period or rank > by_period[key][0]:
                by_period[key] = (rank, {k: p.get(k) for k in ('val','unit','start','end','filed','accn','form','tag','taxonomy')})
        result[field] = sorted((p for _, p in by_period.values()), key=lambda p: p['end'])[-8:]
    return result

def company_model(record, cutoff):
    history = annual_history(record, cutoff)
    # A common annual reporting period is mandatory for baseline margin calculations.
    periods = {}
    for field in REQUIRED:
        for p in history.get(field, []): periods.setdefault((p['start'], p['end']), {})[field] = p
    eligible = [(period, facts) for period, facts in periods.items() if all(f in facts for f in REQUIRED) and facts['revenue']['val'] > 0]
    baseline = None
    if eligible:
        period, facts = max(eligible, key=lambda pair: pair[0][1])
        for field in ('operating_income','operating_cash_flow','capital_expenditure','eps_diluted'):
            values = [p for p in history.get(field, []) if (p.get('start'),p['end']) == period]
            if values: facts[field] = values[-1]
        baseline = {'start': period[0], 'end': period[1], 'facts': facts}
    return {'cik': record['cik'], 'name': record.get('entity_name'), 'source_url': record.get('source_url'), 'retrieved_at': record.get('retrieved_at'), 'history': history, 'baseline': baseline, 'ready': baseline is not None, 'missing_required': [] if baseline else ['positive revenue and net income for a common USD annual reporting period'], 'share_basis': 'No inferred share-class allocation; EPS projects reported diluted EPS using an explicit user growth assumption.'}

def build(universe, records, errors=None, checked_at=None):
    cutoff = universe['as_of']; members = universe.get('securities', [])
    checked_at = checked_at or dt.datetime.now(dt.timezone.utc)
    def fresh(value):
        try:
            observed = dt.datetime.fromisoformat(value.replace('Z','+00:00'))
            return observed.tzinfo is not None and 0 <= (checked_at-observed).total_seconds() <= 36*3600
        except (ValueError, TypeError, AttributeError): return False
    expiries = [checked_at+dt.timedelta(hours=36), dt.datetime.combine(dt.date.fromisoformat(cutoff)+dt.timedelta(days=8), dt.time(), tzinfo=dt.timezone.utc)]
    for stamp in [universe.get('retrieved_at')] + [r.get('retrieved_at') for r in records.values()]:
        try:
            observed = dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if observed.tzinfo is not None: expiries.append(observed+dt.timedelta(hours=36))
        except (ValueError, TypeError, AttributeError): pass
    stale = sorted(cik for cik, record in records.items() if not fresh(record.get('retrieved_at')))
    universe_fresh = fresh(universe.get('retrieved_at')) and 0 <= (checked_at.date()-dt.date.fromisoformat(cutoff)).days <= 7
    companies = {cik: company_model(record, cutoff) for cik, record in records.items() if cik in {s.get('cik') for s in members}}
    pending = sorted({s['cik'] for s in members if s.get('cik') and s['cik'] not in companies})
    unmapped = [s.get('ticker') for s in members if not s.get('cik')]
    unsupported = [{'cik': c, 'reason': m['missing_required']} for c,m in companies.items() if not m['ready']]
    blockers = []
    if not members: blockers.append('Universe is empty')
    if unmapped: blockers.append('Unmapped securities')
    if pending: blockers.append('Fundamental records pending')
    if unsupported: blockers.append('Required annual modeling fields missing or incompatible')
    if errors: blockers.append('Invalid fundamental cache records')
    if stale: blockers.append('Fundamental records older than 36 hours or missing retrieval timestamps')
    if not universe_fresh: blockers.append('Universe retrieval older than 36 hours or membership date older than seven days')
    return {'schema_version': 1, 'updated_at': checked_at.isoformat(), 'expires_at': min(expiries).isoformat(), 'freshness_policy': {'max_retrieval_age_hours': 36, 'max_membership_age_days': 7}, 'universe_as_of': cutoff, 'membership_basis': universe.get('membership_basis'), 'universe_source_url': universe.get('source_url'), 'activation': {'ready': not blockers, 'status': 'ready' if not blockers else 'blocked', 'blockers': blockers, 'policy': 'All universe securities mapped; all issuer records valid and retrieved within 36 hours; universe retrieved within 36 hours and dated within seven days; each issuer has positive revenue and reported net income for a common USD annual period. No silent exemptions.'}, 'coverage': {'securities': len(members), 'unique_issuers': len({s.get('cik') for s in members if s.get('cik')}), 'ingested_issuers': len(companies), 'model_ready_issuers': sum(m['ready'] for m in companies.values()), 'unmapped_securities': unmapped, 'pending_issuers': pending, 'unsupported_issuers': unsupported, 'invalid_records': errors or [], 'stale_issuers': stale, 'universe_fresh': universe_fresh}, 'securities': [{k:s.get(k) for k in ('ticker','name','cik','cusip','currency')} for s in members], 'companies': companies, 'projection_basis': 'User scenarios, not analyst consensus or forecasts; USD annual facts, not TTM.'}

def main():
    universe=json.loads((OUT/'universe.json').read_text()); records={}; errors=[]
    for cik in sorted({s['cik'] for s in universe['securities'] if s.get('cik')}):
        path=OUT/'companyfacts'/(cik+'.json.gz')
        if not path.exists(): continue
        try:
            record=json.loads(gzip.decompress(path.read_bytes()))
            if record.get('cik') != cik or not isinstance(record.get('fields'),dict): raise ValueError('Invalid record identity or fields')
            records[cik]=record
        except (ValueError, OSError, EOFError) as exc: errors.append({'cik':cik,'error':str(exc)})
    result=build(universe,records,errors)
    # Company histories are separate lazy-loaded objects; publish status last as commit gate.
    company_records=result['companies']
    result['companies']={}
    for cik, company in company_records.items():
        company['dataset_updated_at']=result['updated_at']
        filename='model_companies/'+cik+'.json'
        dump(OUT/filename,company)
        result['companies'][cik]={'cik':cik,'ready':company['ready'],'data_file':filename}
    dump(OUT/'model_data.json',result)
    dump(OUT/'model_status.json',{k:v for k,v in result.items() if k not in ('companies','securities')})
    print(json.dumps({'activation':result['activation'],'coverage':{k:v for k,v in result['coverage'].items() if isinstance(v,int)}}))
if __name__=='__main__': main()
