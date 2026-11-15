#!/usr/bin/env python3
"""Checkpointed S&P 1500 + Russell 3000 proxy/SEC Companyfacts ingestion; no estimated facts."""
import argparse, collections, csv, datetime as dt, gzip, hashlib, io, json, math, os, pathlib, time, traceback, urllib.request, urllib.error
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'CapitalSignal/data/fundamentals'
HOLDINGS = 'https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-sptm.xlsx'
HOLDINGS_RUSSELL = 'https://www.ishares.com/us/products/239714/ishares-russell-3000-etf/latest-holdings.csv'
TICKERS = 'https://www.sec.gov/files/company_tickers.json'
NASDAQ_SCREENER = 'https://api.nasdaq.com/api/screener/stocks?tableonly=true'
NASDAQ_PAGE_SIZE = 1000
NASDAQ_MARKETCAP_FILTER = 'mega%7Clarge'
NASDAQ_EXCHANGE_SOURCES = {
 'NASDAQ': NASDAQ_SCREENER+'&exchange=nasdaq&marketcap='+NASDAQ_MARKETCAP_FILTER,
 'NYSE': NASDAQ_SCREENER+'&exchange=nyse&marketcap='+NASDAQ_MARKETCAP_FILTER,
 'NYSE AMERICAN': NASDAQ_SCREENER+'&exchange=amex&marketcap='+NASDAQ_MARKETCAP_FILTER,
}
LARGE_CAP_MIN_USD = 10_000_000_000
VERIFIED_US_EXCHANGES = {'NASDAQ', 'NYSE', 'NYSE AMERICAN', 'AMEX'}
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
 try:
  result=float(raw[:-1])*scale[suffix] if suffix in scale else float(raw)
  return result if math.isfinite(result) and result>0 else None
 except (ValueError,TypeError):return None

def provider_market_date(value):
 raw=str(value or '').strip()
 prefix='Last price as of '
 if not raw.startswith(prefix):raise ValueError('Nasdaq screener missing dated market-cap observation')
 return dt.datetime.strptime(raw[len(prefix):],'%b %d, %Y').date().isoformat()

def fetch_large_megacap():
 """Fetch exchange pages separately so listings and completeness remain auditable."""
 observed_at=now();rows=[];sources=[];as_of_dates=set()
 for exchange,base_url in NASDAQ_EXCHANGE_SOURCES.items():
  offset=0;exchange_count=0;expected_total=None
  while expected_total is None or exchange_count<expected_total:
   url=f'{base_url}&limit={NASDAQ_PAGE_SIZE}&offset={offset}'
   blob=get(url);payload=json.loads(blob);data=payload.get('data') or {};table=data.get('table') or {}
   source_rows=table.get('rows') if isinstance(table,dict) else None
   if source_rows is None:source_rows=data.get('rows')
   total=data.get('totalrecords')
   if not isinstance(total,int) or total<=0:raise ValueError('Nasdaq screener missing total for '+exchange)
   if expected_total is None:expected_total=total
   elif total!=expected_total:raise ValueError(f'Nasdaq screener total changed for {exchange}: {expected_total} to {total}')
   if not isinstance(source_rows,list) or not source_rows:
    raise ValueError(f'Nasdaq screener incomplete for {exchange}: {exchange_count} of {expected_total}')
   if exchange_count+len(source_rows)>expected_total:
    raise ValueError(f'Nasdaq screener overflow for {exchange}: {exchange_count+len(source_rows)} of {expected_total}')
   market_date=provider_market_date(data.get('asof'));as_of_dates.add(market_date)
   source_sha=hashlib.sha256(blob).hexdigest()
   sources.append({'exchange':exchange,'url':url,'sha256':source_sha,'as_of':market_date,
    'row_count':len(source_rows),'offset':offset,'total_records':expected_total})
   for row in source_rows:
    rows.append(dict(row,exchange=exchange,market_cap_as_of=market_date,
     market_cap_source_url=url,market_cap_source_sha256=source_sha,
     exchange_listing_source_url=url,exchange_listing_source_sha256=source_sha))
   exchange_count+=len(source_rows);offset=exchange_count
  if exchange_count!=expected_total:
   raise ValueError(f'Nasdaq screener incomplete for {exchange}: {exchange_count} of {expected_total}')
 if len(as_of_dates)!=1:raise ValueError('Nasdaq exchange screener dates disagree')
 envelope={'data':{'rows':rows},'as_of':next(iter(as_of_dates)),'retrieved_at':observed_at,'sources':sources}
 return json.dumps(envelope,separators=(',',':'),sort_keys=True).encode(),observed_at

def parse_large_megacap(blob,tickers,observed_at=None,enforce_safety=True):
 """Parse a current screener observation without treating it as historical evidence."""
 payload=json.loads(blob)
 rows=payload.get('data',{}).get('rows')
 if not isinstance(rows,list) or not rows:raise ValueError('Nasdaq screener returned no stock rows')
 observed=dt.datetime.fromisoformat(observed_at.replace('Z','+00:00')) if observed_at else dt.datetime.now(dt.timezone.utc)
 if observed.tzinfo is None:raise ValueError('Large/mega-cap observation requires timezone-aware retrieval time')
 observed_at=observed.astimezone(dt.timezone.utc).isoformat()
 market_date=dt.date.fromisoformat(payload['as_of']).isoformat()
 source_sha=hashlib.sha256(blob).hexdigest()
 lookup=collections.defaultdict(set)
 for t in tickers.values():lookup[key(t['ticker'])].add(str(t['cik_str']).zfill(10))
 securities=[];excluded=[];candidate_count=0
 for row in rows:
  cap=parse_market_cap(row.get('marketCap'))
  if cap is None or cap<LARGE_CAP_MIN_USD:continue
  candidate_count+=1
  ticker=str(row.get('symbol') or '').strip()
  exchange=str(row.get('exchange') or '').strip().upper()
  matches=lookup.get(key(ticker),set())
  if exchange not in VERIFIED_US_EXCHANGES:
   excluded.append({'ticker':ticker,'name':row.get('name'),'market_cap_usd':cap,'exchange':exchange or None,'reason':'unverified_us_exchange_listing'})
   continue
  if not ticker or len(matches)!=1:
   excluded.append({'ticker':ticker,'name':row.get('name'),'market_cap_usd':cap,'exchange':exchange,'reason':'no_unique_current_sec_ticker_match'})
   continue
  securities.append({'name':row.get('name') or ticker,'ticker':ticker,'cusip':None,
   'cik':next(iter(matches)),'mapping_status':'unique_sec_ticker_match_current',
   'market_cap_usd':cap,'market_cap_as_of':row.get('market_cap_as_of') or market_date,
   'market_cap_retrieved_at':observed_at,'market_cap_observed_at':observed_at,
   'market_cap_source_url':row.get('market_cap_source_url') or NASDAQ_SCREENER,
   'market_cap_source_sha256':row.get('market_cap_source_sha256') or source_sha,
   'sector':row.get('sector') or None,'exchange':exchange,
   'exchange_listing_observed_at':observed_at,
   'exchange_listing_source_url':row.get('exchange_listing_source_url') or NASDAQ_SCREENER,
   'exchange_listing_source_sha256':row.get('exchange_listing_source_sha256') or source_sha,
   'identifier_basis':'current Nasdaq screener ticker plus unique current SEC ticker-to-CIK match'})
 deduplicated={}
 for security in securities:
  ticker=key(security['ticker']);signature=(security['cik'],security['market_cap_usd'],security['exchange'])
  if ticker in deduplicated and signature!=(deduplicated[ticker]['cik'],deduplicated[ticker]['market_cap_usd'],deduplicated[ticker]['exchange']):
   raise ValueError('Conflicting large/mega-cap screener rows for '+ticker)
  deduplicated[ticker]=security
 securities=list(deduplicated.values())
 if enforce_safety and (candidate_count<350 or len(securities)<300 or len(securities)>1800):
  raise ValueError(f'Large/mega-cap universe failed safety bounds: {len(securities)} SEC-mapped of {candidate_count} market-cap candidates')
 return {'as_of':market_date,'retrieved_at':observed_at,'source_url':NASDAQ_SCREENER,
  'source_sha256':source_sha,'market_cap_floor_usd':LARGE_CAP_MIN_USD,
  'sources':payload.get('sources',[]),
  'membership_basis':'Current Nasdaq screener stocks listed on Nasdaq, NYSE, or NYSE American with market capitalization >= $10 billion and unique SEC ticker-to-CIK mapping; screener is current, not point-in-time historical membership',
  'candidate_count':candidate_count,'securities':securities,'excluded_rows':excluded}

def outside_proxy_large_megacap(screen,universe):
 """Keep only verified current screen rows outside both ETF proxy snapshots."""
 proxy_tickers={key(s.get('ticker','')) for s in universe.get('securities',[]) if s.get('ticker')}
 rows=[];seen=set()
 for security in screen.get('securities',[]):
  ticker=key(security.get('ticker',''))
  if not ticker or ticker in proxy_tickers or ticker in seen:continue
  if (security.get('exchange') not in VERIFIED_US_EXCHANGES or
      not isinstance(security.get('market_cap_usd'),(int,float)) or isinstance(security.get('market_cap_usd'),bool) or
      security['market_cap_usd']<LARGE_CAP_MIN_USD or not security.get('market_cap_as_of') or
      not security.get('market_cap_retrieved_at') or not security.get('market_cap_source_url') or
      not security.get('market_cap_source_sha256') or not security.get('exchange_listing_source_url') or
      not security.get('exchange_listing_source_sha256')):continue
  seen.add(ticker);rows.append(dict(security,universe_memberships=['large_megacap_outside_current_etf_proxies']))
 return {'as_of':screen['as_of'],'retrieved_at':screen['retrieved_at'],'source_url':screen['source_url'],
  'source_sha256':screen['source_sha256'],'market_cap_floor_usd':screen['market_cap_floor_usd'],
  'status':'verified_current_screen_outside_etf_proxies',
  'scope':'Current screener observation only; not historical membership, not an index, and not evidence before retrieved_at.',
  'security_count':len(rows),'unique_mapped_issuers':len({s['cik'] for s in rows}),'securities':rows,
  'excluded_screen_rows':screen.get('excluded_rows',[])}

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
def merge_proxy_universes(sp,russell):
 """Deduplicate ingestion identities while retaining separate dated benchmarks."""
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
   if any(record.get(k) and member.get(k) and record[k]!=member[k] for k in ('cik','cusip')):
    raise ValueError('Conflicting proxy identity for '+ticker_id)
   if label not in record['universe_memberships']:record['universe_memberships'].append(label)
   if record.get('cusip') is None and cusip:record['cusip']=cusip
   if record.get('cik') is None and member.get('cik'):record.update({k:member[k] for k in ('cik','mapping_status')})
 securities=list(by_ticker.values())
 for member in securities:member['universe_memberships'].sort()
 merged={'as_of':min(sp['as_of'],russell['as_of']),'retrieved_at':now(),'source_url':sp['source_url'],'source_sha256':hashlib.sha256((sp['source_sha256']+russell['source_sha256']).encode()).hexdigest(),'membership_basis':'Union of current SPTM S&P1500 proxy and IWV Russell 3000 ETF holdings proxy; deduplicated by normalized ticker, with CUSIP retained when available. IWV source does not include CUSIPs. Current proxy membership, not point-in-time index constituents. A separate large/mega-cap screen outside these proxies is not yet available.','universe_sources':[{'name':'S&P1500 proxy','as_of':sp['as_of'],'url':sp['source_url'],'sha256':sp['source_sha256']},{'name':'Russell3000 proxy','as_of':russell['as_of'],'url':russell['source_url'],'sha256':russell['source_sha256']}],'securities':securities,'excluded_rows':sp['excluded_rows']+russell['excluded_rows']}
 merged['proxy_snapshots']={'S&P1500_proxy':sp,'Russell3000_proxy':russell}
 merged['weight_basis']='Security-level weight_pct is the first provider observation only; no combined benchmark weight exists. Use proxy_snapshots for separate provider denominators.'
 return merged

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--limit',type=int,default=0);ap.add_argument('--refresh-hours',type=float,default=24);ap.add_argument('--max-seconds',type=float,default=0);args=ap.parse_args()
 OUT.mkdir(parents=True,exist_ok=True)
 errors=[]
 try:
  tickers=json.loads(get(TICKERS))
  sp_blob=get(HOLDINGS);sp=parse_universe(sp_blob,tickers)
  russell_blob=get(HOLDINGS_RUSSELL);russell=parse_russell(russell_blob,tickers)
  universe=merge_proxy_universes(sp,russell)
  dump(OUT/'universe.json',universe);dump(OUT/'universes'/(universe['as_of']+'.json'),universe)
 except Exception as e:
  dump(OUT/'last_attempt.json',{'at':now(),'status':'universe_source_failed','error':str(e),'traceback':traceback.format_exc()});raise
 supplemental_error=None;supplemental={'status':'not_observed','securities':[]}
 try:
  large_blob,observed_at=fetch_large_megacap()
  supplemental=outside_proxy_large_megacap(parse_large_megacap(large_blob,tickers,observed_at),universe)
  dump(OUT/'large_megacap_outside_proxies.json',supplemental)
 except Exception as exc:
  supplemental_error={'at':now(),'source_url':NASDAQ_SCREENER,'error':type(exc).__name__+': '+str(exc)}
  prior=OUT/'large_megacap_outside_proxies.json'
  if prior.exists():
   try:
    supplemental=json.loads(prior.read_text())
    supplemental['runtime_source_status']='source_failed_last_verified_snapshot_retained'
   except (OSError,ValueError,TypeError):supplemental={'status':'source_failed_no_valid_snapshot','securities':[]}
  else:supplemental={'status':'source_failed_no_valid_snapshot','securities':[]}
 proxy_ciks={s['cik'] for s in universe['securities'] if s['cik']}
 supplemental_ciks={s['cik'] for s in supplemental.get('securities',[]) if s.get('cik')}
 ciks=sorted(proxy_ciks|supplemental_ciks)
 start=time.monotonic();attempted=0
 def summarize():
  proxy_coverage=collections.Counter();supplemental_coverage=collections.Counter();missing=[];records={};fresh_ciks=set()
  for cik in ciks:
   path=OUT/'companyfacts'/(cik+'.json.gz')
   age=cache_age(path,cik)
   if age is None:missing.append(cik);continue
   record=json.loads(gzip.decompress(path.read_bytes()));records[cik]=record
   if age<args.refresh_hours*3600:fresh_ciks.add(cik)
  for cik,record in records.items():
   if cik in proxy_ciks:proxy_coverage.update(snapshot(record,universe['as_of']).keys())
   if cik in supplemental_ciks:supplemental_coverage.update(snapshot(record,supplemental['as_of']).keys())
  proxy_ok=len(proxy_ciks&records.keys());supplemental_ok=len(supplemental_ciks&records.keys())
  dump(OUT/'status.json',{'updated_at':now(),'status':'complete_with_gaps' if len(records)==len(ciks) else 'partial','universe_as_of':universe['as_of'],'universe_basis':universe['membership_basis'],'security_count':len(universe['securities']),'mapped_security_count':sum(bool(s['cik']) for s in universe['securities']),'unique_mapped_issuers':len(proxy_ciks),'ingested_issuers':proxy_ok,'fresh_issuers':len(proxy_ciks&fresh_ciks),'pending_issuers':sorted(proxy_ciks-records.keys()),'failed_attempts':errors,'unmapped_securities':[s for s in universe['securities'] if not s['cik']],'field_issuer_coverage':dict(proxy_coverage),'field_basis':'USD annual-duration facts; instant balance-sheet/shares facts; filed and end <= proxy universe date; annual is not TTM','supplemental_large_megacap':{'status':supplemental.get('status'),'as_of':supplemental.get('as_of'),'retrieved_at':supplemental.get('retrieved_at'),'source_url':supplemental.get('source_url'),'source_sha256':supplemental.get('source_sha256'),'security_count':len(supplemental.get('securities',[])),'unique_mapped_issuers':len(supplemental_ciks),'ingested_issuers':supplemental_ok,'fresh_issuers':len(supplemental_ciks&fresh_ciks),'pending_issuers':sorted(supplemental_ciks-records.keys()),'field_issuer_coverage':dict(supplemental_coverage),'field_basis':'USD annual-duration facts; instant balance-sheet/shares facts; filed and end <= supplemental screen date; annual is not TTM','source_error':supplemental_error,'scope':supplemental.get('scope')},'fundamental_ingestion_unique_issuers':len(ciks),'fundamental_ingestion_ingested_issuers':len(records),'fundamental_ingestion_fresh_issuers':len(fresh_ciks),'fundamental_ingestion_pending_issuers':missing,'next_stage':'benchmark matching and portfolio diagnostics','gaps':['Official historical constituents/weights','Point-in-time prices and share-class market caps for portfolio calculations','Sector data absent when provider reports dash','Forward consensus estimates unavailable','Custom/IFRS taxonomy normalization pending'],'elapsed_seconds':round(time.monotonic()-start)})
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
