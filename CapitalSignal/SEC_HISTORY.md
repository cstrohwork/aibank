# SEC history from September 30, 2025

Filing-date catalogue: every public EDGAR form type from 2025-09-30 through the latest SEC quarterly index publication. Full submissions, including exhibits, are downloaded incrementally; catalogue membership does not mean the document has been downloaded. Holdings history includes reporting periods on or after 2025-09-30, including filings submitted later. Historical submissions pages are followed when the recent-filings window is insufficient.

## Files
- data/history/status.json: measured catalogue, archived, pending, error, and storage counts.
- data/history/catalogue/: compressed quarterly accession catalogues, all form types.
- data/history/raw/: compressed original complete submissions, SHA-256 tracked in archive_state.json.gz.
- data/history/normalized/: original accession-level 13F and N-PORT data. N-PX and 13D/G are archived as filings, not treated as equivalent ownership statements.
- data/13f/index.json: selected latest-restated manager/report periods.
- data/funds/history_index.json: fund/report-period history; data/funds/index.json remains latest period per fund for existing consumers.
- data/history/investor_profiles/: per-period institution profiles and trailing turnover calculations.
- data/history/registrants/: per-period reported equity assets and fund orientation weights.

## Calculations
Reported 13F equity assets sum disclosed non-option share positions in USD. Total reported 13F value is retained separately. The legacy value_thousands key contains dollars for this 2025+ dataset; SEC changed reporting units in January 2023. A 13F-disclosed equity universe is incomplete institution-wide AUM.

Turnover remains the prior agreed proxy: min(estimated buys, estimated sells) divided by average disclosed portfolio equity value, annualized by elapsed days. Prior value/share approximates trade price; new positions use current value/share. Corporate actions and intra-period trades are limitations. Historical profiles use only earlier reporting periods for the turnover calculation.

13F restatements replace a period; NEW HOLDINGS amendments add positions to the preceding base/restatement. Unknown amendment types require review. N-PORT keeps the latest filing version for each series/report date while original accessions remain in the archive. Different periods are never summed as simultaneous fund assets. History is latest-restated, not a claim about what was known on the report date; filing dates and original accessions support later point-in-time reconstruction.

Investment style remains unknown until sourced point-in-time fundamentals support holdings-weighted factors. Active/passive institution weights require verified fund attribution, non-overlapping equity assets and a same-date denominator. Explicit index-fund names provide limited passive evidence for fund samples; other names remain unclassified. Registrant entities are not automatically ultimate advisers. Partial sample ratios are not institution-wide percentages.

## Workers and boundaries
Backfill SEC filing history runs hourly at minute 37 UTC, resumes checkpoints and shares the SEC data workflow concurrency lock. It fetches up to 120 submissions / 60 MB compressed per run, at no more than 2.5 sequential requests per second. SEC blocks stop the batch and failures retain retry state. The initial Git-backed raw archive pauses at 750 MB; reaching that limit requires a larger durable storage backend before a complete all-form full-document archive can finish. No paid storage or API is enabled. This is an explicit capacity boundary, not a completeness claim. Catalogue and reporting-period coverage must be checked independently.

Official sources:
- https://www.sec.gov/about/developer-resources
- https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f
