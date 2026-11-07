#!/usr/bin/env python3
"""Fetch a bounded sample of public 13F information tables from SEC EDGAR.
No external dependencies. Missing/unavailable filings are skipped, never fabricated.
"""
import json, os, pathlib, re, time, urllib.request, xml.etree.ElementTree as ET
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
    managers=[x.strip().zfill(10) for x in os.getenv("SEC_13F_MANAGER_CIKS","0001067983,0001364742,0001037389").split(",") if x.strip()]
    summary=[]
    for cik in managers[:6]:
        try:
            submission=json.loads(read(f"https://data.sec.gov/submissions/CIK{cik}.json"))
            recent=submission["filings"]["recent"]
            i=next(i for i,form in enumerate(recent["form"]) if form=="13F-HR")
            accession=recent["accessionNumber"][i]
            filing_date=recent["filingDate"][i]
            report_date=recent["reportDate"][i]
            rooturl=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-','')}/"
            time.sleep(.3)
            index=json.loads(read(rooturl+"index.json"))
            candidates=[x["name"] for x in index["directory"]["item"] if x["name"].lower().endswith(".xml") and "primary" not in x["name"].lower()]
            holdings=[]
            for filename in candidates[:12]:
                time.sleep(.3)
                try:
                    xml=read(rooturl+filename)
                    found=parse(xml)
                    if len(found)>len(holdings):holdings=found
                except (ET.ParseError,ValueError,TimeoutError, OSError) as exc:
                    print("XML skipped",filename,str(exc))
            if not holdings: raise ValueError("No readable 13F information table XML")
            output={"manager_cik":cik,"manager_name":submission.get("name",""),"accession":accession,"filing_date":filing_date,"report_date":report_date,"source":rooturl,"holdings":holdings}
            (OUT/f"{cik}.json").write_text(json.dumps(output,separators=(",",":")),encoding="utf-8")
            summary.append({"manager_cik":cik,"manager_name":output["manager_name"],"report_date":report_date,"filing_date":filing_date,"holdings_count":len(holdings),"file":f"{cik}.json"})
            print("13F cached",cik,len(holdings))
        except Exception as exc:
            print("WARNING 13F",cik,str(exc))
        time.sleep(.3)
    (OUT/"index.json").write_text(json.dumps({"managers":summary,"limitations":"Selected managers only; reported 13F positions, not a shareholder register. Values are in thousands of USD as reported."},separators=(",",":")),encoding="utf-8")
if __name__=="__main__":main()
