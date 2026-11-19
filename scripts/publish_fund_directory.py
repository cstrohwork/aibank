#!/usr/bin/env python3
"""Publish verified N-PORT series evidence separately from 13F manager profiles."""
import argparse
import datetime as dt
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "CapitalSignal/data/fund_firms.json"
OUT = ROOT / "CapitalSignal/spotlight/funds"

def run(batch=200):
    if not SOURCE.exists():
        raise FileNotFoundError("N-PORT registrant aggregate not yet generated")
    firms = json.loads(SOURCE.read_text()).get("firms", [])
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_file = OUT / "manifest.json"
    manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else {"profiles": {}, "failures": {}}
    profiles = manifest.setdefault("profiles", {})
    failures = manifest.setdefault("failures", {})
    candidates = []
    for firm in firms:
        for fund in firm.get("funds", []):
            cik = str(firm.get("registrant_cik") or "").zfill(10)
            series = str(fund.get("series_id") or "")
            if not (cik.isdigit() and len(cik) == 10 and series.startswith("S") and series[1:].isdigit()):
                continue
            source = fund.get("source")
            if not (isinstance(source, str) and source.startswith("https://www.sec.gov/")):
                continue
            identifier = cik + "/" + series
            evidence = {"registrant_cik": cik, "registrant_name": firm.get("registrant_name"),
                        "series_id": series, "fund_name": fund.get("fund_name"),
                        "report_date": fund.get("report_date"), "filing_date": fund.get("filing_date"),
                        "accession": fund.get("accession"), "source": source,
                        "reported_equity_assets_usd": fund.get("reported_equity_assets_usd"),
                        "orientation": fund.get("orientation") or "unclassified",
                        "orientation_basis": fund.get("orientation_basis") or "not_verified",
                        "scope": "disclosed_N_PORT_series_equity_holdings_not_total_AUM",
                        "adviser_identity": None, "institution_wide_orientation": None}
            fingerprint = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
            candidates.append((identifier, evidence, fingerprint))
    # One current profile per stable registrant/series identifier. The aggregate
    # may contain multiple reporting periods; never let an older row overwrite
    # newer evidence merely because its reported exposure is larger.
    latest_by_id = {}
    for candidate in candidates:
        identifier, evidence, _ = candidate
        prior = latest_by_id.get(identifier)
        key = (evidence.get("report_date") or "", evidence.get("filing_date") or "",
               evidence.get("accession") or "")
        if prior is None or key > (prior[1].get("report_date") or "",
                                   prior[1].get("filing_date") or "",
                                   prior[1].get("accession") or ""):
            latest_by_id[identifier] = candidate
    candidates = list(latest_by_id.values())
    candidates.sort(key=lambda item: (item[1].get("reported_equity_assets_usd") or 0,
                                      item[1].get("filing_date") or ""), reverse=True)
    # Missing published artifacts must be repaired even when the fingerprint matches.
    # Cool down only repeated failures for identical evidence; fresh filings bypass it.
    now = dt.datetime.now(dt.timezone.utc)
    def eligible(item):
        identifier, _, fingerprint = item
        failure = failures.get(identifier, {})
        if not isinstance(failure, dict) or failure.get("fingerprint") != fingerprint:
            return True
        try:
            previous = dt.datetime.fromisoformat(failure["last_attempt_at"])
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=dt.timezone.utc)
            delay = min(360, 5 * 2 ** min(max(int(failure.get("attempts", 1))-1, 0), 7))
            return now - previous >= dt.timedelta(minutes=delay)
        except (KeyError, ValueError, TypeError, OverflowError):
            return True
    def needs_work(item):
        identifier, evidence, fingerprint = item
        target = OUT / identifier
        if (profiles.get(identifier, {}).get("fingerprint") != fingerprint
                or not (target / "index.html").is_file()
                or not (target / "versions" / (fingerprint + ".json")).is_file()):
            return True
        # An existing file is not proof of a valid publication. Requeue
        # truncated or stale JSON rather than silently marking it complete.
        try:
            published = json.loads((target / "profile.json").read_text())
            versioned = json.loads((target / "versions" / (fingerprint + ".json")).read_text())
            page = (target / "index.html").read_text()
            # Check content, not merely existence: a truncated HTML page or
            # corrupted historical evidence must re-enter the publication queue.
            return (published != evidence or versioned != evidence
                    or "<h1>" not in page or "Original SEC filing" not in page
                    or fingerprint not in page)
        except (OSError, ValueError, TypeError, UnicodeError):
            return True
    new = [x for x in candidates if x[0] not in profiles and eligible(x)]
    changed = [x for x in candidates if x[0] in profiles and needs_work(x) and eligible(x)]
    # Reserve at least 25% for first publication; do not starve updates.
    reserve = min(len(new), max(1, batch // 4))
    selected = new[:reserve] + changed[:max(0, batch-reserve)]
    selected += new[reserve:reserve + max(0, batch-len(selected))]
    selected += changed[max(0,batch-reserve):max(0,batch-reserve)+max(0,batch-len(selected))]
    done = 0
    for identifier, evidence, fingerprint in selected:
        try:
            target = OUT / identifier
            target.mkdir(parents=True, exist_ok=True)
            versions = target / "versions"
            versions.mkdir(exist_ok=True)
            content = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
            (versions / (fingerprint + ".json")).write_text(content)
            (target / "profile.json").write_text(content)
            esc = lambda v: html.escape(str(v if v is not None else "Unknown"), quote=True)
            rows = "".join("<tr><th>"+esc(k)+"</th><td>"+esc(v)+"</td></tr>" for k,v in evidence.items() if k != "source")
            history = "".join('<li><a href="versions/'+esc(p.name)+'">'+esc(p.stem)+'</a></li>' for p in sorted(versions.glob("*.json")))
            page = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>'+esc(evidence["fund_name"])+
                    '</title><style>body{font:16px Arial,sans-serif;max-width:900px;margin:3rem auto;padding:1rem;color:#193350}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:left}table{border-collapse:collapse}</style>'+
                    '<h1>'+esc(evidence["fund_name"])+'</h1><p>SEC N-PORT series disclosure; not total AUM or verified adviser attribution.</p><table>'+rows+
                    '</table><p><a href="'+esc(evidence["source"])+'">Original SEC filing</a></p><h2>Version history</h2><ul>'+history+
                    '</ul><a href="../../">Fund directory</a></html>')
            (target / "index.html").write_text(page)
            profiles[identifier] = {"fingerprint": fingerprint, "report_date": evidence["report_date"]}
            failures.pop(identifier, None)
            done += 1
        except Exception as exc:
            previous = failures.get(identifier, {})
            attempts = (previous.get("attempts", 0) if isinstance(previous, dict)
                        and previous.get("fingerprint") == fingerprint else 0) + 1
            failures[identifier] = {"fingerprint": fingerprint, "attempts": attempts,
                                    "last_attempt_at": now.isoformat(), "last_error": str(exc)}
    pending = [x[0] for x in candidates if needs_work(x)]
    eligible_pending = sum(1 for x in candidates if needs_work(x) and eligible(x))
    manifest.update(discovered_count=len(candidates), completed_current_count=len(candidates)-len(pending),
                    pending_count=len(pending), eligible_pending_count=eligible_pending, changed_this_run=done, next_batch=pending[:200],
                    scope="verified_N_PORT_series_from_current_aggregated_cache_not_complete_universe")
    manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    # Small, independently readable checkpoint for monitoring and reconciliation.
    # Never copy the potentially enormous profile map into this summary.
    checkpoint = {key: manifest[key] for key in (
        "discovered_count", "completed_current_count", "pending_count",
        "changed_this_run", "eligible_pending_count", "scope")}
    checkpoint["failed_count"] = len(failures)
    checkpoint["next_batch_count"] = len(manifest["next_batch"])
    (OUT / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n")
    listing = "".join('<li><a href="'+html.escape(k,quote=True)+'/">'+html.escape(k)+'</a></li>' for k in sorted(profiles))
    (OUT/"index.html").write_text('<!doctype html><html><meta charset="utf-8"><title>N-PORT fund profiles</title><h1>Disclosed N-PORT fund series</h1><p>Incomplete sampled universe; no verified adviser attribution or total AUM.</p><ul>'+listing+'</ul></html>')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ("profiles","failures","next_batch")}))
    return manifest

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=200)
    run(parser.parse_args().batch_size)
