#!/usr/bin/env python3
"""Build fund-to-firm ownership attribution from SEC N-PORT series data.
Registrant is a legal filing entity, not necessarily the ultimate adviser.
"""
import json,pathlib,collections,re
ROOT=pathlib.Path(__file__).resolve().parents[1]/"CapitalSignal"/"data"
DIR=ROOT/"funds"
index=json.loads((DIR/"index.json").read_text())
firms=collections.defaultdict(lambda:{"funds":[],"equity_assets_usd":0.0,"active_equity_assets_usd":0.0,"passive_equity_assets_usd":0.0,"unclassified_equity_assets_usd":0.0})
bycusip=collections.defaultdict(list)
for entry in index["funds"]:
    data=json.loads((DIR/entry["file"]).read_text())
    key=entry["registrant_cik"];firm=firms[key]
    firm["registrant_cik"]=key;firm["registrant_name"]=entry["registrant_name"]
    # Classification is at fund level. Explicit index-tracking names only; other
    # fund names cannot reliably establish active status.
    name=entry["fund_name"]
    passive=bool(re.search(r"\b(index fund|index etf|index portfolio)\b",name,re.I))
    # ETF alone is not a passive classification; actively managed ETFs exist.
    orientation="passive" if passive else "unclassified"
    equities=[h for h in data["holdings"] if h["asset_category"] in ("EC","EP")]
    equity_value=sum(max(0,float(h["reported_value_usd"])) for h in equities)
    firm["equity_assets_usd"]+=equity_value
    firm[orientation+"_equity_assets_usd"]+=equity_value
    firm["funds"].append({"series_id":entry["series_id"],"fund_name":name,"report_date":entry["report_date"],"orientation":orientation,"orientation_basis":"explicit_index_fund_name" if passive else "not_verified","reported_equity_assets_usd":round(equity_value,2),"source":entry["source"]})
    for h in equities:
        bycusip[h["cusip"]].append({"registrant_cik":key,"registrant_name":entry["registrant_name"],"series_id":entry["series_id"],"fund_name":name,"report_date":entry["report_date"],"value_usd":h["reported_value_usd"],"source":entry["source"]})
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
(ROOT/"fund_firms.json").write_text(json.dumps({"firms":out,"methodology":"Registrant groupings from SEC N-PORT filings; fund equity assets sum disclosed EC and EP positions. No attribution to 13F managers or adviser groups without verified mapping. Ratios use only sampled fund assets and are NOT institution-wide. Explicit index fund name is passive evidence; other funds unclassified."},separators=(",",":")))
(DIR/"ownership_by_cusip.json").write_text(json.dumps({"securities":bycusip,"note":"Disclosed N-PORT fund holdings, with registrant attribution, not a complete issuer register."},separators=(",",":")))
print("registrant groups",len(out),"funds",sum(x["fund_count"] for x in out),"equity securities",len(bycusip))
