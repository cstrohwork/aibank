# Capital Signal intelligence foundations

## Execution

`python scripts/run_intelligence_pipeline.py` builds the security/entity master, separate ownership views and amendment chronology, market-input coverage/liquidity diagnostics, evidence-based mandates/classification/targeting, benchmark diagnostics, conditional company Model data, parsed filing signals, and coverage/event monitoring. Each stage checkpoints its execution status; failure does not suppress subsequent diagnostics. A successful run means the calculations executed, not that the source universe or all analytical inputs are complete.

`.github/workflows/intelligence-pipeline.yml` runs after SEC ownership/history and fundamentals workflows, on implementation changes, and daily at 11:23 UTC. It acquires a bounded public-market evidence batch before calculations, observes provider challenge cooldowns, tests all regressions, uploads evidence, and commits derived outputs for GitHub Pages. When upstream data changes before publication, it rebuilds from the latest caches instead of publishing stale generated files. No additional ChatGPT scheduled-task slot is required.

The fundamentals worker prioritizes missing/corrupt issuer caches before refreshing existing issuers and checkpoints bounded runs. This prevents a daily partial refresh from repeatedly processing the beginning of the universe and starving pending issuers.

## Outputs and gates

| Component | Output | Meaning |
| --- | --- | --- |
| Identity | `data/intelligence/identity_master.json`, `identity_status.json` | Validated CUSIPs, legal entities, current-map evidence, explicit unresolved identifiers |
| Ownership and history | `data/intelligence/reconciliation.json` | Separate manager/fund periods; amendment selection; combined totals withheld without proven scope |
| Market and liquidity | `data/intelligence/market_readiness.json`, `market_provider_cache.json` | Verified dated inputs, calculations where available, provider attempts and actual blockers |
| Mandates/targeting | `data/intelligence/investor_readiness.json` | Evidence/coverage-gated classifications and explainable target readiness |
| Filing signals | `data/intelligence/parsed_events.json` | Parsed, attributable observations; absence of usable body is not a zero holding or vote |
| Monitoring | `data/intelligence/health.json`, `events.json`, `pipeline_status.json` | Independent cache coverage, errors, freshness, catalogue event streams and execution evidence |
| Model | `data/fundamentals/model_status.json`, `model_data.json` | Canonical `activation.ready` gate and sourced annual company inputs |

The separate Model page is `/CapitalSignal/model/`. It enables company scenarios only after every security in the current SPTM proxy universe is mapped, every issuer cache is valid/current, and every issuer has compatible required annual model inputs. Expired manifests fail closed in the browser. It is not linked from the publications while readiness is blocked. Optional EPS/FCF data remain explicitly unavailable where absent; scenarios use separately disclosed user assumptions.

## Open data dependencies

The universe is an SPTM fund-holdings proxy, not licensed official/historical S&P index membership. Historical prices, share-class denominators, free float, corporate-action completeness, dated sector classifications, fund/adviser attribution, documented mandates, and genuine forward consensus are separate dependencies. Missing items suppress their dependent metrics; ingestion of all Companyfacts files alone does not certify full investment-style or targeting readiness. Prospectus evidence acquisition and source-review queues are separate from verified fund attribution. Parsed disclosure observations require source review before any activist-intent interpretation.

See the component methodology documents and machine-readable reports for current counts and blockers. Counts in those reports are authoritative over this document.
