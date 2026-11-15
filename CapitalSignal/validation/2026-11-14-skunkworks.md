# Skunkworks Data Lab

50 new live analyses at `/CapitalSignal/skunkworks/`, organized into five groups of ten. Every analysis has a source scope, chart, accessible table, stable fragment URL and complete CSV export. Categories and text search filter the catalog. General views support separate manager/fund lenses and exact reporting dates; common-entity comparisons use explicit current/prior dates.

Security sample: 50 largest manager candidates at 2026-09-30, all 50 exact-version validated. 12,303 distinct CUSIPs and 165,440 distinct manager/CUSIP links. This is a bounded sample, not full market coverage. No manager/fund totals or shares-outstanding ownership percentages are calculated. Portfolio weights stay within individual manager disclosures.

`build_ownership_atlas.py` now refreshes the sample after publishing the Atlas period files. Existing intelligence workflow already commits, guards and retains artifacts from the Atlas data directory; its JS safeguard step now includes the Skunkworks tests. The sample is generated from committed source caches without new external data requests.

Validation: 9 JS tests passed (including Atlas gates), 3 Python tests passed (Atlas publication and sample source gates), syntax checks and diff whitespace checks passed. All 50 analyses executed on published data with finite or explicitly null results. Every sample manager/security pair is unique and weights and concentration metrics are bounded. Desktop browser verified initial loading, all 50 cards, security detail, fund selection, search and separate sample labels. Visual types include bars, percentile lines, count heatmaps, an entity-count donut, and concentration lollipops. Responsive layouts use three, two and one columns.

Data source generation: 2026-11-15T00:06:38Z (November 14, 2026, 7:06 PM EST). General starting coverage: 7,122 September manager summaries; June comparison coverage 8,918; common manager cohort 7,039. Counts reflect this dated incomplete cache and will evolve on rebuild.
