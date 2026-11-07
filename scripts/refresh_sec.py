#!/usr/bin/env python3
"""Cache SEC issuer lookup and selected issuer submissions for GitHub Pages.
Requires Python 3.11+. No third-party packages.
SEC fair access: https://www.sec.gov/about/developer-resources
"""
import json, os, pathlib, time, urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"CapitalSignal"/"data"
OUT.mkdir(parents=True,exist_ok=True)
UA=os.environ.get("SEC_USER_AGENT","CapitalSignal Research hello@ainvestmentbank.ai")
def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json","Accept-Encoding":"identity"})
    with urllib.request.urlopen(req,timeout=35) as response:
        return json.load(response)
tickers=get("https://www.sec.gov/files/company_tickers.json")
items=[{"ticker":v["ticker"],"name":v["title"],"cik":str(v["cik_str"]).zfill(10)} for v in tickers.values()]
(OUT/"issuers.json").write_text(json.dumps(items,separators=(",",":")),encoding="utf-8")
# Seed a small, explicit issuer list; users can still query other CIKs directly.
ciks=os.environ.get("SEC_CACHE_CIKS","0000320193,0000789019,0001018724,0001652044,0001318605,0001067983,0000051143,0000040545,0000731766,0001045810")
for cik in dict.fromkeys(x.strip().zfill(10) for x in ciks.split(",") if x.strip()):
    time.sleep(0.3)
    try:
        submission=get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        recent=submission.get("filings",{}).get("recent",{})
        forms={"10-K","10-Q","8-K","DEF 14A","SC 13D","SC 13D/A","SC 13G","SC 13G/A","13F-HR","13F-HR/A"}
        rows=[]
        for i,form in enumerate(recent.get("form",[])):
            if form not in forms: continue
            rows.append({k:recent.get(k,[])[i] if i<len(recent.get(k,[])) else "" for k in ("form","filingDate","reportDate","accessionNumber","primaryDocument")})
            if len(rows)>=120: break
        record={"cik":cik,"name":submission.get("name",""),"tickers":submission.get("tickers",[]),"exchanges":submission.get("exchanges",[]),"filings":rows,"source":f"https://data.sec.gov/submissions/CIK{cik}.json"}
        (OUT/f"{cik}.json").write_text(json.dumps(record,separators=(",",":")),encoding="utf-8")
        print("cached",cik,len(rows))
    except Exception as exc:
        print("WARNING",cik,str(exc))
print("issuer lookup entries",len(items))
