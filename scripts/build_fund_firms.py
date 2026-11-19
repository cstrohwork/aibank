#!/usr/bin/env python3
"""Build fund-to-firm ownership attribution from SEC N-PORT series data.
Registrant is a legal filing entity, not necessarily the ultimate adviser.
"""
import json,pathlib,collections,re,math
from fund_ownership_index import write_ownership_index
ROOT=pathlib.Path(__file__).resolve().parents[1]/"CapitalSignal"/"data"
DIR=ROOT/"funds"
index=json.loads((DIR/"index.json").read_text())
firms=collections.defaultdict(lambda:{"funds":[],"equity_assets_usd":0.0,"active_equity_assets_usd":0.0,"passive_equity_assets_usd":0.0,"unclassified_equity_assets_usd":0.0})
bycusip=collections.defaultdict(list)
# Reconcile same-period filings by verified SEC filing date and accession.
# Never infer precedence from local filenames or download timestamps.
history_path=DIR/"history_index.json"
candidates=json.loads(history_path.read_text()).get("funds",[]) if history_path.exists() else index["funds"]
# Group all candidate filings before choosing a period winner. A same-day
# conflict in an older filing must not disqualify a later, independently
# verified filing for the same series/reporting period.
by_period=collections.defaultdict(list)
for entry in candidates:
    series=(str(entry.get("registrant_cik") or ""),str(entry.get("series_id") or entry.get("fund_id") or ""))
    if all(series) and entry.get("report_date"):
        by_period[series+(entry["report_date"],)].append(entry)
selected={}
ambiguous=set()
for key, entries in by_period.items():
    # Duplicate index references to the same source are harmless.
    unique={(str(e.get("file") or ""), str(e.get("accession") or ""), str(e.get("filing_date") or ""), str(e.get("source") or "")): e for e in entries}
    entries=list(unique.values())
    if len(entries)==1:
        selected[key]=entries[0]
        continue
    # Without dates and accession evidence for every candidate, precedence
    # cannot be established safely. Accessions themselves are not timestamps.
    if any(not e.get("filing_date") or not e.get("accession") for e in entries):
        ambiguous.add(key)
        continue
    newest=max(str(e["filing_date"]) for e in entries)
    winners=[e for e in entries if str(e["filing_date"])==newest]
    if len({str(e["accession"]) for e in winners})!=1:
        ambiguous.add(key)
        continue
    # Same accession can occur twice in a cache; require consistent source.
    if len({(str(e.get("file") or ""), str(e.get("source") or "")) for e in winners})!=1:
        # Identical accessions with conflicting cache files or source URLs
        # cannot establish one auditable holdings snapshot.
        ambiguous.add(key)
        continue
    selected[key]=winners[0]
# A newer unresolved reporting period must not silently fall back to an
# older period and present stale positions as the latest fund exposure.
# Keep the entire series out until the newest period is reconciled.
newest_period_by_series={}
for key in by_period:
    series=key[:2]
    if series not in newest_period_by_series or key[2]>newest_period_by_series[series]:
        newest_period_by_series[series]=key[2]
blocked_latest_series={
    key[:2] for key in ambiguous
    if key[2]==newest_period_by_series.get(key[:2])
}
latest={}
for key,entry in selected.items():
    series=key[:2]
    if series in blocked_latest_series:
        continue
    if series not in latest or key[2]>latest[series]["report_date"]:
        latest[series]=entry
for entry in latest.values():
    data=json.loads((DIR/entry["file"]).read_text())
    key=entry["registrant_cik"]
    # Classification is at fund level. Explicit index-tracking names only; other
    # fund names cannot reliably establish active status.
    name=entry["fund_name"]
    passive=bool(re.search(r"\b(index fund|index etf|index portfolio)\b",name,re.I))
    # ETF alone is not a passive classification; actively managed ETFs exist.
    orientation="passive" if passive else "unclassified"
    equities=[h for h in data["holdings"] if h["asset_category"] in ("EC","EP")]
    # Reject malformed/nonfinite amounts instead of contaminating aggregate values.
    # Withhold the entire series rather than silently publishing partial exposure.
    values=[]
    invalid=False
    for h in equities:
        try:
            value=float(h["reported_value_usd"])
            if not math.isfinite(value) or value < 0:
                invalid=True
                break
            values.append(value)
        except (KeyError, TypeError, ValueError, OverflowError):
            invalid=True
            break
    if invalid:
        continue
    equity_value=sum(values)
    firm=firms[key]
    firm["registrant_cik"]=key;firm["registrant_name"]=entry["registrant_name"]
    firm["equity_assets_usd"]+=equity_value
    firm[orientation+"_equity_assets_usd"]+=equity_value
    firm["funds"].append({"fund_id":entry.get("fund_id") or entry["series_id"],"series_id":entry["series_id"],"fund_name":name,"report_date":entry["report_date"],"filing_date":entry.get("filing_date"),"accession":entry.get("accession"),"orientation":orientation,"orientation_basis":"explicit_index_fund_name" if passive else "not_verified","reported_equity_assets_usd":round(equity_value,2),"source":entry["source"]})
    for h in equities:
        if not h.get("cusip"):continue
        bycusip[h["cusip"]].append({"registrant_cik":key,"registrant_name":entry["registrant_name"],"fund_id":entry.get("fund_id") or entry["series_id"],"series_id":entry["series_id"],"fund_name":name,"report_date":entry["report_date"],"filing_date":entry.get("filing_date"),"accession":entry.get("accession"),"value_usd":h["reported_value_usd"],"source":entry["source"]})
out=[]
for firm in firms.values():
    total=firm["equity_assets_usd"]
    firm["fund_count"]=len(firm["funds"])
    firm["passive_pct_of_disclosed_sample_equity_assets"]=round(100*firm["passive_equity_assets_usd"]/total,2) if total else None
    firm["active_pct_of_disclosed_sample_equity_assets"]=round(100*firm["active_equity_assets_usd"]/total,2) if total else None
    firm["unclassified_pct_of_disclosed_sample_equity_assets"]=round(100*firm["unclassified_equity_assets_usd"]/total,2) if total else None
    firm["institution_wide_equity_aum_usd"]=None
    firm["institution_wide_orientation"]=None
    firm["coverage"]="sample_only_incomplete_fund_universe"
    for k in ("equity_assets_usd","active_equity_assets_usd","passive_equity_assets_usd","unclassified_equity_assets_usd"):firm[k]=round(firm[k],2)
    out.append(firm)
(ROOT/"fund_firms.json").write_text(json.dumps({"firms":out,"excluded_ambiguous_series_periods":len(ambiguous),"excluded_series_with_ambiguous_latest_period":len(blocked_latest_series),"methodology":"Latest verified filing-date/accession per series/report period; conflicting or undated duplicates excluded; series with unresolved newest periods withheld rather than using stale older positions. Registrant groupings from SEC N-PORT filings; fund equity assets sum disclosed EC and EP positions. No attribution to 13F managers or adviser groups without verified mapping. Ratios use only sampled fund assets and are NOT institution-wide. Explicit index fund name is passive evidence; other funds unclassified."},separators=(",",":")))
write_ownership_index(DIR, bycusip, "Disclosed N-PORT fund holdings, with registrant attribution, not a complete issuer register.")
print("registrant groups",len(out),"funds",sum(x["fund_count"] for x in out),"equity securities",len(bycusip))
