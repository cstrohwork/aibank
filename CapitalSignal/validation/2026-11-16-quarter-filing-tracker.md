# SEC quarter filing tracker — November 16, 2026

## Scope

The SEC history status now publishes a filing-date tracker for every covered calendar quarter. It separates:

- all catalogued public EDGAR filings;
- complete submissions archived;
- remaining, waiting, failed, and deferred filings;
- investor-form discovery and archive counts; and
- successfully parsed 13F-HR/NPORT-P position schedules and normalization errors.

Catalogue membership is explicitly not treated as document-download or normalized-history completion. The tracker labels the current quarter and the initial September 30, 2025 coverage boundary as partial windows.

The Worker Dashboard renders these committed measurements as a table. It does not infer success from workflow scheduling.

## Validation executed

- 21 focused SEC history and intake-priority tests passed.
- All 224 Python tests passed.
- Worker Dashboard JavaScript syntax validation passed with Node.
- Python compilation and `git diff --check` passed.
- Exact current-main cache audit produced the expected full 2026 Q3 window (July 1–September 30): 216,075 catalogued, 45,534 archived, 170,541 not archived, 45,534 investor forms discovered/archived, 23,798 position forms parsed, and zero normalization errors. These local audit counts remain unpublished until a successful post-merge SEC history checkpoint regenerates status.

