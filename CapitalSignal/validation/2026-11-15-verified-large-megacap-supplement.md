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

## Runtime state and next task

At implementation time the existing scheduled fundamentals run [43716501224](https://github.com/cstrohwork/aibank/actions/runs/43716501224) was already active and was not duplicated. The last committed proxy status remained 2,592 current SPTM/IWV ETF-proxy securities, 2,561 mapped issuers and 2,559 successful Companyfacts caches, with two SEC 404s. Those are current ETF holdings proxies, not official S&P Composite 1500 or Russell 3000 membership.

This checkpoint precedes cloud execution and publication of the new screen. The direct source probe verifies the current candidate set, but no supplemental Companyfacts coverage is claimed until a completed fundamentals run publishes and the committed snapshot is read back. Next: pass cloud review, merge against the latest post-ingestion main SHA, then verify the published outside-proxy count, SEC CIK queue, Companyfacts successes/failures and dated field coverage. Exact remaining blockers are point-in-time portfolio price/share-class/float inputs, historical benchmark constituents/weights, two existing Companyfacts 404s, and incomplete September/December/March SEC history.
