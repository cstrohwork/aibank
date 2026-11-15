# Verified current large/mega-cap supplemental ingestion — November 15, 2026

## Scope and source rules

This bounded change activates the public Nasdaq stock-screener adapter as a separate supplemental Companyfacts ingestion universe. It fetches Nasdaq, NYSE and NYSE American separately so each exchange-filtered response is listing evidence. It does not change either benchmark proxy and does not call current membership historical.

An outside-proxy security is retained only when one current screener observation supplies all of the following:

- market capitalization of at least $10 billion, finite and positive;
- an explicit Nasdaq, NYSE, NYSE American or AMEX listing;
- a ticker with exactly one current SEC ticker-to-CIK match;
- a timezone-aware retrieval observation, public source URL and SHA-256 of the source response; and
- absence from the deduplicated current SPTM/IWV ETF holdings proxy union.

Conflicting duplicate screener rows fail the source snapshot. Unsupported exchanges, ambiguous SEC mappings, missing/nonfinite capitalization and below-threshold securities remain excluded with explicit reasons. The retained screen states that it is current observed evidence only—not an index, official membership or evidence before its retrieval time.

## Publication and calculation isolation

- Supplemental issuers are queued for SEC Companyfacts acquisition but are not inserted into `universe.json`, either provider-weight denominator, portfolio matching, or historical benchmark calculations.
- Proxy security/issuer/field counts remain separately reported under their existing keys. New fundamental-ingestion totals and a separate `supplemental_large_megacap` block report the broader queue without making the proxy benchmark look more complete.
- The concurrent-safe checkpoint publisher now validates, merges and republishes `large_megacap_outside_proxies.json`, unions its CIKs only for Companyfacts publication, and recomputes proxy and supplemental coverage at their own dated cutoffs.
- If the optional screener cannot be validated, no new supplemental issuer is admitted. A prior checksum-labelled snapshot may be retained with the runtime source failure disclosed; the ETF proxy ingestion remains available.
- Point-in-time prices, share-class shares outstanding, float and liquidity remain separate blockers. A screener market-cap observation is not reused as a portfolio valuation factor.

## Validation actually executed

- `python -m unittest tests.test_fundamental_publication tests.test_fundamental_proxy_benchmarks -v`: 19 passed.
- `python -m unittest discover -s tests -p 'test_fundamental*.py' -v`: 37 passed after the exchange-fetch regression was added.
- `python -m unittest discover -s tests -v`: 215 passed.
- `python -m py_compile scripts/ingest_sp1500_fundamentals.py scripts/publish_fundamental_checkpoint.py`: passed.
- `git diff --check`: passed.

Regressions cover dated source evidence, three separate exchange queries, explicit U.S. exchanges, unique SEC identity, exclusion from the ETF proxy union, nonfinite market caps, conflicting source rows, separate Companyfacts queue counts, and survival through the latest-main checkpoint merge.

The first direct source probe exposed the old combined-exchange URL as invalid for the current Nasdaq response shape: it returned HTTP 200 with zero records. The implementation was corrected to fetch and validate each exchange independently and to read `data.table.rows`. The corrected public-source probe succeeded: market-cap date November 12, 2026; retrieval `2026-11-15T17:05:18.452008+00:00`; 4,233 Nasdaq, 2,717 NYSE and 301 NYSE American source rows with separate SHA-256 hashes; 966 securities at or above $10 billion; 965 with a supported exchange and unique SEC ticker-to-CIK match; and 242 securities / 218 issuers outside the current SPTM/IWV proxy union. These are observed candidates for the next ingestion run, not published production coverage.

## Production timeout and paged-source correction

Post-merge fundamentals run [43740054223](https://github.com/cstrohwork/aibank/actions/runs/43740054223) completed its workflow and published commit `3d9569f06030326b80a8b6e368c528b60bcf5fe2`, but the committed status explicitly records `TimeoutError: The read operation timed out` for the supplemental Nasdaq source. It published zero supplemental securities and no supplemental snapshot. Workflow success therefore established execution and safe proxy publication only; it did not establish supplemental ingestion.

The source transport now uses independently validated 1,000-row pages. Every page retains its exchange, offset, provider total, source URL, dated observation and raw SHA-256. Totals must remain identical across an exchange's pages, no page may be empty before the provider total is reached, overflow is rejected, all page dates must agree, and the accumulated count must exactly equal the provider total. This reduces response size without weakening completeness or provenance checks.

The corrected live paged probe completed at `2026-11-15T18:03:05.508101+00:00`: five Nasdaq pages totaling 4,233 rows, three NYSE pages totaling 2,717 rows, and one NYSE American page totaling 301 rows. All nine pages reported the November 12, 2026 market date. The parsed result remained 966 $10-billion candidates, 965 supported-exchange/unique-CIK mappings, and 242 securities / 218 issuers outside the ETF-proxy union. These remain verified source candidates until a later completed workflow publishes their snapshot and actual Companyfacts coverage.

Validation for the paged correction actually executed: 19 focused tests passed; all 215 repository tests passed; the ingestion module compiled; `git diff --check` passed; and the nine-page public-source probe passed. The focused regression uses two pages per exchange and verifies offsets, stable totals, row counts, raw page hashes and the single dated observation.

The first production run after pagination, [43745215335](https://github.com/cstrohwork/aibank/actions/runs/43745215335), completed all steps but its committed `2026-11-15T18:17:51Z` status again disclosed a Nasdaq read timeout and zero supplemental securities. Pagination alone did not fix the Azure-hosted runner path. A second bounded transport correction adds Nasdaq's provider-side `mega|large` screen to each exchange request before paging; numeric capitalization of at least $10 billion is still independently required for admission, so the category is a transport prefilter rather than capitalization evidence.

The filtered public-source probe returned in approximately six seconds per exchange: 315 Nasdaq rows / 63,264 bytes, 648 NYSE rows / 126,413 bytes, and three NYSE American rows / 907 bytes, all dated November 12, 2026. The 966-row total exactly matches the candidate count from the prior unfiltered 7,251-row probe. The parser still excludes any row below the numeric $10-billion floor and still requires explicit exchange evidence and a unique SEC mapping. This filtered response is locally verified; production publication remains unproven until a later workflow commits the snapshot.

Post-merge run [43767472322](https://github.com/cstrohwork/aibank/actions/runs/43767472322) also completed its workflow but the committed `2026-11-15T22:16:11Z` status again disclosed the same Azure-runner read timeout and zero supplemental issuers. This confirms an environment-specific source-access failure rather than an oversized-response failure. The completed workflow is not counted as successful supplemental ingestion.

The existing failover path retains a prior validated snapshot when a live refresh fails, but no prior snapshot had yet been published. A current public-source snapshot was therefore generated through the same parser at `2026-11-15T22:17:55.000208Z` and saved for review: 242 outside-proxy securities / 218 SEC issuers, 71 Nasdaq, 168 NYSE and three NYSE American; minimum retained market cap $10,371,010,823; maximum $2,103,905,714,308; source market date November 12, 2026; aggregate envelope SHA-256 `428308e062fe540580efcb44b8ce98a62787f0d312f5113a49a71ce3824bc070`.

Independent snapshot validation found zero issues across security/issuer count reconciliation, unique tickers, ten-digit CIKs, numeric $10-billion floor, supported exchanges, exact dated observations, page URLs, per-row source hashes and explicit outside-proxy membership labels. This snapshot is current observed evidence only. If merged, a later workflow may retain it while disclosing the live source timeout and may use its issuer list for Companyfacts acquisition; no Companyfacts completion is claimed from the snapshot itself.

The workflow push filter originally ignored data-only updates to the fallback snapshot, so merging the verified checkpoint did not schedule its Companyfacts queue. The dedicated workflow now includes the exact supplemental snapshot path. This does not launch duplicate work: the workflow's existing `sp1500-fundamentals` concurrency group remains serialized with `cancel-in-progress: false`. Workflow YAML parsing and a structural assertion for the new path and retained concurrency guard were executed locally before review.

## Runtime state and next task

At implementation time the existing scheduled fundamentals run [43716501224](https://github.com/cstrohwork/aibank/actions/runs/43716501224) was already active and was not duplicated. The last committed proxy status remained 2,592 current SPTM/IWV ETF-proxy securities, 2,561 mapped issuers and 2,559 successful Companyfacts caches, with two SEC 404s. Those are current ETF holdings proxies, not official S&P Composite 1500 or Russell 3000 membership.

This checkpoint precedes cloud execution and publication of the new screen. The direct source probe verifies the current candidate set, but no supplemental Companyfacts coverage is claimed until a completed fundamentals run publishes and the committed snapshot is read back. Next: pass cloud review, merge against the latest post-ingestion main SHA, then verify the published outside-proxy count, SEC CIK queue, Companyfacts successes/failures and dated field coverage. Exact remaining blockers are point-in-time portfolio price/share-class/float inputs, historical benchmark constituents/weights, two existing Companyfacts 404s, and incomplete September/December/March SEC history.
