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
