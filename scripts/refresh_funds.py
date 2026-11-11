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
def fund_identity(root):
    series=val(root,"seriesId")
    if re.fullmatch(r"S\d+",series):
        return {"series_id":series,"fund_id":series,"identity_basis":"sec_series_id"}
    if series:
        raise ValueError("Missing/invalid N-PORT series identifier")
    cik=val(root,"regCik")
    reg_name=val(root,"regName")
    series_name=val(root,"seriesName","seriesNm","seriesNameOfFund")
    reg_lei=val(root,"regLei").upper()
    series_lei=val(root,"seriesLei").upper()
    same_name=" ".join(reg_name.casefold().split())==" ".join(series_name.casefold().split())
    same_entity=(bool(reg_name) and same_name and re.fullmatch(r"[A-Z0-9]{20}",reg_lei)
                 and reg_lei==series_lei)
    explicit_na=series_name.upper()=="N/A" and series_lei=="N/A"
    if not re.fullmatch(r"\d{1,10}",cik) or not reg_name or not (same_entity or explicit_na):
        raise ValueError("Missing/invalid N-PORT series identifier")
    return {"series_id":None,"fund_id":"CIK"+cik.zfill(10),
            "identity_basis":"matching_registrant_series_lei_and_name" if same_entity else "explicit_not_applicable_series",
            "identity_registrant_cik":cik.zfill(10),"registrant_lei":reg_lei,
            "series_lei_reported":series_lei,"series_name_reported":series_name}

def parse(raw,source):
    root=ET.fromstring(raw)
    fund=val(root,"seriesName","seriesNm","seriesNameOfFund")
    report=val(root,"repPdDate","reportDate","reportingPeriod")
    assets=val(root,"totAssets","totalAssets")
    rows=[]
    for n in root.iter():
        if local(n.tag) not in ("invstorsec","investmentorsecurity"):continue
        cusip=val(n,"cusip").upper()
        if not re.fullmatch("[A-Z0-9]{9}",cusip):cusip=None
        try:amount=float(val(n,"valUSD","valueUSD","valueInUSD","reportedValue"))
        except ValueError:continue
        rows.append({"cusip":cusip,"isin":val(n,"isin"),"issuer":val(n,"name","issuerName","title"),"asset_category":val(n,"assetCat"),"reported_value_usd":amount,"balance":val(n,"balance"),"reported_percentage":val(n,"pctVal","reportedPercentage")})
    if not rows:return None
    identity=fund_identity(root)
    if not fund or fund.upper()=="N/A":fund=val(root,"regName") or identity["fund_id"]
    return {**identity,"fund_name":fund,"report_date":report,"total_assets_reported":assets,"source":source,"holdings":rows}
def main():
    # Registered fund trust CIKs; these are not assumed to map to 13F managers.
    ciks=[x.strip().zfill(10) for x in os.getenv("SEC_FUND_CIKS","0001100663,0000036405,0000225322").split(",") if x.strip()]
    from sec_history import submission_rows
    start=os.getenv("SEC_HISTORY_START","2025-09-30")
    history_path=OUT/"history_index.json"
    index=json.loads(history_path.read_text()).get("funds",[]) if history_path.exists() else []
    if not index and (OUT/"index.json").exists():index=json.loads((OUT/"index.json").read_text()).get("funds",[])
    checkpoint_path=OUT/"seed_checkpoint.json"
    known=set(json.loads(checkpoint_path.read_text()).get("processed",[])) if checkpoint_path.exists() else set()
    known.update(x.get("accession") for x in index if x.get("accession"))
    errors=[]
    processed=0
    budget=int(os.getenv("SEC_FUND_BATCH","30"))
    for cik in ciks:
        try:
            sub=json.loads(get("https://data.sec.gov/submissions/CIK"+cik+".json"))
            eligible=[]
            for row in submission_rows(sub,get,start):
                if row.get("form") in ("NPORT-P","NPORT-P/A") and row.get("filingDate","")>=start:
                    eligible.append((row["filingDate"],row["accessionNumber"]))
            for filing,accession in sorted(eligible):
                if accession in known or processed>=budget:continue
                processed+=1
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
                    if best["report_date"]<start:
                        known.add(accession)
                        continue
                    best.update({"registrant_cik":cik,"registrant_name":sub.get("name"),"filing_date":filing,"accession":accession})
                    key=best["fund_id"]+"-"+(best["report_date"] or filing)
                    filename=re.sub("[^A-Za-z0-9_-]","_",key)+".json"
                    existing=OUT/filename
                    if existing.exists():
                        previous=json.loads(existing.read_text())
                        if (previous.get("filing_date",""),previous.get("accession",""))>(filing,accession):
                            known.add(accession)
                            continue
                    (OUT/filename).write_text(json.dumps(best,separators=(",",":")))
                    index.append({"fund_id":best["fund_id"],"identity_basis":best["identity_basis"],"series_id":best["series_id"],"fund_name":best["fund_name"],"registrant_cik":cik,"registrant_name":sub.get("name"),"report_date":best["report_date"],"filing_date":filing,"accession":accession,"holdings_count":len(best["holdings"]),"file":filename,"source":best["source"]})
                    known.add(accession)
                    print("fund cached",filename,len(best["holdings"]))
                except Exception as e:errors.append(f"{cik} {accession}: {e}")
                time.sleep(.3)
        except Exception as e:errors.append(f"{cik}: {e}")
    periods={}
    for f in sorted(index,key=lambda x:(x["filing_date"],x.get("accession",""))):
        periods[(f.get("fund_id") or f["series_id"],f["report_date"])]=f
    history=list(periods.values())
    history_path.write_text(json.dumps({"funds":history,"start_report_date":start},separators=(",",":")))
    latest={}
    for f in sorted(history,key=lambda x:(x["report_date"],x["filing_date"])):
        latest[f.get("fund_id") or f["series_id"] or f["file"]]=f
    selected=list(latest.values())
    (OUT/"index.json").write_text(json.dumps({"funds":selected,"filings_parsed":len(index),"registrants_attempted":ciks,"errors":errors[:30],"limitations":"Bounded SEC N-PORT sample, not complete market coverage. N-PX is proxy voting, not a holdings inventory. No fund-to-13F manager attribution inferred."},separators=(",",":")))
    checkpoint_path.write_text(json.dumps({"processed":sorted(known)},separators=(",",":")))
    # Fund-level ownership index: securities -> disclosed fund positions.
    owners={}
    for f in selected:
        data=json.loads((OUT/f["file"]).read_text())
        for h in data["holdings"]:
            if h["asset_category"] not in ("EC","EP") or not h.get("cusip"):continue
            owners.setdefault(h["cusip"],[]).append({"fund_id":f.get("fund_id") or f["series_id"],"series_id":f["series_id"],"fund_name":f["fund_name"],"report_date":f["report_date"],"reported_value_usd":h["reported_value_usd"],"source":f["source"]})
    (OUT/"ownership_by_cusip.json").write_text(json.dumps({"securities":owners,"note":"Disclosed N-PORT fund holdings only; not total issuer ownership; different report dates may occur."},separators=(",",":")))
    print("funds",len(selected),"equity CUSIPs",len(owners),"errors",len(errors))
if __name__=="__main__":main()

