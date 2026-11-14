#!/usr/bin/env python3
"""Bounded, resumable investor readiness queue. Does not assert SEC filing validation."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "CapitalSignal" / "data" / "intelligence"
SOURCE = ROOT / "investor_readiness.json"
DEST = ROOT / "profile_processing_queue.json"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=10)
    args = ap.parse_args()
    if args.batch_size < 1:
        raise SystemExit("batch-size must be positive")
    source = json.loads(SOURCE.read_text())
    prior = json.loads(DEST.read_text()) if DEST.exists() else {}
    # The existing operational checkpoint uses schema_version=1 with "items".
    # Never overwrite it with an incompatible "records" checkpoint: that would
    # discard accession fingerprints, retries, and validation evidence.
    if "items" in prior and "records" not in prior:
        items = prior["items"]
        # Expand the discovered universe incrementally without discarding prior evidence.
        known = {str(x["id"]) for x in items}
        pool = []
        for kind, field, id_field, name_field in (
            ("manager", "managers", "manager_id", "manager_name"),
            ("fund", "funds", "fund_id", "fund_name"),
        ):
            for obj in source.get(field, []):
                raw_id = obj.get(id_field)
                if not raw_id:
                    continue
                ident = str(raw_id)
                if ident in known:
                    continue
                pool.append((kind, ident, obj, name_field))
        pool.sort(key=lambda row: (
            -(float(row[2].get("reported_value_usd") or row[2].get("reported_common_equity_value_usd") or 0)),
            row[1]))
        discovery_limit = min(5, args.batch_size)
        for kind, ident, obj, name_field in pool[:discovery_limit]:
            items.append({
                "id": ident, "name": obj.get(name_field) or ident,
                "kind": kind, "status": "pending",
                "report_date": obj.get("report_date"),
                "source_url": obj.get("source_url"),
                "reported_13f_value_usd": None,
                "retries": 0,
                "reason": "Newly discovered from readiness index; source and monetary units not independently validated",
            })
            known.add(ident)
        prior.setdefault("discovery", {})["readiness_unqueued_remaining"] = len(pool) - min(discovery_limit, len(pool))
        prior["discovery"]["readiness_last_expanded_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        # Perform bounded, actual cached-source reconciliation before rotating.
        # This does not certify SEC monetary totals or authorize publication.
        processed = []
        for item in [x for x in items if x.get("status") == "pending" and x.get("source_file")][:min(3, args.batch_size)]:
            path = ROOT.parents[2] / item["source_file"]
            item["last_checked_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            try:
                if not path.is_file():
                    raise FileNotFoundError(str(path))
                with path.open(encoding="utf-8") as stream:
                    filing = json.load(stream)
                if not isinstance(filing, dict) or not isinstance(filing.get("holdings"), list):
                    raise ValueError("missing holdings array")
                if str(filing.get("report_date")) != str(item.get("report_date")):
                    raise ValueError("reporting period mismatch")
                accession = filing.get("accession") or filing.get("accession_number")
                if not accession:
                    raise ValueError("missing accession")
                item["accession_fingerprint"] = str(accession)
                item["holdings_count"] = len(filing["holdings"])
                item["source_blob_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                item["cached_source_reconciled"] = True
                item["last_error_code"] = None
                item["reason"] = ("Cached holdings, period and accession reconciled; original SEC summary, "
                                  "monetary units, amendments and newer filings remain unverified. Not publishable.")
                processed.append({"id": item["id"], "result": "cached_evidence_reconciled"})
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                item["retries"] = int(item.get("retries") or 0) + 1
                item["last_error_code"] = type(exc).__name__
                item["reason"] = "Cached-source reconciliation failed: " + str(exc)[:180]
                processed.append({"id": item["id"], "result": "retry_required"})
        prior["last_processing_batch"] = processed
        # Rotate across pending investors instead of repeatedly selecting the same
        # first ten (which previously produced no progress on oversized filings).
        # This advances a durable selection cursor without falsely validating data.
        pending = [r for r in items if r.get("status") == "pending"]
        pending.sort(key=lambda r: (r.get("retries", 0), r.get("filing_date") or "", r["id"]))
        cursor = int(prior.get("selection_cursor", 0))
        selected = ([pending[(cursor + i) % len(pending)]
                     for i in range(min(args.batch_size, len(pending)))]) if pending else []
        prior["next_batch"] = [r["id"] for r in selected]
        prior["selection_cursor"] = (cursor + len(selected)) % len(pending) if pending else 0
        prior["last_queue_selection_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        prior["last_selection_warning"] = (
            "Rotating queue selection only: no holdings validated or profiles published."
        )
        prior["counts"] = {state: sum(r.get("status") == state for r in items)
                           for state in ("pending", "validated_pending_publication", "published", "failed", "blocked")}
        DEST.write_text(json.dumps(prior, indent=2) + "\n")
        print(json.dumps({"counts": prior["counts"], "next_batch": prior["next_batch"],
                          "warning": "selection only; no validation or publication performed"}))
        return
    old = {r["id"]: r for r in prior.get("records", [])}
    candidates = []
    for kind, key in (("manager", "managers"), ("fund", "funds")):
        for obj in source.get(key, []):
            identifier = obj.get("manager_id") if kind == "manager" else obj.get("fund_id")
            if not identifier:
                continue
            identity = kind + ":" + str(identifier)
            evidence = {"source_url": obj.get("source_url"), "report_date": obj.get("report_date"),
                        "value": obj.get("reported_common_equity_value_usd") if kind == "fund" else obj.get("reported_value_usd")}
            fingerprint = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
            prev = old.get(identity, {})
            changed = prev.get("fingerprint") != fingerprint
            state = "pending" if changed else prev.get("state", "pending")
            if state not in ("pending", "completed", "failed", "blocked"):
                state = "pending"
            candidates.append({"id": identity, "kind": kind, "fingerprint": fingerprint,
                               "state": state, "attempts": prev.get("attempts", 0),
                               "report_date": evidence["report_date"], "source_url": evidence["source_url"],
                               "reported_exposure_usd": evidence["value"],
                               "last_error": None if changed else prev.get("last_error"),
                               "publication_verified": prev.get("publication_verified", False) if not changed else False})
    candidates.sort(key=lambda r: (r["state"] != "pending", -(r["reported_exposure_usd"] or 0), r["id"]))
    pending = [r for r in candidates if r["state"] == "pending"]
    # This pass establishes an evidence queue only. Never mark published or validated from cache alone.
    batch = pending[:args.batch_size]
    result = {"schema_version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "source_generated_at": source.get("generated_at"),
              "universe_definition": "distinct cached manager/fund IDs in investor_readiness.json; not all SEC filers",
              "records": candidates, "next_batch": [r["id"] for r in batch],
              "counts": {s: sum(r["state"] == s for r in candidates) for s in ("pending", "completed", "failed", "blocked")}}
    DEST.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"counts": result["counts"], "next_batch": result["next_batch"]}))

if __name__ == "__main__":
    main()
