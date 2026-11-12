#!/usr/bin/env python3
"""Checkpointed S&P 1500 + Russell 3000 proxy/SEC Companyfacts ingestion; no estimated facts."""
import argparse, collections, datetime as dt, gzip, hashlib, io, json, os, pathlib, time, urllib.request, urllib.error
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'CapitalSignal/data/fundamentals'
HOLDINGS = 'https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-sptm.xlsx'
TICKERS = 'https://www.sec.gov/files/company_tickers.json'
TAGS = {
 'revenue': ('RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','RevenueFromContractWithCustomerIncludingAssessedTax'),
 'net_income': ('NetIncomeLoss','ProfitLoss'),
 'equity': ('StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'),
 'assets': ('Assets',), 'liabilities': ('Liabilities',),
 'operating_income': ('OperatingIncomeLoss',),
 'operating_cash_flow': ('NetCashProvidedByUsedInOperatingActivities',),
 'capital_expenditure': ('PaymentsToAcquirePropertyPlantAndEquipment',),
 'eps_diluted': ('EarningsPerShareDiluted',),
 'shares_outstanding': ('EntityCommonStockSharesOutstanding','CommonStockSharesOutstanding'),
 'dividends_per_share': ('CommonStockDividendsPerShareDeclared','CommonStockDividendsPerShareCashPaid'),
}
INSTANT = {'equity','assets','liabilities','shares_outstanding'}
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def dump(path, data):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(data,separators=(',',':')));tmp.replace(path)
def get(url):
 for attempt in range(4):
  try:
   time.sleep(.35)
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':os.getenv('SEC_USER_AGENT','CapitalSignal Research hello@ainvestmentbank.ai'),'Accept-Encoding':'identity'}),timeout=45) as response: return response.read()
  except Exception as exc:
   if isinstance(exc, urllib.error.HTTPError) and exc.code in (403,429): raise
   if attempt==3: raise
   time.sleep(2**attempt*2)
def key(ticker): return str(ticker).strip().upper().replace('.','-')
def parse_universe(blob, tickers):
 import openpyxl
 rows=list(openpyxl.load_workbook(io.BytesIO(blob),read_only=True,data_only=True).active.values)
 date=next(str(r[1]) for r in rows if r[0]=='Holdings:')
 asof=dt.datetime.strptime(date.replace('As of ',''),'%d-%b-%Y').date().isoformat()
 start=next(i for i,r in enumerate(rows) if r[0]=='Name' and r[1]=='Ticker')
 lookup=collections.defaultdict(set)
 for t in tickers.values(): lookup[key(t['ticker'])].add(str(t['cik_str']).zfill(10))
 securities=[]; excluded=[]
 for row in rows[start+1:]:
  name,ticker,cusip,sedol,weight,sector,shares,currency=row[:8]
  if not name: continue
  if not ticker or ticker=='-' or 'CVR' in str(cusip) or str(name).startswith('CONTRA ') or 'MONEY MARKET' in str(name) or not cusip or len(str(cusip))!=9 or not isinstance(weight,(int,float)) or weight<=0 or not isinstance(shares,(int,float)) or shares<=0:
   excluded.append({'name':str(name),'reason':'non_equity_or_invalid_identifier_weight_shares'}); continue
  matches=lookup.get(key(ticker),set())
  securities.append({'name':name,'ticker':ticker,'cusip':str(cusip),'cik':next(iter(matches)) if len(matches)==1 else None,'mapping_status':'unique_sec_ticker_match_current' if len(matches)==1 else 'unmapped_or_ambiguous','weight_pct':weight,'sector':None if sector in (None,'-') else sector,'currency':currency})
 if not 1300<=len(securities)<=1700: raise ValueError(f'Universe count outside safety range: {len(securities)}')
 return {'as_of':asof,'retrieved_at':now(),'source_url':HOLDINGS,'source_sha256':hashlib.sha256(blob).hexdigest(),'membership_basis':'SPTM ETF holdings proxy; not official index constituents or historical membership','securities':securities,'excluded_rows':excluded}
def extract(data,url):
 fields={}
 for field,tags in TAGS.items():
  observations=[]
  for taxonomy in ('us-gaap','dei'):
   for tag in tags:
    for unit,points in data.get('facts',{}).get(taxonomy,{}).get(tag,{}).get('units',{}).items():
     for p in points:
      if p.get('filed') and p.get('end') and isinstance(p.get('val'),(int,float)):
       observations.append(dict(p,taxonomy=taxonomy,tag=tag,unit=unit))
  fields[field]=observations
 return {'cik':str(data['cik']).zfill(10),'entity_name':data['entityName'],'source_url':url,'retrieved_at':now(),'fields':fields}
def snapshot(record,asof):
 result={}
 for field,points in record['fields'].items():
  unit='shares' if field=='shares_outstanding' else 'USD/shares' if field in ('eps_diluted','dividends_per_share') else 'USD'
  eligible=[]
  for p in points:
   if p['unit']!=unit or p['filed']>asof or p['end']>asof: continue
   if field not in INSTANT:
    if not p.get('start'): continue
    days=(dt.date.fromisoformat(p['end'])-dt.date.fromisoformat(p['start'])).days
    if not 330<=days<=400: continue
   eligible.append(p)
  if eligible:
   # Prefer the primary tag, then the most recently available restatement for that period.
   p=max(eligible,key=lambda p:(p['end'],p['filed'],-TAGS[field].index(p['tag'])))
   result[field]=p
 return result
def cache_age(path, cik):
 """Invalid caches are missing work, not successful checkpoints."""
 try:
  record=json.loads(gzip.decompress(path.read_bytes()))
  if record.get('cik')!=cik or not isinstance(record.get('fields'),dict):return None
  retrieved=dt.datetime.fromisoformat(record['retrieved_at'])
  if retrieved.tzinfo is None:return None
  age=(dt.datetime.now(dt.timezone.utc)-retrieved).total_seconds()
  return age if age>=0 else None
 except (OSError,ValueError,KeyError,TypeError,EOFError):return None
def work_queue(ciks, directory, refresh_hours):
 """Missing issuers precede refreshes so bounded daily runs cannot starve coverage."""
 pending=[];stale=[]
 for cik in ciks:
  age=cache_age(directory/(cik+'.json.gz'),cik)
  if age is None:pending.append(cik)
  elif age>=refresh_hours*3600:stale.append((age,cik))
 return sorted(pending)+[cik for age,cik in sorted(stale,reverse=True)]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--limit',type=int,default=0);ap.add_argument('--refresh-hours',type=float,default=24);ap.add_argument('--max-seconds',type=float,default=0);args=ap.parse_args()
 OUT.mkdir(parents=True,exist_ok=True)
 errors=[]
 try:
  tickers=json.loads(get(TICKERS))
  sp_blob=get(HOLDINGS);sp=parse_universe(sp_blob,tickers)
  russell_blob=get(HOLDINGS_RUSSELL);russell=parse_universe(russell_blob,tickers)
  by_cusip={}
  for label,collection in [('S&P1500_proxy',sp['securities']),('Russell3000_proxy',russell['securities'])]:
   for member in collection:
    record=by_cusip.setdefault(member['cusip'],dict(member,universe_memberships=[]))
    if label not in record['universe_memberships']:record['universe_memberships'].append(label)
    if record.get('cik') is None and member.get('cik'):record.update({k:member[k] for k in ('cik','mapping_status')})
  securities=list(by_cusip.values())
  for member in securities:member['universe_memberships'].sort()
  merged={'as_of':min(sp['as_of'],russell['as_of']),'retrieved_at':now(),'source_url':sp['source_url'],'source_sha256':hashlib.sha256((sp['source_sha256']+russell['source_sha256']).encode()).hexdigest(),'membership_basis':'Union of current SPTM S&P1500 proxy and IWV Russell 3000 ETF holdings proxies; deduplicated by CUSIP. Not official or historical index membership. SEC-listed large/mega cap issuers outside both proxies require reliable point-in-time market cap data.','universe_sources':[{'name':'S&P1500 proxy','as_of':sp['as_of'],'url':sp['source_url'],'sha256':sp['source_sha256']},{'name':'Russell3000 proxy','as_of':russell['as_of'],'url':russell['source_url'],'sha256':russell['source_sha256']}],'securities':securities,'excluded_rows':sp['excluded_rows']+russell['excluded_rows']}
  universe=merged
  dump(OUT/'universe.json',universe);dump(OUT/'universes'/(universe['as_of']+'.json'),universe)
 except Exception as e:
  dump(OUT/'last_attempt.json',{'at':now(),'status':'universe_source_failed','error':str(e)});raise
 ciks=sorted({s['cik'] for s in universe['securities'] if s['cik']})
 start=time.monotonic();attempted=0
 def summarize():
  coverage=collections.Counter();ok=0;fresh=0;missing=[]
  for cik in ciks:
   path=OUT/'companyfacts'/(cik+'.json.gz')
   age=cache_age(path,cik)
   if age is None:missing.append(cik);continue
   record=json.loads(gzip.decompress(path.read_bytes()));ok+=1
   if age<args.refresh_hours*3600:fresh+=1
   coverage.update(snapshot(record,universe['as_of']).keys())
  dump(OUT/'status.json',{'updated_at':now(),'status':'complete_with_gaps' if ok==len(ciks) else 'partial','universe_as_of':universe['as_of'],'universe_basis':universe['membership_basis'],'security_count':len(universe['securities']),'mapped_security_count':sum(bool(s['cik']) for s in universe['securities']),'unique_mapped_issuers':len(ciks),'ingested_issuers':ok,'fresh_issuers':fresh,'pending_issuers':missing,'failed_attempts':errors,'unmapped_securities':[s for s in universe['securities'] if not s['cik']],'field_issuer_coverage':dict(coverage),'field_basis':'USD annual-duration facts; instant balance-sheet/shares facts; filed and end <= universe date; annual is not TTM','next_stage':'benchmark matching and portfolio diagnostics','gaps':['Official historical constituents/weights','Point-in-time prices and share-class market caps','Sector data absent when provider reports dash','Forward consensus estimates unavailable','Custom/IFRS taxonomy normalization pending'],'elapsed_seconds':round(time.monotonic()-start)})
 for cik in work_queue(ciks,OUT/'companyfacts',args.refresh_hours):
  path=OUT/'companyfacts'/(cik+'.json.gz')
  if args.limit and attempted>=args.limit:break
  if args.max_seconds and time.monotonic()-start>=args.max_seconds:break
  attempted+=1;url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
  try:
   blob=get(url);data=json.loads(blob)
   if str(data.get('cik','')).zfill(10)!=cik:raise ValueError('CIK mismatch')
   record=extract(data,url);record['source_sha256']=hashlib.sha256(blob).hexdigest()
   path.parent.mkdir(exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_bytes(gzip.compress(json.dumps(record,separators=(',',':')).encode(),mtime=0));tmp.replace(path)
  except KeyboardInterrupt:
   errors.append({'cik':cik,'source_url':url,'error':'interrupted; saved caches retained','at':now()})
   break
  except Exception as e:
   errors.append({'cik':cik,'source_url':url,'error':str(e),'at':now()})
   if isinstance(e,urllib.error.HTTPError) and e.code in (403,429):
    summarize();raise
  if attempted%25==0:summarize();print(f'Checkpoint {attempted} attempted',flush=True)
 summarize();print((OUT/'status.json').read_text(),flush=True)
if __name__=='__main__':main()
