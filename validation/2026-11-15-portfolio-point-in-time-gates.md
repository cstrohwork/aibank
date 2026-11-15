# Portfolio point-in-time coverage gates

Validated 2026-11-15 at 11:03 UTC (06:03 EST).

## Production state inspected before implementation

- The current fundamentals universe contains 2,592 securities from the
  deduplicated union of the dated SPTM and IWV ETF holdings files. These are
  current ETF holdings proxies, not official S&P Composite 1500 or Russell
  3000 membership.
- 2,579 securities map to 2,561 unique SEC issuers. Companyfacts ingestion
  succeeded for 2,559 issuers; two SEC CIK endpoints remain 404 responses.
- The latest completed portfolio matching calculation reported 9,233 cached
  portfolios and zero unavailable cached portfolio files. That prior run is
  evidence of input availability only; this change has not yet regenerated
  the production diagnostic file.
- Historical official benchmark constituents and weights are unavailable.
  Current provider weights cannot be combined into a union benchmark.
  Verified point-in-time prices, share-class market capitalizations and float
  denominators are also unavailable, so production benchmark comparisons and
  calculated styles remain blocked.
- The SEC history checkpoint at 2026-11-15T10:43:09Z contained 92,382 archived
  filings and 918,932 pending filings. Current/recent and June 2026 intake were
  complete; September 2025 had 12,355 outstanding. One SEC HTTP 503 download
  failure was retained, normalization failures were zero, and
  `storage_blocked=false`. The existing serialized backfill worker was left
  running; no duplicate ingestion was launched.

## Bounded implementation

`scripts/match_fundamental_portfolios.py` now emits three explicit gates for
every portfolio diagnostic:

1. A 70% reported-value diagnostic coverage gate for identifier matching and
   available fundamentals, plus per-ratio coverage results. Passing this gate
   authorizes diagnostics only.
2. A point-in-time gate that records the portfolio report date, fundamental
   fact availability cutoff and current proxy snapshot date. A current proxy
   is never treated as historical membership. Even an exact-date proxy match
   remains diagnostic-only because official historical benchmark membership
   and weights are unavailable.
3. A production classification gate that remains false with
   `calculated_style=null` until coverage, point-in-time benchmark and market
   factor requirements all pass.

The output also includes aggregate pass counts so publication and health
checks can distinguish diagnostic coverage from production eligibility.
Unknown classifications remain unknown.

## Validation actually executed

- `python -m unittest tests.test_fundamentals -v`: 8 tests passed.
- `python -m unittest discover -s tests -v`: 206 tests passed.
- `python -m py_compile scripts/match_fundamental_portfolios.py`: passed.
- `git diff --check`: passed.

New regressions prove that high current-proxy coverage does not establish a
historical benchmark and that sub-70% reported-value coverage blocks the
diagnostic gate. They also prove that an exact proxy/report date does not
authorize a production style.

## Next task and exact blockers

After cloud review and merge, run the existing intelligence workflow and
inspect its committed `portfolio_diagnostics.json` before claiming the gates
were published. Next, add health assertions for the generated aggregate and
per-portfolio gates, then source point-in-time price/share-class market-cap
inputs from a dated public source if one can be verified.

Blockers are historical official benchmark membership and weights, verified
point-in-time prices, share-class market capitalization, float denominators,
two SEC Companyfacts 404s, incomplete September/December/March filing history,
and the retained SEC 503 retry. No outside-proxy issuer is eligible merely
from ticker, issuer size or an undated market-cap claim.
