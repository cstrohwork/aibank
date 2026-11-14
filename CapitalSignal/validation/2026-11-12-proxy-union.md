# Proxy-union calculation safeguards — November 12, 2026

## Scope and verified production evidence
Pinned source: 2d24ffb1b56cb013941d26af3fb89b79bdc2f851. Root, CapitalSignal, scripts, tests and validation directories inspected; no applicable AGENTS.md found. No open PRs returned. Active history run https://github.com/cstrohwork/aibank/actions/runs/43226635910 was left undisturbed; no SEC ingestion or refresh launched.

Reviewed scripts/ingest_sp1500_fundamentals.py, its dedicated workflow and status.json. The union is already implemented, so it was not reimplemented. Dedicated ingestion https://github.com/cstrohwork/aibank/actions/runs/43204893830 completed successfully at 11:00 UTC (06:00 Eastern), including tests, ingestion and checkpoint publication. Saved status at 11:00:23 UTC is partial: 2,591 securities, 2,578 mapped securities (99.50%), 2,560 distinct CIKs, 2,558 valid/fresh issuer caches (99.92% of mapped issuers), 13 unmapped securities, two missing issuer caches. SEC Companyfacts returned 404 for CIKs 0001492165 and 0001569650. No retry timing is recorded for these Companyfacts failures; future runs will attempt missing caches first. No mapping or successful ingestion is invented.

Both provider snapshots are dated November 10, 2026:
- SPTM: https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-sptm.xlsx ; SHA-256 3cd765db9af541cac36f547230812b12253cea87681d4bbfdff64bc419febb9b
- IWV: https://www.ishares.com/us/products/239714/ishares-russell-3000-etf/latest-holdings.csv ; SHA-256 5e1620a6091f63a632ac6da1bca6f41ad1c7593cbe5cf6b725944378e1588135

These are current ETF holdings proxies, not official S&P/Russell membership. Cache coverage is not evidence of complete financial fields or historical constituents. Saved field issuer coverage: revenue 2,299; net income 2,484; equity 2,516; assets 2,516; liabilities 2,175; operating cash flow 2,473; capex 2,021; diluted EPS 2,427; shares 2,390; dividends/share 1,402; operating income 2,043. Annual-duration USD facts are not TTM; filing and period end must precede the cutoff. No separate verified large/mega-cap additions outside the proxies exist.

Existing portfolio diagnostics are dated 10:33 UTC, predate the successful union publication, contain 4,564 profiles and zero calculated styles. Do not present those outputs as a completed union rebuild. Latest intelligence run https://github.com/cstrohwork/aibank/actions/runs/43224612264 failed at market_inputs.py line 291: TypeError: can only concatenate str (not "NoneType") to str. Job 131204486150 logs were inspected. Existing cloud tests passed before this runtime failure; this does not establish production success.

## One bounded implementation: union-compatible calculation inputs
- Missing provider CUSIPs stay explicit blockers in market audit, retain all securities and null market/ownership/liquidity results, and are skipped by optional transport.
- Missing CUSIPs cannot match each other in portfolio joins; contradictory CUSIP/CIK mappings fail closed. Nonfinite/bool position values are excluded.
- Union benchmark reports the union and preserves both dated provider sources. Its mixed first-provider weights are explicitly unusable as a common benchmark: weighted coverage is null with a blocker. Distinct-issuer field counts remain available; share classes cannot inflate issuer counts. Single-proxy weighted diagnostics remain supported.
- No historical membership, market caps, classification, source mappings or runtime counters fabricated. Existing style/publication gates remain closed.

## Validation actually executed
- Fresh source from GitHub, not reused prior checkout.
- Baseline: python -m unittest discover -s tests -p 'test_fundamental*.py' -v : 12 passed.
- Patched relevant suite: python -m unittest discover -s tests -v : 33 passed (12 existing fundamental/publication/queue + 13 market + eight new union tests). This isolated directory contains those relevant tests only; this is not the full repository's 149-test suite.
- Ran patched python scripts/market_inputs.py without acquisition against the actual pinned universe. Completed successfully with all 2,591 rows, 1,085 explicit missing-CUSIP blockers, zero verified market caps/prices/float/liquidity. This local smoke intentionally supplied no market inputs or issuer caches; zero values describe that smoke, not a fresh measurement of production market coverage.
- Asserted row preservation, missing-ID count equality to universe and null market caps. Full unittest output: 2026-11-12-proxy-union-tests.txt.
- No live SEC requests, full cloud pipeline, deployment or browser test performed for this patch.

## Next task and exact blockers
Review this isolated PR, run full regression tests/cloud intelligence rebuild on the merged code, and inspect the saved outputs rather than infer success. Then retain separate per-provider weights/dates in universe ingestion and compute separate SPTM/IWV benchmark coverage; never construct a blended benchmark from current union weights. Obtain sourced security identifiers for the 1,085 IWV-only rows before historical portfolio matching. Audit downstream CUSIP-only consumers for the same union assumption.
Other blockers: two SEC Companyfacts 404s; 13 unmapped securities (including retained CVR/escrow/rights rows that need an explicit eligibility review); dated historical constituents/weights; verified unadjusted prices, US exchange listing, share-class caps and corporate actions; sector and TTM/growth normalization; documented two-dimension 70% style gates and adviser denominators. Nasdaq parser presence is not evidence of verified listing/date/capitalization outside the proxies.
