# Portfolio diagnostics publication health — November 15, 2026

## Production evidence inspected

- The portfolio gate implementation merged in PR #25, but the committed `portfolio_diagnostics.json` still had the older `initial_identifier_matching_and_fundamental_ratio_diagnostics_only` schema at `2026-11-15T08:58:34Z`.
- The committed artifact contained 9,233 profiles but no aggregate `summary`, per-profile diagnostic coverage gate, point-in-time gate, or production-classification gate.
- The most recent completed intelligence run was [43695814381](https://github.com/cstrohwork/aibank/actions/runs/43695814381), created before the gate implementation. No completed post-merge intelligence run was found.
- Root cause: `scripts/match_fundamental_portfolios.py` was absent from the intelligence workflow's push path filters. A successful merge therefore did not schedule regeneration. The old artifact is not treated as proof that gate publication completed.

## Bounded implementation

- Added the matcher script to the intelligence workflow trigger paths.
- Added health validation for the generated diagnostics status, summary/profile count, finite coverage threshold, six reconciled aggregate gate counts, three required per-profile gate objects, report-date/fact-cutoff consistency, and prevention of a style label escaping a blocked production gate.
- Invalid or stale structure adds `portfolio_diagnostics_missing_or_invalid_gate_structure` to health blockers. Validation details are bounded to 100 published examples with a full issue count to prevent an old large artifact from bloating health output.
- Corrected the health limitation label to the deduplicated current SPTM/IWV ETF holdings proxy union. This remains explicitly not official S&P Composite 1500 or Russell 3000 membership.
- This check validates publication structure only. It does not certify complete holdings, historical membership, benchmark weights, market factors, or a production classification.

## Validation actually executed

- `python -m unittest tests.test_intelligence_health -v`: 13 passed.
- `python -m unittest discover -s tests -v`: 210 passed after materializing the repository's tracked Model assets in the isolated sparse checkout. The first full-suite attempt exposed only the sparse-checkout omission of those tracked assets; after adding them, the suite passed unchanged.
- `python -m py_compile scripts/intelligence_health.py scripts/match_fundamental_portfolios.py`: passed.
- `git diff --check`: passed.
- Applying the validator to the committed old artifact returned `structure_valid=false`, 9,233 observed profiles, and the expected stale-status/missing-summary/missing-gate evidence.

## Remaining gates and next task

- A merged workflow run must actually regenerate and commit the aggregate and per-profile gates before publication is complete.
- Historical official constituents/weights, verified point-in-time prices, share-class market capitalizations, float denominators, and market factors remain unavailable. Production styles stay unknown/null while those gates are blocked.
- Fundamentals remain the dated current SPTM/IWV ETF holdings proxy union. No outside-proxy large/mega issuer is admitted without verified point-in-time market capitalization and U.S.-exchange listing evidence.
- After cloud review and merge, inspect the completed intelligence run and committed `portfolio_diagnostics.json`; reconcile its gate counts independently and record the exact run/commit. Do not infer success merely because the run started.
