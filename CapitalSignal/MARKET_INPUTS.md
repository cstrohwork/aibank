# Market inputs, ownership denominators, corporate actions, and liquidity

Run the actual-data readiness audit:

```sh
python scripts/market_inputs.py
```

This creates `CapitalSignal/data/intelligence/market_readiness.json`. Its `results` array covers each CUSIP in the current SPTM holdings proxy. The proxy has 1,506 securities as of November 10, 2026; it is not an official constituent history. The initial repository audit has **zero verified price, class market capitalization, float, or liquidity observations**. Six cached issuers have dated share facts, which are not automatically assigned to a share class. These are explicit blockers, not completed datasets.

To run with verified market inputs:

```sh
python scripts/market_inputs.py --input /absolute/path/verified-market-inputs.json --as-of 2026-11-10 --window 20
```

Without `--input`, the script reads `CapitalSignal/data/intelligence/market_inputs.json` when present, otherwise it audits an empty bundle. Explicit missing input paths fail. Inputs are JSON arrays under `prices`, `denominators`, `actions`, and `action_coverage`.

## Input contract

All observations require `security_id` (currently `cusip:<nine-character CUSIP>`), ISO `date`, ISO `available_at`, and `source_url`. `available_at` is when the observation could actually be known. For downloaded records without archived availability evidence, use the retrieval timestamp, not the historical price date. The cutoff is end of the specified UTC date. A historical record downloaded today is not evidence it was available to this system in a prior backtest.

| Array | Additional fields | Accepted basis |
|---|---|---|
| `prices` | `close`, `volume`, `currency`, `price_basis`, `volume_basis` | Positive finite close, nonnegative volume, `USD`, `unadjusted_close`, `unadjusted_shares` |
| `denominators` | `kind`, `scope`, `unit`, `value` | `outstanding` or `float`; `share_class`; `shares`; positive finite count |
| `actions` | `type`, `new_shares`, `old_shares` | `split` with explicit positive ratio; other actions block affected calculations |
| `action_coverage` | `start`, `complete` | `date` is coverage end; `complete: true` attests that the source completely covers the interval |

Do not mark action coverage complete because a source returned no events. The provider must establish complete event coverage. Keep prices, share counts, and actions on the same security-class identifier; historical ticker-to-CUSIP correspondence requires external evidence. A current ticker mapping must not be used as a historical listing map.

The unattended acquisition command is:

```sh
python scripts/market_inputs.py --acquire --limit 25
```

It attempts a bounded set of current ETF ticker candidates, checkpoints each attempt to `CapitalSignal/data/intelligence/market_provider_cache.json`, skips identifiers attempted within 24 hours, stops the batch on an HTML challenge or HTTP 403/429 with a source-wide 24-hour cooldown, and resumes with remaining identifiers on subsequent runs. It inspects the actual SPTM workbook headers and records URL, HTTP status, response hash, retrieval timestamp, and bounded error/challenge evidence. Provider observations are quarantined rather than promoted into verified inputs. This command can run from the scheduled cloud workflow without credentials. Keep the provider cache among committed checkpoint files.

The first live attempt retrieved the SPTM workbook successfully: headers contain Name, Ticker, Identifier, SEDOL, Weight, Sector, Shares Held, Local Currency, and empty columns. It contains no issuer market value, raw price, trading volume, or shares-outstanding denominator. Stooq requests for AAPL and NVDA returned HTTP 200 with an HTML browser-verification challenge rather than CSV. The response hashes and excerpts are retained in the cache. This is a source-access blocker; HTTP success alone does not establish data success.

The supplied `fetch_stooq(symbol, security_id, currency, mapping_source_url)` function retrieves optional public daily CSV data without credentials. It requires a separately verified USD listing map. Its output is deliberately quarantined with `provider_unspecified` adjustment basis because the CSV transport does not establish raw price/volume treatment. It is **not** accepted automatically by the calculation pipeline. No network request runs in the default audit.

## Calculation API

`calculate_security(security_id, bundle, as_of, position_shares=None, participation=.1, window=20)` returns dated class market cap, ownership percentages, liquidity diagnostics, source URLs, and blockers. Optional position shares must already be in the latest price date's share units. `split_factor` can convert an earlier position count when complete corporate action evidence exists.

- Class market cap equals unadjusted close × class shares outstanding, after supported splits. It is not whole-issuer market cap for a multi-class company.
- Ownership percentages use separately evidenced outstanding or float counts; issuer-level XBRL share counts are rejected. Counts older than 45 calendar days relative to the price are rejected. Different-date counts require complete corporate action coverage.
- Prices more than seven calendar days old relative to cutoff are flagged stale and not used for valuation/liquidity.
- Liquidity uses the latest `window` valid daily observations, adjusts historical volumes into latest share units, and computes average close × volume in USD. These are observation-based estimates: upstream adapters must provide complete trading-session histories before these are interpreted as a consecutive-session ADV. The routine does not infer exchange holidays or delisting history.
- Estimated trading days equal position shares ÷ (average observed daily volume × participation). This excludes intraday liquidity, market impact, spreads, trading halts, and execution constraints. No execution capacity is guaranteed.
- A merger, spinoff, conversion, unknown event interval, conflicting same-date price/share count, future availability, unsupported currency, or nonfinite number cannot silently pass.

## Remaining acquisition work

A verified source for raw dated prices/volumes, corporate-action completeness, share-class counts, free float, listing history, and currencies is still needed. An issuer-wide capitalization layer additionally needs all share classes and conversion relationships. Spreads need bid/ask observations; daily OHLCV cannot supply them. Neither SEC portfolio value/share ratios nor ETF basket shares substitute for a market-price feed or issuer float.

Tests: `python -m unittest discover -s tests -p test_market_inputs.py -v`.
