# Capital Signal — Holdings-based investment style methodology (v0.1)

## Required inputs
For each manager and reporting period: SEC CIK, accession, filing and report dates, security CUSIP, issuer, position market value, shares and instrument type. Use amended filings as the effective version, preserving superseded versions. Resolve securities to permanent issuer IDs, ticker history and issuer fundamentals *as of the portfolio measurement date*.

For each issuer obtain price, shares outstanding, market cap, book equity, trailing earnings (with negative earnings flagged), trailing revenue, EBITDA/enterprise value where available, forward earnings estimates where licensed, revenue growth (3y), EPS growth (3y), analyst forward growth where licensed, ROE/ROIC, operating margins, leverage, sector/industry and fiscal reporting dates. SEC companyfacts/XBRL and SEC submissions are free primary sources for many backward-looking fundamentals; prices, sector mappings and analyst forecasts need separately documented, lawful sources. Do not fill missing forward estimates with fabricated values.

## Scoring
1. Restrict to ordinary listed equity; separately report ADRs, ETFs, options, preferred and unclassified securities. Do not confuse the manager's 13F value with firm-wide equity AUM.
2. Join positions to issuer fundamentals using point-in-time effective dates and filing availability dates to avoid look-ahead bias. Capture raw fields, units, provenance and missingness.
3. Compute industry-relative percentile ranks for value: earnings yield (positive earnings only), book-to-price, EBITDA/EV (positive EBITDA and EV only), and free-cash-flow yield where reliably derived. Compute growth percentiles for historical sales CAGR, EPS growth (when meaningful), and available forward estimates. Do not treat negative or absent denominators as extreme value.
4. Each security's value and growth scores are the equally weighted mean of its **available valid** factor percentiles, with at least two valid factors per dimension for a full classification. Require at least 70% of eligible disclosed equity value to have both dimension scores; otherwise mark insufficient coverage and provide partial diagnostics.
5. Aggregate security scores by disclosed market-value weights, renormalized over classified eligible equities. Compare portfolio value/growth scores to a same-date, sector-matched reference universe to distinguish style from sector exposure. Store value/growth score, benchmark-relative difference, classified weight, missing weight, and factor contributions.
6. Classification thresholds (initial, subject to calibration): Value if value-minus-growth percentile score >= 15 points; Growth if <= -15; Blend otherwise. Expose **style confidence** and underlying scores. A manager with materially different fund strategies should be assessed fund-by-fund and consolidated using verified fund equity AUM weights, not arbitrary fund counts.
7. Update whenever a new 13F amendment, N-PORT portfolio, or newly available point-in-time fundamentals changes a relevant input; retain historical snapshots and filing accession lineage. Recompute on a nightly fundamentals refresh as a fallback. Never overwrite user-directed editorial labels silently; keep them distinct from calculated style.

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
