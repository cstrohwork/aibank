# Intelligence health and source-event monitoring

Run `python scripts/intelligence_health.py` after committed data refresh and the model builder. This offline command writes `CapitalSignal/data/intelligence/health.json` and `events.json` atomically. Use `--data-root PATH`, `--as-of 2026-11-12T04:00:00+00:00` for reproducibility, `--stale-hours 36` to change freshness, and `--strict` to return exit code 1 while intelligence readiness is blocked. The default exits successfully after generating a report even if coverage is incomplete; report generation success is deliberately distinct from data readiness.

## Health contract

`schema_version: 1`; `status` is `blocked` or `ready`; `blocking_reasons` describes coverage and source failures. `sources` reports fundamentals/history timestamp ages, with `fresh`, `stale`, `unknown`, and `future_timestamp` states. Record ingestion freshness does not imply that a financial observation's reporting period is recent.

`fundamentals` independently reads every issuer cache expected by the current universe, checks identity and fact structure, recomputes eligible annual and instant field coverage, identifies missing/corrupt caches and unmapped securities, and compares actual cache counts with the ingestion status file. Issuer coverage percentages use unique mapped CIKs as denominator. The current universe is an ETF holdings proxy, not a certification of official index membership.

`ownership` compares each 13F/fund index with files actually present, counts missing snapshots, preserves source errors, and exposes the latest reporting date. A market-wide expected manager/fund/report-date manifest is absent, so `expected_snapshots` is null and all-market completeness remains explicitly unknown/incomplete. Never substitute the number of indexed snapshots for all institutions expected to file.

`history` exposes catalogued versus archived filing coverage, pending/deferred filings, source download/normalization failures, storage blocks, and independently counted archive-state statuses. `pipeline` observes the integration pipeline manifest if present; a failed previous pipeline blocks readiness, while a current running pipeline is informational to avoid a circular dependency. This tool does not query GitHub workflow APIs or claim live workflow success.

`readiness.fundamentals_ingestion_complete` requires actual valid caches for every mapped issuer and no unmapped securities. `readiness.model_ready` exclusively observes **`fundamentals/model_status.json` → `activation.ready`**; the model builder owns that gate. Missing model status keeps readiness false. Per-field coverage and freshness remain separate diagnostics. This avoids contradictory model activation rules.

`production_style_ready` remains blocked when historical benchmark or style inputs are unavailable, when historical archive is incomplete, or when measured data/source controls fail. This health result does not substitute for portfolio-specific classification coverage controls. It does not establish market-wide ownership completeness.

## Event contract

The event catalogue scans existing compressed filing catalogues, deduplicates accessions, and counts four filing streams: beneficial ownership Schedule 13D, Schedule 13G, insider Forms 3/4/5, and N-PX voting reports. It retains the latest **500 filings per stream**, with complete local catalogue counts under `streams`. Future-dated/missing filing dates are excluded from event results and counted. Source catalogues are not assumed to cover all public filings.

Each retained event includes accession, filer CIK/name, form, filing date, SEC source URL, archive availability, and any existing normalized-file paths. Metadata events have `evidence_level: filing_metadata_only`, `interpretation_status: requires_document_parsing_and_entity_linkage`, and null activist intent, transaction direction, and vote direction. A 13D filing is not automatically an activism campaign; an insider form is not automatically a purchase or sale; an N-PX filing is not a vote direction.

When available, health separately observes `intelligence/parsed_events.json`, produced by the dedicated document parser. Metadata stream counts remain separate from document-derived signals. Missing source streams and absent normalized signals are explicit, rather than silently rendered as zero activity.

## Verification

`python -m unittest discover -s tests -p test_intelligence_health.py -v` covers false completion claims, absent field coverage, stale/future timestamps, canonical model gate behavior, event deduplication and retention, future event exclusion, path traversal, missing indexed files, and pipeline cycle avoidance.
