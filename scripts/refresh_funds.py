#!/usr/bin/env python3
"""Build a bounded, sourced fund-level holdings database from SEC N-PORT-P.
N-PX is voting activity, not a complete positions statement.
"""
import os,json,re,time,math,pathlib,urllib.request,xml.etree.ElementTree as ET
from fund_ownership_index import write_ownership_index
import datetime as dt
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
    valid_reg_lei=bool(re.fullmatch(r"[A-Z0-9]{20}",reg_lei)) and reg_lei!="0"*20
    valid_series_lei=bool(re.fullmatch(r"[A-Z0-9]{20}",series_lei)) and series_lei!="0"*20
    same_valid_lei=valid_reg_lei and valid_series_lei and reg_lei==series_lei
    distinct_series_lei=valid_series_lei and series_lei!=reg_lei
    same_entity=bool(reg_name) and same_name and same_valid_lei
    same_named_entity_without_series_lei=bool(reg_name) and same_name and series_lei=="N/A"
    same_named_entity_with_zero_series_lei=(bool(reg_name) and same_name and
                                            series_lei=="0"*20 and valid_reg_lei)
    explicit_na=series_name.upper()=="N/A" and series_lei=="N/A"
    explicit_none_zero_lei=(series_name.upper()=="NONE" and series_lei=="0"*20 and valid_reg_lei)
    if re.fullmatch(r"\d{1,10}",cik) and reg_name and series_name and distinct_series_lei:
        return {"series_id":None,"fund_id":"LEI"+series_lei,
                "identity_basis":"sec_series_lei_without_series_id",
                "identity_registrant_cik":cik.zfill(10),"registrant_lei":reg_lei,
                "series_lei_reported":series_lei,"series_name_reported":series_name}
    if not re.fullmatch(r"\d{1,10}",cik) or not reg_name or not (same_valid_lei or same_named_entity_without_series_lei or same_named_entity_with_zero_series_lei or explicit_na or explicit_none_zero_lei):
        raise ValueError("Missing/invalid N-PORT series identifier")
    if same_entity:basis="matching_registrant_series_lei_and_name"
    elif same_valid_lei:basis="matching_registrant_series_lei"
    elif same_named_entity_without_series_lei:basis="matching_registrant_series_name_series_lei_not_applicable"
    elif same_named_entity_with_zero_series_lei:basis="matching_registrant_series_name_zero_placeholder_series_lei"
    elif explicit_none_zero_lei:basis="explicit_none_series_zero_lei"
    else:basis="explicit_not_applicable_series"
    return {"series_id":None,"fund_id":"CIK"+cik.zfill(10),
            "identity_basis":basis,
            "identity_registrant_cik":cik.zfill(10),"registrant_lei":reg_lei,
            "series_lei_reported":series_lei,"series_name_reported":series_name}

def capture_download_evidence(record,retrieved_at):
    """Stamp only successful new public downloads, never legacy cache reads."""
    return dict(record,retrieved_at=retrieved_at,ingested_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                public_observed_at=retrieved_at,public_observation_basis="successful_public_sec_download")

def position_field(n,name):
    # Position-level units/currency must not be taken from nested derivative legs.
    for child in n:
        if local(child.tag)==name.lower():return (child.text or "").strip()
    return ""

def parse_position(n):
    cusip=val(n,"cusip").upper()
    if not re.fullmatch("[A-Z0-9]{9}",cusip):cusip=None
    try:amount=float(val(n,"valUSD","valueUSD","valueInUSD","reportedValue"))
    except ValueError:return None
    return {"cusip":cusip,"isin":val(n,"isin"),"issuer":val(n,"name","issuerName","title"),"asset_category":val(n,"assetCat"),"reported_value_usd":amount,"balance":val(n,"balance"),"balance_units":position_field(n,"units") or None,"balance_units_description":position_field(n,"descOthUnits") or None,"currency_code":position_field(n,"curCd") or None,"reported_percentage":val(n,"pctVal","reportedPercentage")}

def parse(raw,source):
    root=ET.fromstring(raw)
    fund=val(root,"seriesName","seriesNm","seriesNameOfFund")
    report=val(root,"repPdDate","reportDate","reportingPeriod")
    assets=val(root,"totAssets","totalAssets")
    rows=[]
    position_nodes=0
    for n in root.iter():
        if local(n.tag) not in ("invstorsec","investmentorsecurity"):continue
        position_nodes+=1
        position=parse_position(n)
        if position is not None:rows.append(position)
    # An empty SEC investment schedule is a real zero-position observation only
    # when the complete filing still supplies identity, period and balance facts.
    # If position nodes exist but none parse, retain the explicit error instead.
    if not rows and position_nodes:return None
    try: identity=fund_identity(root)
    except ValueError:
        if not rows:return None
        raise
    if not rows:
        balances=[assets,val(root,"totLiabs","totalLiabilities"),val(root,"netAssets")]
        try: valid_balances=all(x!="" and math.isfinite(float(x)) for x in balances)
        except ValueError: valid_balances=False
        if not report or not valid_balances:return None
    if not fund or fund.upper() in {"N/A","NONE"}:fund=val(root,"regName") or identity["fund_id"]
    return {**identity,"fund_name":fund,"report_date":report,"total_assets_reported":assets,"source":source,
            "position_coverage":"parsed_supported_positions" if rows else "sec_reported_no_investment_positions",
            "reported_position_count":len(rows),"holdings":rows}
def main():
    # Registered fund trust CIKs; these are not assumed to map to 13F managers.
    # Expand the SEC registrant discovery frontier from previously verified
    # N-PORT filings, rather than revisiting only three bootstrap trusts.
    # A registrant CIK is not evidence of its ultimate investment adviser.
    seed_ciks = [x.strip().zfill(10) for x in os.getenv(
        "SEC_FUND_CIKS", "0001100663,0000036405,0000225322"
    ).split(",") if re.fullmatch(r"\\d{1,10}", x.strip())]
    observed_ciks = set()
    for catalogue in (OUT / "history_index.json", OUT / "index.json"):
        if not catalogue.exists():
            continue
        for record in json.loads(catalogue.read_text()).get("funds", []):
            raw_cik = str(record.get("registrant_cik") or "").strip()
            if re.fullmatch(r"\\d{1,10}", raw_cik):
                observed_ciks.add(raw_cik.zfill(10))
    ciks = list(dict.fromkeys(seed_ciks + sorted(observed_ciks)))
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
                            raw=get(base+filename)
                            retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat()
                            result=parse(raw,base+filename)
                            if result:result=capture_download_evidence(result,retrieved_at)
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
                    index.append({"fund_id":best["fund_id"],"identity_basis":best["identity_basis"],"series_id":best["series_id"],"fund_name":best["fund_name"],"registrant_cik":cik,"registrant_name":sub.get("name"),"report_date":best["report_date"],"filing_date":filing,"accession":accession,"holdings_count":len(best["holdings"]),"position_coverage":best["position_coverage"],"file":filename,"source":best["source"]})
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
    write_ownership_index(OUT, owners, "Disclosed N-PORT fund holdings only; not total issuer ownership; different report dates may occur.")
    print("funds",len(selected),"equity CUSIPs",len(owners),"errors",len(errors))
if __name__=="__main__":main()

