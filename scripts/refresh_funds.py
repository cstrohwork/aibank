#!/usr/bin/env python3
"""Build a bounded, sourced fund-level holdings database from SEC N-PORT-P.
N-PX is voting activity, not a complete positions statement.
"""
import os,json,re,time,math,pathlib,urllib.request,urllib.error,xml.etree.ElementTree as ET
from fund_ownership_index import write_ownership_index
import datetime as dt
ROOT=pathlib.Path(__file__).resolve().parents[1]/"CapitalSignal"/"data"
OUT=ROOT/"funds";OUT.mkdir(parents=True,exist_ok=True)
UA=os.getenv("SEC_USER_AGENT","CapitalSignal Research hello@ainvestmentbank.ai")
# Share a conservative request cadence across submission, index and XML requests.
# Retry transient SEC service interruptions without losing the persisted cursor.
_last_request_at = 0.0
def get(url):
    global _last_request_at
    for attempt in range(4):
        wait = max(0.0, 0.25 - (time.monotonic() - _last_request_at))
        if wait:
            time.sleep(wait)
        _last_request_at = time.monotonic()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            retry_after = exc.headers.get("Retry-After", "")
            delay = min(30.0, float(retry_after)) if retry_after.isdigit() else min(30.0, 2 ** attempt)
            time.sleep(delay)
        except (TimeoutError, urllib.error.URLError):
            if attempt == 3:
                raise
            time.sleep(min(30.0, 2 ** attempt))
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
    ).split(",") if re.fullmatch(r"\d{1,10}", x.strip())]
    observed_ciks = set()
    for catalogue in (OUT / "history_index.json", OUT / "index.json"):
        if not catalogue.exists():
            continue
        for record in json.loads(catalogue.read_text()).get("funds", []):
            raw_cik = str(record.get("registrant_cik") or "").strip()
            if re.fullmatch(r"\d{1,10}", raw_cik):
                observed_ciks.add(raw_cik.zfill(10))
    ciks = list(dict.fromkeys(seed_ciks + sorted(observed_ciks)))
    from sec_history import submission_rows
    start=os.getenv("SEC_HISTORY_START","2025-09-30")
    history_path=OUT/"history_index.json"
    index=json.loads(history_path.read_text()).get("funds",[]) if history_path.exists() else []
    if not index and (OUT/"index.json").exists():index=json.loads((OUT/"index.json").read_text()).get("funds",[])
    checkpoint_path=OUT/"seed_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {}
    known=set(checkpoint.get("processed",[]))
    known.update(x.get("accession") for x in index if x.get("accession"))
    errors=[]
    # Keep accession-level failures across runs without blocking other registrants.
    # Successful accessions clear their previous retry records.
    failed=dict(checkpoint.get("failed_accessions", {}))
    processed=0
    budget=int(os.getenv("SEC_FUND_BATCH","30"))
    # Rotate the starting registrant and cap per-registrant work so a large
    # trust cannot consume the entire batch before other trusts are visited.
    cursor = int(checkpoint.get("next_registrant_offset", 0)) % max(1, len(ciks))
    ciks = ciks[cursor:] + ciks[:cursor]
    per_registrant = max(1, math.ceil(budget / max(1, len(ciks))))
    for cik in ciks:
        if processed >= budget: break
        try:
            sub=json.loads(get("https://data.sec.gov/submissions/CIK"+cik+".json"))
            eligible=[]
            for row in submission_rows(sub,get,start):
                if row.get("form") in ("NPORT-P","NPORT-P/A") and row.get("filingDate","")>=start:
                    eligible.append((row["filingDate"],row["accessionNumber"]))
            # Reserve a quarter of the bounded batch for oldest missing filings,
            # while prioritizing recent disclosures and amendments for the rest.
            missing = sorted((row for row in eligible if row[1] not in known), reverse=True)
            # Cool down repeatedly failed accessions without blocking other filings.
            now_utc = dt.datetime.now(dt.timezone.utc)
            def retry_ready(row):
                failure = failed.get(row[1])
                if not failure:
                    return True
                try:
                    attempted = dt.datetime.fromisoformat(failure["last_attempt_at"])
                    if attempted.tzinfo is None:
                        attempted = attempted.replace(tzinfo=dt.timezone.utc)
                    attempts = max(1, int(failure.get("attempts", 1)))
                    delay = dt.timedelta(minutes=min(360, 5 * 2 ** min(attempts - 1, 7)))
                    return now_utc - attempted >= delay
                except (ValueError, TypeError, KeyError, OverflowError):
                    return True
            missing = [row for row in missing if retry_ready(row)]
            # A per-registrant cap of one previously meant the oldest
            # reservation was always truncated away. Alternate whole bounded
            # cycles so historical filings receive a real processing slot.
            historical_cycle = int(checkpoint.get("selection_cycle", 0)) % 4 == 3
            ordered = (list(reversed(missing)) if historical_cycle else missing)[:per_registrant]
            for filing,accession in ordered:
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
                    if not best:
                        raise ValueError("No supported N-PORT holdings document parsed from filing XML; accession remains retryable")
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
                    failed.pop(accession, None)
                    print("fund cached",filename,len(best["holdings"]))
                except Exception as e:
                    errors.append(f"{cik} {accession}: {e}")
                    previous=failed.get(accession, {})
                    failed[accession]={"registrant_cik":cik,"attempts":int(previous.get("attempts",0))+1,
                        "last_error":str(e)[:300],"last_attempt_at":dt.datetime.now(dt.timezone.utc).isoformat()}
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
    checkpoint_path.write_text(json.dumps({"processed":sorted(known),
        "next_registrant_offset": (cursor + 1) % max(1, len(ciks)),
        "selection_cycle": int(checkpoint.get("selection_cycle", 0)) + 1,
        "failed_accessions":{k:v for k,v in sorted(failed.items()) if k not in known}},separators=(",",":")))
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

