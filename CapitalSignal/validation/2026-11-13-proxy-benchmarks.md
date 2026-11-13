# Separate ETF proxy benchmark implementation — November 13, 2026

## Selection and repository state
Read WORKER_BACKLOG.md and current repository/workflow state before editing. Initial source was pinned to b521af05226f6c1dfe63fc5aabc814c872209d85. Root, scripts, tests, CapitalSignal and CapitalSignal/validation directory listings contain no applicable AGENTS.md. PR #7 (head b0d2dfe695b8184c42073ab8574b4f7b65413bbc) is still open and owns missing-identifier and mixed-union-weight safeguards. Those changes were not repeated or overwritten.

Selected next unblocked fundamentals task: preserve separate SPTM and IWV source snapshots and implement per-provider benchmark field diagnostics. Current code already ingests the deduplicated union, so no duplicate ingestion was started. Publication is based on the newer main 3295ace45043d0fb692c1f96d3f7fc1e3cbebaa4, tree 9c2850463895295e576f254dde545b487fd9cf7a. The ingestion source blob SHA was rechecked unchanged at publication; backlog was retrieved from that base.

Reviewed scripts/ingest_sp1500_fundamentals.py, .github/workflows/sp1500-fundamentals.yml and data/fundamentals/status.json. Saved status is partial and dated November 12; two Companyfacts CIKs (0001492165, 0001569650) still have retained 404s and 13 securities are unmapped. Current run https://github.com/cstrohwork/aibank/actions/runs/43433691948 has passed its existing regression step, but ingestion was still in progress when inspected; no new checkpoint or completion inferred. Active history https://github.com/cstrohwork/aibank/actions/runs/43435502418 was also left undisturbed. Existing backfill https://github.com/cstrohwork/aibank/actions/runs/43434485071 and Pages https://github.com/cstrohwork/aibank/actions/runs/43435499638 completed successfully before this patch; they do not verify it.

## Bounded change
- Extracted merge_proxy_universes and retained both complete eligible provider snapshots (dates, retrieval timestamps, URLs, response SHA-256, membership basis, securities and excluded rows) in proxy_snapshots before deduplication discards secondary weights.
- Preserved existing union fields for compatibility and explicitly labelled first-provider security weight_pct as unsuitable for a combined benchmark.
- Contradictory CIK/CUSIP evidence on a deduplicated identity fails visibly instead of silently merging.
- New CLI: python scripts/benchmark_proxy_coverage.py --as-of YYYY-MM-DD. It writes proxy_benchmark_coverage.json with independent SPTM/IWV weighted field coverage, source provenance, unique issuer counts and each provider's own holdings-date fact cutoff.
- Missing caches and unmapped members remain in each denominator. Rounded zero-weight rows remain counted. Share classes contribute their actual separate weights while issuer counts deduplicate.
- Future provider snapshots, invalid/zero weights, missing source evidence and legacy union files lacking separate snapshots remain explicit blockers. Lost provider weights are never reconstructed from the combined union.
- These are current ETF holdings proxies, not official index membership. Historical comparison and calculated style stay blocked/null. No price, capitalization, listing or classification is inferred.

## Validation actually executed
Python 3.12.14, freshly retrieved isolated source directory; no assumption that yesterday's local files persisted.
- Baseline: python -m unittest discover -s tests -p 'test_fundamental*.py' -v — 12 passed.
- Final same command — 22 passed: 12 existing fundamental/queue/publication tests plus 10 new provider-preservation/date/denominator/identity/CLI regression cases.
- Compiled all three changed/new Python sources; checked trailing whitespace.
- Mocked ingestion main wrote both current and dated snapshots and an honest partial status without network requests. Benchmark CLI read gzip issuer fixtures and wrote separate reports.
- Synthetic regression evidence: 2026-11-13-proxy-benchmark-fixture.json. One revenue filing dated November 11 is excluded by SPTM's November 10 cutoff but included at 20% IWV coverage at its November 12 cutoff. This fixture is NOT production data.
- Exact captured output: 2026-11-13-proxy-benchmark-tests.txt.
- Full repository tests, live provider ingestion, cloud execution/deployment and production benchmark recalculation of this patch are not claimed.

## Next task and exact blockers
Review this isolated PR alongside PR #7. Merge and verify a real existing serialized ingestion publishes proxy_snapshots; then run the new diagnostic CLI on those caches and integrate its output into the intelligence-owned publication path. The existing publisher retains ingestion inputs, not generated analytics; no workflow/publication ownership change is included here. Until that happens legacy universe files must report blocked_missing_separate_provider_snapshots.

Remaining blockers: pending PR #7 and existing missing-CUSIP consumers; two SEC Companyfacts 404s; unresolved identifier/eligibility rows; dated historical membership/weights; verified US listing and point-in-time share-class prices/capitalization/actions; sector and TTM/growth normalization and the two-dimension style coverage gates. No outside-proxy large/mega-cap issuers were added without that evidence. No paid services, spending, third-party contact, runtime counter edits, duplicate refresh or GitHub access failure occurred.
