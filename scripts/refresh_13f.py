#!/usr/bin/env python3
"""Fetch a bounded sample of public 13F information tables from SEC EDGAR.
No external dependencies. Missing/unavailable filings are skipped, never fabricated.
"""
import json, os, pathlib, re, time, urllib.request, xml.etree.ElementTree as ET
import datetime as dt
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"CapitalSignal"/"data"/"13f"
OUT.mkdir(parents=True,exist_ok=True)
UA=os.environ.get("SEC_USER_AGENT","CapitalSignal Research hello@ainvestmentbank.ai")
def read(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json","Accept-Encoding":"identity"})
    with urllib.request.urlopen(req,timeout=35) as resp:
        return resp.read()
def tag(node):
    return node.tag.rsplit("}",1)[-1].lower()
def field(node,name):
    for child in node.iter():
        if tag(child)==name.lower(): return (child.text or "").strip()
    return ""
def parse(xml):
    root=ET.fromstring(xml)
    records=[]
    for node in root.iter():
        if tag(node)!="infotable": continue
        cusip=field(node,"cusip").upper()
        if not re.fullmatch(r"[0-9A-Z]{9}",cusip):continue
        try: value=int(field(node,"value").replace(",",""))
        except ValueError: continue
        records.append({"issuer":field(node,"nameOfIssuer"),"cusip":cusip,"class":field(node,"titleOfClass"),"value_thousands":value,"shares":field(node,"sshPrnamt"),"share_type":field(node,"sshPrnamtType"),"put_call":field(node,"putCall")})
    return records
def main():
    start=os.getenv("SEC_13F_START_DATE","2025-09-30")
    managers=[x.strip().zfill(10) for x in os.getenv("SEC_13F_MANAGER_CIKS","0001067983,0001364742,0001037389").split(",") if x.strip()]
    from sec_history import submission_rows
    old=json.loads((OUT/"index.json").read_text()).get("managers",[]) if (OUT/"index.json").exists() else []
    summary=[x for x in old if x["report_date"]>=start]
    for cik in managers:
        try:
            submission=json.loads(read(f"https://data.sec.gov/submissions/CIK{cik}.json"))
            eligible=[]
            for row in submission_rows(submission,read,start):
                report=row.get("reportDate","")
                if row.get("form")=="13F-HR" and report and report>=start:
                    eligible.append((report,row["filingDate"],row["accessionNumber"]))
            # One filing per report period, latest filing date wins.
            periods={}
            for report,filing,accession in eligible:
                if report not in periods or (filing,accession)>periods[report]:
                    periods[report]=(filing,accession)
            for report_date,(filing_date,accession) in sorted(periods.items()):
                try:
                    rooturl=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-','')}/"
                    cached=OUT/f"{cik}-{report_date}.json"
                    if cached.exists() and json.loads(cached.read_text()).get("accession")==accession:
                        continue
                    time.sleep(.35)
                    index=json.loads(read(rooturl+"index.json"))
                    candidates=[x["name"] for x in index["directory"]["item"] if x["name"].lower().endswith(".xml") and "primary" not in x["name"].lower()]
                    holdings=[];retrieved_at=None
                    for filename in candidates[:12]:
                        time.sleep(.35)
                        try:
                            raw=read(rooturl+filename)
                            downloaded_at=dt.datetime.now(dt.timezone.utc).isoformat()
                            found=parse(raw)
                            if len(found)>len(holdings):holdings=found;retrieved_at=downloaded_at
                        except (ET.ParseError,ValueError,TimeoutError,OSError) as exc:
                            print("XML skipped",filename,str(exc))
                    if not holdings:raise ValueError("No readable 13F information table XML")
                    # This pipeline's requested reporting window is after the SEC USD transition.
                    # Leave older ad-hoc backfills untyped rather than assigning ambiguous units.
                    if report_date >= '2025-09-30':
                        for holding in holdings:holding['value_usd']=holding['value_thousands']
                    output={"manager_cik":cik,"manager_name":submission.get("name",""),"accession":accession,"filing_date":filing_date,"report_date":report_date,"source":rooturl,"holdings":holdings,"retrieved_at":retrieved_at,"ingested_at":dt.datetime.now(dt.timezone.utc).isoformat(),"public_observed_at":retrieved_at,"public_observation_basis":"successful_public_sec_download"}
                    if report_date >= '2025-09-30':output.update(value_unit='USD',legacy_value_thousands_field_contains='USD')
                    filename=f"{cik}-{report_date}.json"
                    (OUT/filename).write_text(json.dumps(output,separators=(",",":")),encoding="utf-8")
                    summary.append({"manager_cik":cik,"manager_name":output["manager_name"],"report_date":report_date,"filing_date":filing_date,"holdings_count":len(holdings),"file":filename})
                    print("13F cached",cik,report_date,len(holdings))
                except Exception as exc:
                    print("WARNING 13F period",cik,report_date,str(exc))
            time.sleep(.35)
        except Exception as exc:
            print("WARNING 13F manager",cik,str(exc))
    summary=list({(x["manager_cik"],x["report_date"]):x for x in summary}.values())
    (OUT/"index.json").write_text(json.dumps({"start_report_date":start,"managers":summary,"limitations":"Selected managers and 13F-HR report periods only, starting at the stated report date. Not a complete issuer shareholder register; reported 13F values are USD (legacy value_thousands field name retained). Filing dates can lag report dates."},separators=(",",":")),encoding="utf-8")
if __name__=="__main__":main()

