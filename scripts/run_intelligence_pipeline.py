#!/usr/bin/env python3
"""Rebuild intelligence products from committed source caches, preserving failures."""
import datetime as dt
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
STAGES = (
    ("identity", "build_identity_master.py"),
    ("ownership_history", "reconcile_ownership.py"),
    ("market_inputs_liquidity", "market_inputs.py"),
    ("mandates_targeting", "investor_intelligence.py"),
    ("benchmark_diagnostics", "match_fundamental_portfolios.py"),
    ("model_readiness", "build_model_data.py"),
    ("filing_signals", "parse_investor_events.py"),
    ("coverage_events", "intelligence_health.py"),
)

def rebuild(root=ROOT, runner=subprocess.run):
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    stages = []
    out = root / "CapitalSignal/data/intelligence/pipeline_status.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    def checkpoint():
        report = {"started_at": started, "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "status": "failed" if any(s["status"] == "failed" for s in stages) else
                            "completed" if len(stages) == len(STAGES) else "running",
                  "scope": "Calculation execution only; successful execution does not certify source coverage or Model activation.",
                  "stages": stages}
        temp = out.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2) + "\n")
        temp.replace(out)
        return report
    checkpoint()
    for name, script in STAGES:
        try:
            result = runner([sys.executable, str(root / "scripts" / script)], cwd=root,
                            capture_output=True, text=True, timeout=480)
            stage = {"name": name, "script": script, "status": "passed" if result.returncode == 0 else "failed",
                     "return_code": result.returncode,
                     "stdout_tail": result.stdout[-2000:], "stderr_tail": result.stderr[-2000:]}
        except (OSError, subprocess.TimeoutExpired) as exc:
            stage = {"name": name, "script": script, "status": "failed", "error": str(exc)}
        stages.append(stage)
        checkpoint()
        print(f"{name}: {stage['status']}", flush=True)
    return checkpoint()

if __name__ == "__main__":
    sys.exit(rebuild()["status"] == "failed")
