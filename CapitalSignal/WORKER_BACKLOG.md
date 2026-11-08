# Capital Signal cloud worker backlog

## Operating rules
- Resume from this file and current repository state; verify prior claims against files and workflow runs.
- Work on one bounded task per run. Test changes before publishing. Never fabricate holdings, investor classifications, source evidence, or completion.
- No paid services, API spending, account creation, prospect contact, or regulated activity. Use existing authorized connections and public sources.
- Do not commit credentials. Do not start a second competing data refresh. Preserve existing website functionality.
- Record date, commit/run URLs, checks actually executed, next task, and exact blockers below after each run. Never claim an unattended cycle passed until its run completed.

## Current priority — SEC history, September 30, 2025 onward
The user requested all SEC filing history from 2025-09-30 and the existing investor calculations. Verify Backfill SEC filing history and daily Refresh SEC EDGAR public-data cache runs. Read SEC_HISTORY.md and data/history/status.json. Continue all-form catalogue discovery, raw submission downloads, and accession normalization; report pending/failed/normalization-error counts rather than declaring completion from catalogue counts. Fix parse failures from retained originals. Keep 13F/N-PORT report-period histories and per-period investor profiles intact, and never sum different fund periods together. Raw originals now publish to checksum-verified daily GitHub release shards. The 750 MB cap is only a staging guard if publication fails; no paid storage was enabled. Keep normalized holdings/history storage scalable as coverage expands; do not grow unbounded raw blobs in Git. Style and institution-wide orientation remain unknown until underlying evidence and denominators are sourced. Confirm first cloud backfill before marking this task complete.

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

## Historical backfill checkpoint — November 7, 2026
Successful cloud run: https://github.com/cstrohwork/aibank/actions/runs/42427119447 . It catalogued 993,066 public filings since 2025-09-30 and persisted the first 120 complete submissions with zero index/download/normalization errors. Rebuilt cache: 28 manager/report-period snapshots across 2025-09-30, 2025-12-31, 2026-03-31 and 2026-06-30. Original September 2025 Berkshire submission was independently normalized: 115 positions, reported non-option equity value $267,334,501,955, filing address Omaha. Full-market backfill remains incomplete. Eleven local tests pass, including source checksum round-trip and preserving originals on failed release upload. Verify first release-backed publication run before considering migration complete.

## Release-backed history verified — November 7, 2026
Cloud run https://github.com/cstrohwork/aibank/actions/runs/42427523310 passed every stage, including release upload, historical rebuild, integrity checks and checkpoint commit. Confirmed status: 993,066 catalogued filings; 240 complete submissions archived; 992,826 pending; zero index/download/normalization errors. Coverage: 55 managers, 61 manager/report-period snapshots, and 12 fund/report-period snapshots (fund backfill to September 2025 is still incomplete). The first 120-submission release shard was independently downloaded and every original SHA-256 checksum verified. Raw storage is release-backed, with zero staged raw bytes in Git. Hourly batch capacity has been increased to 1,000 submissions subject to 60 MB / 20 minute bounds. Continue backfill and normalization; prioritize complete September 2025 fund coverage, verified adviser attribution, point-in-time style fundamentals, and storage scaling for normalized holdings. Never equate the 993,066-entry catalogue with completed downloads.

## Development checkpoint — November 8, 2026: N-PORT cutoff repair
- Inspected current main 108306a41bd3fd0d8f77d1e27788352d403d3f75, all repository paths for AGENTS.md (none present), this backlog, SEC_HISTORY.md, archive state, history status, open PRs (none), and recent workflow runs. No in-progress refresh was observed; no competing refresh was started.
- Completed one bounded parser fix on branch `fix/capitalsignal-nport-report-cutoff-20261108`: apply N-PORT report-date cutoff before supported-position and series validation. Confirmed from checksum-verified retained original 0002071691-25-002515 that its zero-asset report is dated 2025-05-31 and belongs outside the holdings window.
- Validation actually executed: 11 baseline tests passed; new regression cases reproduced two errors and one failure before the fix; all 17 tests passed afterward. Replayed both retained error submissions: old report excluded, missing series still explicitly unresolved. Full evidence, checksums, public source/run URLs: [validation/2026-11-08-nport-cutoff.md](validation/2026-11-08-nport-cutoff.md).
- Existing completed successful runs inspected: [refresh](https://github.com/cstrohwork/aibank/actions/runs/42493354266), [backfill](https://github.com/cstrohwork/aibank/actions/runs/42486674927), [health](https://github.com/cstrohwork/aibank/actions/runs/42493438391), [Pages](https://github.com/cstrohwork/aibank/actions/runs/42493430787). These precede this patch; patch cloud execution/deployment is unverified.
- Measured main checkpoint remains 993,066 catalogued / 3,096 archived / 989,970 pending; three download failures and two normalization failures. Runtime counters were not manually changed. Coverage is incomplete; source provenance and unknown classifications remain intact.
- Next: review/merge this isolated fix, then verify the existing serialized backfill retries and clears the out-of-window amendment error. Do not repeat the parser fix. Then implement bounded streamed archival for the three oversized submissions.
- Exact blockers: N-PORT 0000894189-25-011392 lacks seriesId in retained XML; do not invent fund mapping. Downloads 0000929638-25-003679, 0000929638-25-003681, 0000929638-25-003682 exceed the 80 MB response cap. No source fundamentals/adviser evidence was added, so unknown styles/orientations remain unknown. The earlier generic scheduled-task failure exposed no diagnostic; unattended development-worker recovery is unverified.
