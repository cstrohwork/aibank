#!/usr/bin/env python3
"""Parse evidenced 13D/G positions and N-PX votes from verified archived submissions."""
import argparse, collections, datetime as dt, gzip, hashlib, io, json, pathlib, re, tarfile, urllib.request
import xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]/'CapitalSignal/data'
PARSER_VERSION=1
FORMS={'SC 13D','SC 13D/A','SC 13G','SC 13G/A','SCHEDULE 13D','SCHEDULE 13D/A','SCHEDULE 13G','SCHEDULE 13G/A','N-PX','N-PX/A'}

def local(tag):return tag.rsplit('}',1)[-1]
def text(node,*names):
 for name in names:
  for item in node.iter():
   if local(item.tag)==name:
    value=' '.join(' '.join(item.itertext()).split())
    if value:return value
 return None

def number(value):
 if value is None:return None
 value=value.replace(',','').strip()
 if not re.fullmatch(r'-?\d+(?:\.\d+)?',value):return None
 result=float(value)
 return result if abs(result)<1e30 else None

def documents(raw):
 source=raw.decode('utf-8',errors='replace')
 for i,body in enumerate(re.findall(r'<DOCUMENT>(.*?)</DOCUMENT>',source,re.S|re.I),1):
  filename=re.search(r'<FILENAME>\s*([^\r\n<]+)',body,re.I)
  for xml in re.findall(r'<XML>(.*?)</XML>',body,re.S|re.I):
   xml=xml.strip()
   if '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():continue
   try:yield filename.group(1).strip() if filename else str(i),ET.fromstring(xml)
   except ET.ParseError:continue

def parse_submission(raw,meta):
 base={k:meta.get(k) for k in ('accession','form','source','filing_date','cik','name')}
 base['is_amendment']=str(meta.get('form','')).endswith('/A')
 base['activist_intent']=None
 ownership=[];votes=[];docs=0;notice=None
 for filename,tree in documents(raw):
  docs+=1
  if str(meta.get('form','')).startswith('N-PX'):
   notice=text(tree,'noticeExplanation') or notice
   for i,table in enumerate(n for n in tree.iter() if local(n.tag)=='proxyTable'):
    records=[n for n in table.iter() if local(n.tag)=='voteRecord']
    if not records:continue
    for j,record in enumerate(records):
     direction=text(record,'howVoted')
     if direction is None:continue
     votes.append(dict(base,record_id=f"{meta.get('accession')}:{filename}:{i}:{j}",document=filename,issuer_name=text(table,'issuerName'),cusip=text(table,'cusip'),meeting_date=text(table,'meetingDate'),description=text(table,'voteDescription'),categories=[text(n,'categoryType') for n in table.iter() if local(n.tag)=='voteCategory'],how_voted=direction,shares_voted=number(text(record,'sharesVoted')),shares_on_loan=number(text(table,'sharesOnLoan')),management_recommendation=text(record,'managementRecommendation'),series_id=text(table,'seriesId','seriesID'),evidence_excerpt=ET.tostring(record,encoding='unicode')[:1200],evidence_path=f'proxyTable[{i}]/vote/voteRecord[{j}]'))
  else:
   purpose=text(tree,'transactionPurpose')
   for i,person in enumerate(n for n in tree.iter() if local(n.tag) in ('reportingPersonInfo','coverPageHeaderReportingPersonDetails')):
    shares=number(text(person,'aggregateAmountOwned','reportingPersonBeneficiallyOwnedAggregateNumberOfShares'))
    pct=number(text(person,'percentOfClass','classPercent'))
    if shares is None and pct is None:continue
    ownership.append(dict(base,record_id=f"{meta.get('accession')}:{filename}:{i}",document=filename,issuer_name=text(tree,'issuerName'),issuer_cik=text(tree,'issuerCIK','issuerCik'),cusip=text(tree,'issuerCUSIP','issuerCusip','cusipNumber'),event_date=text(tree,'dateOfEvent','eventDateRequiresFilingThisStatement'),reporting_person_name=text(person,'reportingPersonName'),reporting_person_cik=text(person,'reportingPersonCIK'),beneficial_shares=shares,percent_of_class=pct,sole_voting_power=number(text(person,'soleVotingPower')),shared_voting_power=number(text(person,'sharedVotingPower')),purpose_excerpt=purpose[:1600] if purpose else None,purpose_truncated=bool(purpose and len(purpose)>1600),evidence_excerpt=ET.tostring(person,encoding='unicode')[:1800],evidence_path=f'{local(person.tag)}[{i}]',aggregation_warning='Joint reporting persons may describe the same shares; do not sum. Amendments remain separate observations.'))
 return {'metadata':base,'structured_documents':docs,'notice_explanation':notice,'ownership':ownership,'votes':votes}

def read_body(root,record,shards,max_raw):
 path=root/record.get('raw_file','MISSING')
 if path.is_file():compressed=path.read_bytes()
 else:
  url=record.get('release_asset_url')
  if url not in shards:raise ValueError('body_not_local_or_selected_release_shard')
  payload=shards[url]
  if isinstance(payload,Exception):raise ValueError('release_fetch_failed: '+str(payload))
  with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
   member=archive.getmember(record['raw_file'])
   if member.size>max_raw:raise ValueError('compressed_body_exceeds_budget')
   compressed=archive.extractfile(member).read(max_raw+1)
 with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as reader:raw=reader.read(max_raw+1)
 if len(raw)>max_raw:raise ValueError('decompressed_body_exceeds_budget')
 if not record.get('sha256') or hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('body_checksum_mismatch_or_missing')
 return raw

def run(root=ROOT,limit=2000,fetch_release=False,max_shards=2,max_shard_bytes=100000000,max_raw=10000000):
 state_path=root/'history/archive_state.json.gz'
 state=json.loads(gzip.decompress(state_path.read_bytes())) if state_path.exists() else {}
 candidates=sorted([r for r in state.values() if r.get('form') in FORMS],key=lambda r:(r.get('release_asset_url',''),r.get('accession','')))
 archived=[r for r in candidates if r.get('status')=='archived']
 checkpoint=root/'intelligence/parsed_events.json'
 previous=json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
 previous_filings={r['accession']:r for r in previous.get('filings',[])}
 completed={a for a,r in previous_filings.items() if r.get('parse_status')=='parsed'}
 unchanged_unsupported={a for a,r in previous_filings.items() if r.get('parse_status')!='parsed' and r.get('parser_version')==PARSER_VERSION}
 pending=[r for r in archived if r['accession'] not in completed and not (r['accession'] in unchanged_unsupported and previous_filings[r['accession']].get('source_sha256')==r.get('sha256'))]
 selected=pending[:limit]
 shards={}
 if fetch_release:
  # Select at least one voting shard and one ownership shard when both are available.
  counts=collections.Counter(r.get('release_asset_url') for r in selected if r.get('release_asset_url'))
  npx=collections.Counter(r.get('release_asset_url') for r in selected if r.get('form','').startswith('N-PX') and r.get('release_asset_url'))
  dg=collections.Counter(r.get('release_asset_url') for r in selected if not r.get('form','').startswith('N-PX') and r.get('release_asset_url'))
  urls=[]
  for counter in (npx,dg,counts):
   for url,_ in counter.most_common():
    if url not in urls:urls.append(url)
    if counter is not counts:break
  for url in urls[:max_shards]:
   try:
    if not url.startswith('https://github.com/cstrohwork/aibank/releases/download/'):raise ValueError('unapproved_release_location')
    with urllib.request.urlopen(url,timeout=45) as response:payload=response.read(max_shard_bytes+1)
    if len(payload)>max_shard_bytes:raise ValueError('release_shard_exceeds_budget')
    expected={r.get('release_asset_sha256') for r in selected if r.get('release_asset_url')==url}
    if len(expected)!=1 or hashlib.sha256(payload).hexdigest() not in expected:raise ValueError('release_checksum_mismatch_or_missing')
    shards[url]=payload
   except Exception as exc:shards[url]=exc
 filings=list(previous_filings.values());ownership=list(previous.get('beneficial_ownership',[]));votes=list(previous.get('proxy_votes',[]));unavailable=[];unsupported=[]
 for r in selected:
  try:
   raw=read_body(root,r,shards,max_raw);parsed=parse_submission(raw,r)
   row=dict(parsed['metadata'],structured_documents=parsed['structured_documents'],ownership_records=len(parsed['ownership']),proxy_vote_records=len(parsed['votes']),notice_explanation=parsed['notice_explanation'])
   if parsed['ownership'] or parsed['votes'] or parsed['notice_explanation']:row['parse_status']='parsed'
   else:row['parse_status']='unsupported_or_no_extracted_records';unsupported.append(r['accession'])
   row['source_sha256']=r.get('sha256');row['parser_version']=PARSER_VERSION
   filings=[f for f in filings if f.get('accession')!=r['accession']];filings.append(row)
   ownership=[v for v in ownership if v.get('accession')!=r['accession']];ownership.extend(parsed['ownership'])
   votes=[v for v in votes if v.get('accession')!=r['accession']];votes.extend(parsed['votes'])
  except Exception as exc:unavailable.append({'accession':r.get('accession'),'form':r.get('form'),'source':r.get('source'),'reason':str(exc)})
 all_completed={f['accession'] for f in filings if f.get('parse_status')=='parsed'}
 unsupported=sorted({f['accession'] for f in filings if f.get('parse_status')!='parsed'})
 pending_accessions={r['accession'] for r in archived if r['accession'] not in all_completed}
 reasons={u['accession']:u for u in unavailable}
 unavailable=[reasons.get(r['accession'],{'accession':r['accession'],'form':r['form'],'source':r.get('source'),'reason':'pending_next_bounded_run'}) for r in archived if r['accession'] in pending_accessions and r['accession'] not in unsupported]
 summary={'catalogued_candidate_filings':len(candidates),'archived_candidate_filings':len(archived),'selected_filings':len(selected),'parsed_filings':sum(r['parse_status']=='parsed' for r in filings),'beneficial_ownership_records':len(ownership),'proxy_vote_records':len(votes),'unavailable_filings':len(unavailable),'unsupported_filings':len(unsupported),'unselected_archived_filings':len(pending)-len(selected),'unchanged_unsupported_filings':len(unchanged_unsupported),'previously_parsed_filings':len(completed),'remaining_archived_filings':len(pending_accessions),'release_shards_fetched':sum(not isinstance(x,Exception) for x in shards.values())}
 return {'schema_version':1,'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'partial' if unavailable or unsupported or pending_accessions else 'parsed_cached_candidates','summary':summary,'filings':filings,'beneficial_ownership':ownership,'proxy_votes':votes,'unavailable':unavailable,'unsupported_accessions':unsupported,'limitations':['Only structured XML supported; legacy HTML/text needs separate parsing.','Source date is filing date; voting meeting date/event date retained separately.','No activist intent inferred from filing form or generic purpose language.','Joint reporting persons and amendments are separate observations, never additive ownership.','N-PX votes do not establish portfolio ownership.','Bounded release retrieval can leave archived documents unavailable in this run.']}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--data-root',type=pathlib.Path,default=ROOT);ap.add_argument('--limit',type=int,default=2000);ap.add_argument('--fetch-release',action='store_true',help='Compatibility flag; release fetching is enabled by default');ap.add_argument('--offline',action='store_true');ap.add_argument('--max-shards',type=int,default=2);args=ap.parse_args()
 if args.limit<1 or args.max_shards<0:ap.error('limit must be positive and max-shards nonnegative')
 result=run(args.data_root,args.limit,not args.offline,args.max_shards);out=args.data_root/'intelligence/parsed_events.json';out.parent.mkdir(parents=True,exist_ok=True);tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(result,separators=(',',':')));tmp.replace(out);print(json.dumps(result['summary']))
if __name__=='__main__':main()
