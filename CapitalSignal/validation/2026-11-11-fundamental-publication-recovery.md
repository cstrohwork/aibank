# Fundamental publication recovery

The initial full ingestion run 43150270157 downloaded 1,498 of 1,500 mapped issuers. Its download step exited successfully at 2026-11-12 04:07:44 UTC. SEC Companyfacts returned 404 for Preferred Bank (PFBC, CIK 0001492165) and Bank OZK (OZK, CIK 0001569650). Those records remain missing; no zero-filled substitutes are accepted.

The run later failed at publication when rebasing its generated benchmark_status.json and portfolio_diagnostics.json over an intelligence worker's changes. The original source caches were preserved in the sp1500-ingestion-evidence artifact, ID 13915605319, approximately 31 MB, on the failed run. The website's six-issuer count was the prior published smoke checkpoint, not the live download count.

Repair:

- Recover the preserved artifact with the authenticated GitHub Actions artifact download and validate every incoming issuer's identity and retrieval timestamp.
- Make the ingestion workflow publish only its owned universe, issuer cache, attempt and coverage files. The intelligence workflow owns all benchmark, portfolio, Model and intelligence products.
- Publish inputs against the latest branch head using a validated cache union; preserve newer remote issuer observations and unrelated worker files. No generated-report rebase occurs.
- Rebuild derived products after a successful recovery workflow.
- Cache issuer/date fundamental snapshots across portfolios to eliminate repeated scans. The failed run spent approximately eleven minutes on matching, above the newer pipeline's eight-minute per-stage limit.

Regression tests reproduce a stale checkout with a competing analytics commit, validate cache union/newer-observation preservation, reject invalid artifact records, and verify snapshot reuse remains separated by report date. Full suite passed 136 tests before publication. Workflow recovery success and current source coverage must be verified from the live run and status.json; this document does not itself certify completed publication or Model readiness.
