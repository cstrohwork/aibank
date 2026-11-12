# Capital Signal — Holdings-based investment style methodology (v0.2)

## Required inputs
For each manager and reporting period: SEC CIK, accession, filing and report dates, security CUSIP, issuer, position market value, shares and instrument type. Use amended filings as the effective version, preserving superseded versions. Resolve securities to permanent issuer IDs, ticker history and issuer fundamentals *as of the portfolio measurement date*.

For each issuer obtain price, shares outstanding, market cap, book equity, trailing earnings (with negative earnings flagged), trailing revenue, EBITDA/enterprise value where available, forward earnings estimates where licensed, revenue growth (3y), EPS growth (3y), analyst forward growth where licensed, ROE/ROIC, operating margins, leverage, sector/industry and fiscal reporting dates. SEC companyfacts/XBRL and SEC submissions are free primary sources for many backward-looking fundamentals; prices, sector mappings and analyst forecasts need separately documented, lawful sources. Do not fill missing forward estimates with fabricated values.

## Scoring
1. Restrict to ordinary listed equity; separately report ADRs, ETFs, options, preferred and unclassified securities. Do not confuse the manager's 13F value with firm-wide equity AUM.
2. Join positions to issuer fundamentals using point-in-time effective dates and filing availability dates to avoid look-ahead bias. Capture raw fields, units, provenance and missingness.
3. Compute industry-relative percentile ranks for value: earnings yield (positive earnings only), book-to-price, EBITDA/EV (positive EBITDA and EV only), and free-cash-flow yield where reliably derived. Compute growth percentiles for historical sales CAGR, EPS growth (when meaningful), and available forward estimates. Do not treat negative or absent denominators as extreme value.
4. Each security's value and growth scores are the equally weighted mean of its **available valid** factor percentiles, with at least two valid factors per dimension for a full classification. Require at least 70% of eligible disclosed equity value to have both dimension scores; otherwise mark insufficient coverage and provide partial diagnostics.
5. Aggregate security scores by disclosed market-value weights, renormalized over classified eligible equities. Compare portfolio value/growth scores to a same-date, sector-matched reference universe to distinguish style from sector exposure. Store value/growth score, benchmark-relative difference, classified weight, missing weight, and factor contributions.
6. Base classification thresholds (initial, subject to calibration): Value if value-minus-growth percentile score >= 15 points; Growth if <= -15; Blend otherwise. Expose **style confidence** and underlying scores. A manager with materially different fund strategies should be assessed fund-by-fund and consolidated using verified fund equity AUM weights, not arbitrary fund counts.
7. Update whenever a new 13F amendment, N-PORT portfolio, or newly available point-in-time fundamentals changes a relevant input; retain historical snapshots and filing accession lineage. Recompute on a nightly fundamentals refresh as a fallback. Never overwrite user-directed editorial labels silently; keep them distinct from calculated style.


## Expanded investment style taxonomy (v0.2)

Use **one primary style** and optional descriptive flags (sector, yield, index exposure), so overlap does not hide important traits. Preserve fund strategy type separately from investment style and active/passive orientation. Use market-value-weighted *security-level* fundamentals; report coverage and comparator dates.

| Style | Quantitative or documented rule |
| --- | --- |
| Value | Base factor score value minus growth >= +15 points, subject to higher-priority styles |
| Growth | Base factor score growth minus value >= +15 points, subject to higher-priority styles |
| Blend | Neither base score exceeds the other by 15 points |
| Yield | Portfolio-weighted indicated forward dividend yield >= 1.5x the same-date broad-market benchmark yield **and** >= benchmark + 1.5 percentage points, with >= 70% eligible equity value having valid yield data. Cash distributions, specials and zero dividends handled explicitly; do not infer yield from 13F alone |
| Sector | A **single** GICS sector exceeds 75% of eligible equity portfolio market value (strictly >75%). Store sector name and share, e.g. Sector — Health Care; distinguish sector funds from accidental concentration |
| Index | Fund is legally/documentedly an index fund, or its documented mandate is primarily index-based, **or** >=75% of its eligible equity portfolio market value is in benchmark constituents **and** active-share/weight tracking evidence supports index alignment. Membership overlap alone does not establish index replication; if only membership overlap is known, flag 'index constituent overlap' rather than automatically classify Index. Use correct point-in-time benchmark membership |
| Alternative | Hedge fund or alternative strategy with no defensible Value/Growth/Blend/etc. dominant style, supported by mandate or registration; do not infer hedge-fund status from 13F alone |
| Private Equity | Verified private-equity investment strategy / vehicle based on regulatory disclosures, fund documents or manager materials; not inferred from public-equity 13F holdings |
| Venture Capital | Verified venture-capital investment strategy / vehicle based on regulatory disclosures, fund documents or manager materials; not inferred from public-equity 13F holdings |
| Deep Value | Portfolio valuation materially below same-date broad market: e.g. portfolio-weighted positive-E/P and FCF yield relative to benchmark >= 1.5x, with >=70% valuation coverage and industry-relative value score >=75th percentile. Check sector composition and outliers |
| Aggressive Growth | Portfolio historical and/or forward growth materially above same-date market: >=1.5x benchmark growth rate with >=70% growth coverage and growth score >=75th percentile; avoid ratios when market growth is zero/negative; use percentile-spread fallback |
| GARP | Portfolio weighted valuation below market, growth above market, **and portfolio aggregate forward PEG < 1** where estimates are available. PEG = positive forward P/E divided by positive expected annual EPS growth expressed as percentage points; require positive earnings, growth, >=70% eligible value covered and show methodology. Calculate portfolio PEG from portfolio aggregate P/E and growth, not the arithmetic average of individual PEGs; also disclose individual-position weighted PEG for diagnostic comparison |

**Provisional significance thresholds** (1.5x, 1.5 percentage points, 75th percentile) must be backtested against broad-market and sector-matched universes before production use. Deep Value requires both cheap absolute valuation and sector-relative cheapness. Growth comparisons must not divide by nonpositive benchmark growth. Use point-in-time benchmarks and publish the chosen benchmark and period.

### Primary style precedence and exceptions
1. At fund level, verified **Private Equity** or **Venture Capital** strategy takes priority over public-equity factor classifications. A mixed manager may have multiple fund styles; firm-wide style is weighted by *verified* equity AUM and marked mixed if no dominant style.
2. Verified **Index** strategy takes priority over factor classifications. For inferred Index, require index membership overlap >=75% plus a low active-share threshold (provisional <=30%) or demonstrated tracking; do not call concentrated active managers index investors solely because their holdings are index constituents.
3. **Sector** (>75% one sector) is the primary style for a public equity portfolio unless a verified index mandate takes priority; preserve the sector's factor style as a secondary flag.
4. **Yield**, **Deep Value**, **Aggressive Growth**, **GARP** are refinements of fundamental style. In overlapping cases: GARP if all its conditions hold; otherwise Deep Value or Aggressive Growth if their respective conditions hold; otherwise Yield if it qualifies. Always retain other qualifying flags, including Yield.
5. Then Value, Growth or Blend. **Alternative** is reserved for verified hedge-fund/alternative vehicles lacking a well-supported more specific style; otherwise use **Insufficient data**, not Alternative.
6. For firm-level classifications, never weight different funds equally without fund assets; use verified fund equity AUM weights, and show style distribution. An explicit editorial designation (e.g. Berkshire Value) is separate from computed style and is not overwritten automatically.

### Additional data and quality controls
- Dividend per share, ex-date, annualization method, regular versus special distributions, currency and security price; comparable market index dividend yield.
- Point-in-time GICS sector codes and classification changes; position value and eligible-equity denominator.
- Benchmark identifier, historical constituent identifiers, constituent weights, benchmark market value, active share and tracking-error observations if available; documented fund objective and replication methodology.
- Verified manager/vehicle type and mandates from Form ADV, fund prospectuses, N-PORT, annual reports and manager websites; mark private holdings coverage limits.
- Forward P/E, consensus EPS growth forecast horizon and timestamp for PEG; handle negative/zero EPS and growth as missing rather than valid PEG.
- Report style result, primary/secondary flags, exact metric values, benchmark, as-of date, data coverage, sources, classification version and confidence. Retain all source lineage.
- Regression tests: exact 75% is NOT Sector; >75% is; index membership alone is insufficient; special dividends excluded from regular yield; negative earnings and growth do not produce PEG; editorial labels remain intact.

## Implementation sequence
- Inventory 13F holdings and validate value units, CUSIP matching and reporting periods.
- Build issuer identifier map and SEC companyfacts ingestion with filing-availability dates.
- Add documented price/market-cap and sector sources; calculate point-in-time factors.
- Implement cross-sectional percentile benchmarks, coverage gates, manager rollups and regression tests.
- Publish measured score and coverage beside classification; never publish calculated style without evidence.

## Berkshire Hathaway
User-directed editorial style: **Value**. User-directed orientation: **Active (IR Resistant)**. Both remain visible while quantitative style is **pending calculation**, and must not be misrepresented as outputs of the factor engine.

## Acceptance tests
No future fundamentals leak; split-adjusted position reconciliation; no division by nonpositive denominators; amendments supersede originals; weights sum to 100% of eligible disclosed value; missing factors are transparent; fund-level and firm-level measures are not conflated.
