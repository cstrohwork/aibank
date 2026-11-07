#!/usr/bin/env python3
"""Build evidence-tagged manager profiles from cached public 13F snapshots.
13F value is not total equity AUM. Turnover is an estimated trading proxy.
"""
import json,pathlib,collections,datetime,statistics
ROOT=pathlib.Path(__file__).resolve().parents[1]/"CapitalSignal"/"data"
DIR=ROOT/"13f"
index=json.loads((DIR/"index.json").read_text())
grouped=collections.defaultdict(list)
for entry in index["managers"]:
    path=DIR/entry["file"]
    if path.exists():
        grouped[entry["manager_cik"]].append(json.loads(path.read_text()))
fund_file=ROOT/"fund_assets_verified.json"
fund_records=json.loads(fund_file.read_text()).get("funds",[]) if fund_file.exists() else []
profiles=[]
for cik,periods in sorted(grouped.items()):
    periods.sort(key=lambda x:x["report_date"])
    latest=periods[-1]
    def positions(period):
        out=collections.defaultdict(lambda:[0.0,0.0])
        for h in period["holdings"]:
            if h.get("put_call"):continue
            try:
                shares=float(str(h.get("shares","")).replace(",",""))
                val=float(h["value_thousands"])
                if shares<=0 or val<0:continue
                key=(h["cusip"],h.get("class",""))
                out[key][0]+=shares
                out[key][1]+=val
            except (ValueError,TypeError,KeyError):continue
        return out
    values=[sum(float(h.get("value_thousands",0)) for h in p["holdings"]) for p in periods]
    turns=[]
    for prev,cur in zip(periods,periods[1:]):
        a,b=positions(prev),positions(cur)
        buys=sells=0.0
        for key in a.keys()|b.keys():
            before=a.get(key,[0,0]);after=b.get(key,[0,0])
            price=before[1]/before[0] if before[0]>0 else (after[1]/after[0] if after[0]>0 else 0)
            delta=(after[0]-before[0])*price
            buys+=max(delta,0)
            sells+=max(-delta,0)
        avg=(sum(x[1] for x in a.values())+sum(x[1] for x in b.values()))/2
        days=(datetime.date.fromisoformat(cur["report_date"])-datetime.date.fromisoformat(prev["report_date"])).days
        if avg>0 and days>0:
            turns.append({"from":prev["report_date"],"to":cur["report_date"],"estimated_two_way_turnover_annualized_pct":round(min(buys,sells)/avg*365.25/days*100,2),"estimated_gross_churn_annualized_pct":round((buys+sells)/avg*365.25/days*100,2)})
    p={"manager_cik":cik,"investor_name":latest["manager_name"],"city":None,"state":None,"country":None,"location_status":"not_enriched","equity_aum_usd":round(values[-1]),"equity_aum_status":"reported_13f_equity_exposure_proxy_not_total_institutional_equity_aum","reported_13f_value_usd":round(values[-1]),"latest_report_date":latest["report_date"],"periods_available":[x["report_date"] for x in periods],"turnover_intervals":turns,"annualized_turnover_proxy_pct":round(statistics.mean(x["estimated_two_way_turnover_annualized_pct"] for x in turns),2) if turns else None,"turnover_status":"estimated_from_13f_share_changes_not_actual_trades" if turns else "insufficient_history","investor_style":None,"style_status":"requires_point_in_time_fundamental_data","orientation":None,"orientation_status":"requires_verified_active_passive_classification","source_filings":[x["source"] for x in periods]}
    verified={}
    for fund in fund_records:
        if (fund.get("manager_cik")==cik and fund.get("report_date")==latest["report_date"]
            and fund.get("attribution_verified") is True and fund.get("non_overlapping") is True
            and fund.get("source_url") and fund.get("fund_id")
            and fund.get("orientation") in ("active","passive")):
            try:
                amount=float(fund["equity_assets_usd"])
                if amount>0: verified[fund["fund_id"]]=fund
            except (ValueError,TypeError,KeyError): pass
    active=sum(float(x["equity_assets_usd"]) for x in verified.values() if x["orientation"]=="active")
    passive=sum(float(x["equity_assets_usd"]) for x in verified.values() if x["orientation"]=="passive")
    classified=active+passive
    p["fund_orientation"]={"active_equity_assets_usd":round(active),"passive_equity_assets_usd":round(passive),
        "classified_equity_assets_usd":round(classified),"classified_fund_count":len(verified),
        "active_pct_of_classified_assets":round(active/classified*100,2) if classified else None,
        "passive_pct_of_classified_assets":round(passive/classified*100,2) if classified else None,
        "source_urls":sorted({x["source_url"] for x in verified.values()})}
    if classified:
        p["orientation"]="active" if active/classified>=.75 else "passive" if passive/classified>=.75 else "mixed"
        p["orientation_status"]="classified_fund_subset_only_not_institution_wide"
    p["active_pct_of_total_institution_equity_aum"]=None
    p["passive_pct_of_total_institution_equity_aum"]=None
    p["fund_coverage_pct_of_institution_equity_aum"]=None
    profiles.append(p)
(ROOT/"investor_profiles.json").write_text(json.dumps({"generated_from":"public SEC 13F cache","profiles":profiles,"methodology":"Reported 13F long holdings value is an equity exposure proxy, not verified total institution equity AUM. Turnover proxy is min(estimated buys,estimated sells) / average reported non-option portfolio value, annualized by elapsed days; trade prices approximated using preceding period value/share, or current for new holdings. Corporate actions, market changes, non-13F assets, confidential treatment and intraperiod trades cause errors. Do not treat as actual turnover.","style_methodology":"Future point-in-time weighted fundamental factor scores across holdings; no style assigned without reliable fundamentals.","orientation_methodology":"Active/passive mix is computed from independently verified non-overlapping underlying fund equity assets at the same report date. Shares refer to classified fund assets only; institution-wide percentages require complete equity AUM and coverage."},separators=(",",":")),encoding="utf-8")
print("investor profiles generated",len(profiles))
