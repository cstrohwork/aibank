#!/usr/bin/env python3
"""Evidence-based identifier master. Observations are not effective-date assertions."""
import argparse
import collections
import datetime as dt
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def cik_id(value):
    value = str(value or '').strip()
    return 'cik:' + value.zfill(10) if re.fullmatch(r'\d{1,10}', value) and int(value) else None


def cusip_valid(value):
    """Validate standard CUSIP structure and check digit, including special symbols."""
    if not re.fullmatch(r'[0-9A-Z*@#]{8}[0-9]', value):
        return False
    total = 0
    for i, char in enumerate(value[:8]):
        n = int(char) if char.isdigit() else ord(char)-55 if char.isalpha() else {'*':36,'@':37,'#':38}[char]
        n *= 1 if i % 2 == 0 else 2
        total += n // 10 + n % 10
    return (10-total % 10) % 10 == int(value[-1])


def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def build(data_root):
    entities = {}
    securities = {}
    relationships = {}
    mappings = {}
    quarantine = collections.Counter()
    missing_files = []

    def entity(eid, role, name, date, source):
        if not eid:
            quarantine[('invalid_entity_identifier', str(name), str(source))] += 1
            return
        e = entities.setdefault(eid, {'id':eid, 'roles':set(), 'names':set(), 'observations':set()})
        e['roles'].add(role)
        if name:
            e['names'].add(str(name))
        e['observations'].add((str(date or ''),str(source or '')))

    def security(value, name, date, source, ticker=None, isin=None, share_class=None):
        value = str(value or '').strip().upper()
        if not cusip_valid(value):
            quarantine[('invalid_or_missing_cusip', value, str(source or ''))] += 1
            return None
        sid='cusip:'+value
        s=securities.setdefault(sid, {'id':sid,'cusip':value,'names':set(),'tickers':set(),'isins':set(),'share_classes':set(),'observed_report_dates':set(),'source_types':set()})
        for key,val in [('names',name),('tickers',ticker),('isins',isin),('share_classes',share_class),('observed_report_dates',date)]:
            if val: s[key].add(str(val))
        s['source_types'].add(source)
        return sid

    def relation(child,parent,kind,date,source):
        key=(child,parent,kind)
        r=relationships.setdefault(key, {'child_id':child,'parent_id':parent,'relationship':kind,'observations':set(),'valid_from':None,'valid_to':None})
        r['observations'].add((str(date or ''),str(source or '')))

    paths=sorted((data_root/'fundamentals/universes').glob('*.json'))
    current=data_root/'fundamentals/universe.json'
    if current.exists(): paths.append(current)
    for path in paths:
        u=read(path,{})
        date=u.get('as_of'); source=u.get('source_url') or str(path.relative_to(data_root))
        for row in u.get('securities',[]):
            eid=cik_id(row.get('cik'))
            sid=security(row.get('cusip'),row.get('name'),date,'fundamentals_universe',ticker=row.get('ticker'))
            if eid: entity(eid,'issuer',row.get('name'),date,source)
            if sid and eid:
                k=(sid,eid,date,source)
                mappings[k]={'security_id':sid,'entity_id':eid,'observed_on':date,'source':source,'mapping_basis':row.get('mapping_status'),'valid_from':None,'valid_to':None}

    for folder,key in [('13f','managers'),('funds','funds')]:
        index=read(data_root/folder/'index.json',{})
        for row in index.get(key,[]):
            date=row.get('report_date'); source=row.get('source') or folder+'/'+str(row.get('file',''))
            eid=cik_id(row.get('manager_cik') if folder=='13f' else row.get('registrant_cik'))
            entity(eid,'13f_manager' if folder=='13f' else 'fund_registrant',row.get('manager_name') if folder=='13f' else row.get('registrant_name'),date,source)
            if folder=='funds':
                series=row.get('series_id')
                if series and re.fullmatch(r'S\d{9}',series): fid='series:'+series
                elif row.get('fund_id')=='CIK'+str(row.get('registrant_cik')) and row.get('identity_basis')=='matching_registrant_series_lei_and_name' and eid:
                    fid='fund:registrant:'+eid[4:]
                else:
                    fid=None
                    quarantine[('unverified_fund_identity',str(row.get('fund_id')),source)]+=1
                if fid:
                    entity(fid,'fund',row.get('fund_name'),date,source)
                    if eid: relation(fid,eid,'registered_under',date,source)
            filename=row.get('file')
            path=data_root/folder/filename if filename else None
            if not path or not path.is_file():
                missing_files.append(str(path) if path else source)
                continue
            # Cache contains normalized SEC observations; never fuzzy-link names.
            document=read(path,{})
            for h in document.get('holdings',[]):
                security(h.get('cusip'),h.get('issuer'),date,folder,isin=h.get('isin'),share_class=h.get('class'))

    by_security=collections.defaultdict(set)
    for m in mappings.values(): by_security[m['security_id']].add(m['entity_id'])
    ambiguous={k:sorted(v) for k,v in sorted(by_security.items()) if len(v)>1}
    for m in mappings.values():
        m['resolution_status']='quarantined_conflicting_issuer' if m['security_id'] in ambiguous else 'observed_mapping_only'
    for group in (entities,securities):
        for row in group.values():
            for k,v in list(row.items()):
                if isinstance(v,set):
                    row[k]=([{'report_date':d or None,'source':s or None} for d,s in sorted(v)] if k=='observations' else sorted(v))
    for r in relationships.values():
        r['observations']=[{'report_date':d or None,'source':s or None} for d,s in sorted(r['observations'])]
    return {
        'schema_version':1,
        'methodology':{'entity_identity':'Exact SEC CIK; roles may overlap. Fund series is distinct from registrant.',
            'security_identity':'Validated CUSIP, distinct share classes remain distinct.',
            'historical_validity':'Observed dates only. Null validity dates mean unknown, not perpetual validity. Current ticker maps cannot establish prior issuer identity.',
            'parent_attribution':'Fund registrant is evidenced; adviser and ultimate parent relationships are unverified and absent. Name similarity never creates relationships.',
            'security_names':'Reported aliases, never authoritative issuer identities.'},
        'entities':sorted(entities.values(),key=lambda x:x['id']),
        'securities':sorted(securities.values(),key=lambda x:x['id']),
        'security_issuer_observations':sorted(mappings.values(),key=lambda x:(x['security_id'],x['entity_id'],str(x['observed_on']),x['source'])),
        'relationships':sorted(relationships.values(),key=lambda x:(x['child_id'],x['parent_id'],x['relationship'])),
        'ambiguous_security_issuer_mappings':ambiguous,
        'quarantine':[{'reason':k[0],'identifier':k[1],'source':k[2],'observation_count':v} for k,v in sorted(quarantine.items())],
        'missing_cached_files':sorted(set(missing_files))}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data-root',type=pathlib.Path,default=ROOT/'CapitalSignal/data')
    ap.add_argument('--output-dir',type=pathlib.Path)
    args=ap.parse_args()
    result=build(args.data_root)
    result['generated_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    out=args.output_dir or args.data_root/'intelligence';out.mkdir(parents=True,exist_ok=True)
    def save(name,obj):
        path=out/name;tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,separators=(',',':')));tmp.replace(path)
    save('identity_master.json',result)
    status={'generated_at':result['generated_at'],'status':'built_with_explicit_gaps','entity_count':len(result['entities']), 'security_count':len(result['securities']), 'relationship_count':len(result['relationships']), 'issuer_mapping_observation_count':len(result['security_issuer_observations']), 'ambiguous_security_count':len(result['ambiguous_security_issuer_mappings']), 'quarantine_observations':sum(x['observation_count'] for x in result['quarantine']), 'missing_cached_files':len(result['missing_cached_files']), 'gaps':['Historical effective identifier dates unknown','Adviser and ultimate parent attribution unverified','Identifiers outside cached filings not covered']}
    save('identity_status.json',status)
    print(json.dumps(status))


if __name__=='__main__': main()
