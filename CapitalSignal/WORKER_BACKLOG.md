# Capital Signal cloud worker backlog

## Operating rules
- Resume from this file and current repository state; verify prior claims against files and workflow runs.
- Work on one bounded task per run. Test changes before publishing. Never fabricate holdings, investor classifications, source evidence, or completion.
- No paid services, API spending, account creation, prospect contact, or regulated activity. Use existing authorized connections and public sources.
- Do not commit credentials. Do not start a second competing data refresh. Preserve existing website functionality.
- Record date, commit/run URLs, checks actually executed, next task, and exact blockers below after each run. Never claim an unattended cycle passed until its run completed.

## Current priority — SEC history, September 30, 2025 onward
The user requested all SEC filing history from 2025-09-30 and the existing investor calculations. Verify Backfill SEC filing history and daily Refresh SEC EDGAR public-data cache runs. Read SEC_HISTORY.md and data/history/status.json. Continue all-form catalogue discovery, raw submission downloads, and accession normalization; report pending/failed/normalization-error counts rather than declaring completion from catalogue counts. Fix parse failures from retained originals. Keep 13F/N-PORT report-period histories and per-period investor profiles intact, and never sum different fund periods together. Address the 750 MB Git-backed archive capacity boundary with the user before adding paid storage; no spending is authorized. Style and institution-wide orientation remain unknown until underlying evidence and denominators are sourced. Confirm first cloud backfill before marking this task complete.

## Earlier priority queue
1. Verify scheduled SEC refresh end to end: scripts execute, cache outputs validate, deployed site reads the refreshed data. Record coverage and failures.
2. Correct build_fund_firms.py's escaped word-boundary regex; test positive index fund names and negative active ETF names. Verify reported_value_usd against actual N-PORT cache schema before aggregating.
3. Prevent amended/duplicate N-PORT filings and repeated fund reporting periods from inflating registrant aggregates. Use latest valid filing per series/report date and preserve source evidence.
4. Expand manager and fund coverage with bounded, resumable ingestion and SEC rate-limit compliance. Persist checkpoints.
5. Add verified fund-to-adviser/13F-manager mappings; keep registrants separate from ultimate advisers until sourced.
6. Implement active/passive classification from verified fund mandates and equity-asset weights; preserve unknown coverage and institution-wide denominator limitations.
7. Build holdings-weighted investment style only with sourced point-in-time fundamentals; do not infer missing values.
8. Integrate N-PX voting evidence separately from ownership; validate issuer and fund identifiers.

## Initial checkpoint
Cloud workers are being configured. Existing refresh-sec.yml schedules the SEC pipeline at 08:17 UTC daily. Setup is not evidence that any new unattended run has completed. First development run should verify current state before modifying ingestion.

## Worker setup verified, November 7, 2026
- GitHub health worker passed: https://github.com/cstrohwork/aibank/actions/runs/42426250634 . It validates cache integrity and retains a report artifact; it does not certify complete coverage or website behavior.
- Daily development and monitoring tasks are enabled, starting November 8 around 08:00 and 10:00 America/New_York respectively. Their first unattended runs remain unverified. See CLOUD_WORKERS.md.
- Verified committed coverage: 2 investor profiles, 6 indexed 13F snapshots / 9,827 holdings, 12 fund snapshots / 23,454 holdings, 3 registrant groups. Earlier larger counts are not substantiated by this repository snapshot.
- Next: priority 1 end-to-end refresh/deployment verification, then priority 2 classification correction. No paid API or external account was configured.
