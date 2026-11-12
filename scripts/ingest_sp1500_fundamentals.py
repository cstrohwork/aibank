#!/usr/bin/env python3
"""Checkpointed S&P 1500 + Russell 3000 proxy/SEC Companyfacts ingestion; no estimated facts."""
import argparse, collections, csv, datetime as dt, gzip, hashlib, io, json, os, pathlib, time, traceback, urllib.request, urllib.error
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'CapitalSignal/data/fundamentals'
HOLDINGS = 'https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-sptm.xlsx'
HOLDINGS_RUSSELL = 'https://www.ishares.com/us/products/239714/ishares-russell-3000-etf/latest-holdings.csv'
TICKERS = 'https://www.sec.gov/files/company_tickers.json'
NASDAQ_SCREENER = 'https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=5000&offset=0&exchange=nasdaq%7Cnyse%7Camex'
LARGE_CAP_MIN_USD = 10_000_000_000
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
def get(url,extra_headers=None):
 for attempt in range(4):
  try:
   time.sleep(.35)
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':os.getenv('SEC_USER_AGENT','CapitalSignal Research hello@ainvestmentbank.ai'),'Accept-Encoding':'identity',**(extra_headers or {})}),timeout=45) as response: return response.read()
  except Exception as exc:
   if isinstance(exc, urllib.error.HTTPError) and exc.code in (403,429): raise
   if attempt==3: raise
   time.sleep(2**attempt*2)
def key(ticker): return str(ticker).strip().upper().replace('.','-').replace(' ','-').replace('/','-')
def parse_universe(blob, tickers):
 import openpyxl
 rows=list(openpyxl.load_workbook(io.BytesIO(blob),read_only=True,data_only=True).active.values)
 date=next(str(r[1]) for r in rows if len(r)>1 and r[0]=='Holdings:')
 asof=dt.datetime.strptime(date.replace('As of ',''),'%d-%b-%Y').date().isoformat()
 start=next(i for i,r in enumerate(rows) if len(r)>1 and r[0]=='Name' and r[1]=='Ticker')
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

def parse_russell(blob, tickers):
 rows=list(csv.reader(io.StringIO(blob.decode('utf-8-sig'))))
 date=next(r[1] for r in rows if len(r)>1 and r[0]=='Fund Holdings as of')
 asof=dt.datetime.strptime(date.strip(),'%b %d, %Y').date().isoformat()
 start=next(i for i,r in enumerate(rows) if r and r[0]=='Ticker' and len(r)>3 and r[1]=='Name' and r[3]=='Asset Class')
 headers=rows[start]
 ix={name:i for i,name in enumerate(headers)}
 required=('Ticker','Name','Sector','Asset Class','Market Value','Weight (%)','Quantity','Currency')
 if any(name not in ix for name in required):raise ValueError('Russell holdings CSV schema changed')
 lookup=collections.defaultdict(set)
 for t in tickers.values():lookup[key(t['ticker'])].add(str(t['cik_str']).zfill(10))
 securities=[];excluded=[]
 for row in rows[start+1:]:
  # Trailing empty CSV fields may be omitted by the provider; validate only fields we consume.
  if len(row)<=max(ix[name] for name in required):continue
  ticker,name,sector,asset_class=(row[ix[x]].strip() for x in ('Ticker','Name','Sector','Asset Class'))
  if not name:continue
  try:
   market_value=float(row[ix['Market Value']].replace(',',''))
   weight=float(row[ix['Weight (%)']].replace(',',''))
   quantity=float(row[ix['Quantity']].replace(',',''))
  except (ValueError,AttributeError):
   excluded.append({'name':name,'reason':'invalid_weight_or_quantity'});continue
  # The provider rounds small portfolio weights to 0.00%; keep positive-value equity rows.
  if asset_class!='Equity' or not ticker or ticker=='-' or market_value<=0 or weight<0 or quantity<=0:
   excluded.append({'name':name,'reason':'non_equity_or_invalid_identifier_weight_shares'});continue
  matches=lookup.get(key(ticker),set())
  securities.append({'name':name,'ticker':ticker,'cusip':None,'cik':next(iter(matches)) if len(matches)==1 else None,
   'mapping_status':'unique_sec_ticker_match_current' if len(matches)==1 else 'unmapped_or_ambiguous',
   'weight_pct':weight,'sector':None if sector in ('','-') else sector,'currency':row[ix['Currency']],
   'identifier_basis':'provider_ticker_only_no_cusip_in_source'})
 if not 2200<=len(securities)<=3500:raise ValueError(f'Russell universe count outside safety range: {len(securities)}')
 return {'as_of':asof,'retrieved_at':now(),'source_url':HOLDINGS_RUSSELL,
  'source_sha256':hashlib.sha256(blob).hexdigest(),
  'membership_basis':'IWV Russell 3000 ETF holdings proxy; not official historical index constituents',
  'securities':securities,'excluded_rows':excluded}

def parse_market_cap(value):
 raw=str(value or '').strip().replace('$','').replace(',','').replace(' ','')
 if not raw or raw in ('—','-','N/A'):return None
 scale={'K':1e3,'M':1e6,'B':1e9,'T':1e12}
 suffix=raw[-1].upper()
 try:return float(raw[:-1])*scale[suffix] if suffix in scale else float(raw)
 except (ValueError,TypeError):return None

def parse_large_megacap(blob,tickers):
 payload=json.loads(blob)
 rows=payload.get('data',{}).get('rows')
 if not isinstance(rows,list) or not rows:raise ValueError('Nasdaq screener returned no stock rows')
 lookup=collections.defaultdict(set)
 for t in tickers.values():lookup[key(t['ticker'])].add(str(t['cik_str']).zfill(10))
 securities=[];excluded=[];candidate_count=0
 for row in rows:
  cap=parse_market_cap(row.get('marketCap'))
  if cap is None or cap<LARGE_CAP_MIN_USD:continue
  candidate_count+=1
  ticker=str(row.get('symbol') or '').strip()
  matches=lookup.get(key(ticker),set())
  if not ticker or len(matches)!=1:
   excluded.append({'ticker':ticker,'name':row.get('name'),'market_cap_usd':cap,'reason':'no_unique_current_sec_ticker_match'})
   continue
  securities.append({'name':row.get('name') or ticker,'ticker':ticker,'cusip':None,
   'cik':next(iter(matches)),'mapping_status':'unique_sec_ticker_match_current',
   'market_cap_usd':cap,'sector':row.get('sector') or None,'exchange':row.get('exchange') or None,
   'identifier_basis':'nasdaq_current_screener_ticker_market_cap'})
 if candidate_count<350 or len(securities)<300 or len(securities)>1800:
  raise ValueError(f'Large/mega-cap universe failed safety bounds: {len(securities)} SEC-mapped of {candidate_count} market-cap candidates')
 return {'as_of':dt.date.today().isoformat(),'retrieved_at':now(),'source_url':NASDAQ_SCREENER,
  'source_sha256':hashlib.sha256(blob).hexdigest(),'market_cap_floor_usd':LARGE_CAP_MIN_USD,
  'membership_basis':'Current Nasdaq screener stocks listed on Nasdaq, NYSE, or NYSE American with market capitalization >= $10 billion and unique SEC ticker-to-CIK mapping; screener is current, not point-in-time historical membership',
  'candidate_count':candidate_count,'securities':securities,'excluded_rows':excluded}

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
  russell_blob=get(HOLDINGS_RUSSELL);russell=parse_russell(russell_blob,tickers)
  by_cusip={};by_ticker={}
  for label,collection in [('S&P1500_proxy',sp['securities']),('Russell3000_proxy',russell['securities'])]:
   for member in collection:
    ticker_id=key(member.get('ticker',''))
    cusip=member.get('cusip')
    record=by_ticker.get(ticker_id) if ticker_id else None
    if record is None and cusip:record=by_cusip.get(cusip)
    if record is None:
     record=dict(member,universe_memberships=[])
     if cusip:by_cusip[cusip]=record
     if ticker_id:by_ticker[ticker_id]=record
    if label not in record['universe_memberships']:record['universe_memberships'].append(label)
    if record.get('cusip') is None and cusip:record['cusip']=cusip
    if record.get('cik') is None and member.get('cik'):record.update({k:member[k] for k in ('cik','mapping_status')})
  securities=list(by_ticker.values())
  for member in securities:member['universe_memberships'].sort()
  merged={'as_of':min(sp['as_of'],russell['as_of']),'retrieved_at':now(),'source_url':sp['source_url'],'source_sha256':hashlib.sha256((sp['source_sha256']+russell['source_sha256']).encode()).hexdigest(),'membership_basis':'Union of current SPTM S&P1500 proxy and IWV Russell 3000 ETF holdings proxy; deduplicated by normalized ticker, with CUSIP retained when available. IWV source does not include CUSIPs. Current proxy membership, not point-in-time index constituents. A separate large/mega-cap screen outside these proxies is not yet available.','universe_sources':[{'name':'S&P1500 proxy','as_of':sp['as_of'],'url':sp['source_url'],'sha256':sp['source_sha256']},{'name':'Russell3000 proxy','as_of':russell['as_of'],'url':russell['source_url'],'sha256':russell['source_sha256']}],'securities':securities,'excluded_rows':sp['excluded_rows']+russell['excluded_rows']}
  universe=merged
  dump(OUT/'universe.json',universe);dump(OUT/'universes'/(universe['as_of']+'.json'),universe)
 except Exception as e:
  dump(OUT/'last_attempt.json',{'at':now(),'status':'universe_source_failed','error':str(e),'traceback':traceback.format_exc()});raise
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
