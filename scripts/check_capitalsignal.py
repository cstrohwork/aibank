#!/usr/bin/env python3
"""Validate committed CapitalSignal caches without downloading SEC data."""
import datetime
import json
import math
import pathlib
import sys

def check(root):
    errors, warnings, counts = [], [], {}
    def read(path):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
            return {}
    for folder, key, ids in (("13f", "managers", ("manager_cik", "report_date")),
                              ("funds", "funds", ("series_id", "report_date"))):
        directory = root / folder
        index = read(directory / "index.json")
        entries = index.get(key, [])
        counts[folder + "_snapshots"] = len(entries)
        if not entries:
            errors.append(f"{folder}: empty index")
        seen = set()
        holdings_count = 0
        for entry in entries:
            identity = tuple(entry.get(k) for k in ids)
            if not all(identity) or identity in seen:
                errors.append(f"{folder}: missing or duplicate identity {identity}")
            seen.add(identity)
            file = entry.get("file", "")
            path = directory / file
            if not file or path.resolve().parent != directory.resolve():
                errors.append(f"{folder}: invalid snapshot path")
                continue
            data = read(path)
            holdings = data.get("holdings", [])
            holdings_count += len(holdings)
            if len(holdings) != entry.get("holdings_count"):
                errors.append(f"{file}: holdings count differs from index")
            if not holdings:
                errors.append(f"{file}: no holdings")
            value_key = "value_thousands" if folder == "13f" else "reported_value_usd"
            for h in holdings:
                try:
                    value = float(h[value_key])
                    if not math.isfinite(value) or value < 0:
                        raise ValueError("invalid amount")
                except (KeyError, TypeError, ValueError):
                    errors.append(f"{file}: missing/invalid {value_key}")
                    break
        counts[folder + "_holdings"] = holdings_count
        if index.get("errors"):
            warnings.append(f"{folder}: ingestion reported {len(index['errors'])} errors; inspect source index")
    profiles = read(root / "investor_profiles.json").get("profiles", [])
    counts["profiles"] = len(profiles)
    if not profiles:
        errors.append("No investor profiles")
    firms = read(root / "fund_firms.json").get("firms", [])
    counts["registrant_groups"] = len(firms)
    if not firms:
        errors.append("No registrant groups")
    return {"checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": "failed" if errors else "passed", "counts": counts,
            "errors": errors, "warnings": warnings,
            "scope": "Cache structure and numeric integrity only; does not certify completeness, freshness or live website behavior."}

if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1] / "CapitalSignal" / "data"
    report = check(root)
    pathlib.Path("worker-health.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    sys.exit(bool(report["errors"]))
