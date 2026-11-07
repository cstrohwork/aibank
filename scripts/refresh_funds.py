#!/usr/bin/env python3
"""Build a bounded, sourced fund-level holdings database from SEC N-PORT-P.
N-PX is voting activity, not a complete positions statement.
"""
import os,json,re,time,pathlib,urllib.request,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]/"CapitalSignal"/"data"
OUT=ROOT/"funds";OUT.mkdir(parents=True,exist_ok=True)
UA=os.getenv("SEC_USER_AGENT","CapitalSignal Research hello@ainvestmentbank.ai")
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":UA,"Accept-Encoding":"identity"}),timeout=45) as r:return r.read()
def local(t):return t.rsplit("}",1)[-1].lower()
def val(n,*names):
    wanted={x.lower() for x in names}
    for c in n.iter():
        if local(c.tag) in wanted and c.text:return c.text.strip()
    return ""
def parse(raw,source):
    root=ET.fromstring(raw)
    series=val(root,"seriesId")
    fund=val(root,"seriesName","seriesNm","seriesNameOfFund") or series
    report=val(root,"repPdDate","reportDate","reportingPeriod")
    assets=val(root,"totAssets","totalAssets")
    rows=[]
    for n in root.iter():
        if local(n.tag) not in ("invstorsec","investmentorsecurity"):continue
        cusip=val(n,"cusip").upper()
        if not re.fullmatch("[A-Z0-9]{9}",cusip):continue
        try:amount=float(val(n,"valUSD","valueUSD","valueInUSD","reportedValue"))
        except ValueError:continue
        rows.append({"cusip":cusip,"issuer":val(n,"name","issuerName","title"),"asset_category":val(n,"assetCat"),"reported_value_usd":amount,"balance":val(n,"balance"),"reported_percentage":val(n,"pctVal","reportedPercentage")})
    if not rows:return None
    return {"series_id":series,"fund_name":fund,"report_date":report,"total_assets_reported":assets,"source":source,"holdings":rows}
def main():
    # Registered fund trust CIKs; these are not assumed to map to 13F managers.
    ciks=[x.strip().zfill(10) for x in os.getenv("SEC_FUND_CIKS","0001100663,0000036405,0000225322").split(",") if x.strip()]
    index=[];errors=[]
    for cik in ciks[:8]:
        try:
            sub=json.loads(get("https://data.sec.gov/submissions/CIK"+cik+".json"))
            rec=sub["filings"]["recent"];eligible=[]
            for i,form in enumerate(rec["form"]):
                if form in ("NPORT-P","NPORT-P/A") and rec["filingDate"][i]>="2026-01-01":
                    eligible.append((rec["filingDate"][i],rec["accessionNumber"][i]))
            for filing,accession in sorted(eligible,reverse=True)[:4]:
                try:
                    base=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-','')}/"
                    listing=json.loads(get(base+"index.json"))["directory"]["item"]
                    xmls=[f["name"] for f in listing if f["name"].lower().endswith(".xml")]
                    best=None
                    for filename in xmls[:8]:
                        time.sleep(.25)
                        try:
                            result=parse(get(base+filename),base+filename)
                            if result and (not best or len(result["holdings"])>len(best["holdings"])):best=result
                        except (OSError,ValueError,ET.ParseError):pass
                    if not best:continue
                    best.update({"registrant_cik":cik,"registrant_name":sub.get("name"),"filing_date":filing,"accession":accession})
                    key=(best["series_id"] or cik)+"-"+(best["report_date"] or filing)
                    filename=re.sub("[^A-Za-z0-9_-]","_",key)+".json"
                    (OUT/filename).write_text(json.dumps(best,separators=(",",":")))
                    index.append({"series_id":best["series_id"],"fund_name":best["fund_name"],"registrant_cik":cik,"registrant_name":sub.get("name"),"report_date":best["report_date"],"filing_date":filing,"holdings_count":len(best["holdings"]),"file":filename,"source":best["source"]})
                    print("fund cached",filename,len(best["holdings"]))
                except Exception as e:errors.append(f"{cik} {accession}: {e}")
                time.sleep(.3)
        except Exception as e:errors.append(f"{cik}: {e}")
    # Do not claim an institution-fund mapping without independent attribution.
    latest={}
    for f in sorted(index,key=lambda x:x["filing_date"]):
        latest[f["series_id"] or f["file"]]=f
    selected=list(latest.values())
    (OUT/"index.json").write_text(json.dumps({"funds":selected,"filings_parsed":len(index),"registrants_attempted":ciks[:8],"errors":errors[:30],"limitations":"Bounded SEC N-PORT sample, not complete market coverage. N-PX is proxy voting, not a holdings inventory. No fund-to-13F manager attribution inferred."},separators=(",",":")))
    # Fund-level ownership index: securities -> disclosed fund positions.
    owners={}
    for f in selected:
        data=json.loads((OUT/f["file"]).read_text())
        for h in data["holdings"]:
            if h["asset_category"] not in ("EC","EP"):continue
            owners.setdefault(h["cusip"],[]).append({"series_id":f["series_id"],"fund_name":f["fund_name"],"report_date":f["report_date"],"reported_value_usd":h["reported_value_usd"],"source":f["source"]})
    (OUT/"ownership_by_cusip.json").write_text(json.dumps({"securities":owners,"note":"Disclosed N-PORT fund holdings only; not total issuer ownership; different report dates may occur."},separators=(",",":")))
    print("funds",len(selected),"equity CUSIPs",len(owners),"errors",len(errors))
if __name__=="__main__":main()
