# SEC history from September 30, 2025

Filing-date catalogue: every public EDGAR form type from 2025-09-30 through the latest SEC quarterly index publication. Full submissions, including exhibits, are downloaded incrementally; catalogue membership does not mean the document has been downloaded. Holdings history includes reporting periods on or after 2025-09-30, including filings submitted later. Historical submissions pages are followed when the recent-filings window is insufficient.

## Files
- data/history/status.json: measured catalogue, archived, pending, error, and storage counts.
- data/history/catalogue/: compressed quarterly accession catalogues, all form types.
- GitHub releases tagged sec-history-raw-YYYY-MM-DD: permanent downloadable tar shards containing compressed original complete submissions, embedded manifests and SHA-256 checksums. archive_state.json.gz maps each accession to its release asset and member path. data/history/raw/ is only a temporary staging buffer.
- data/history/normalized/: original accession-level 13F and N-PORT data. N-PX and 13D/G are archived as filings, not treated as equivalent ownership statements.
- data/13f/index.json: selected latest-restated manager/report periods.
- data/funds/history_index.json: fund/report-period history; data/funds/index.json remains latest period per fund for existing consumers.
- data/history/investor_profiles/: per-period institution profiles and trailing turnover calculations.
- data/history/registrants/: per-period reported equity assets and fund orientation weights.

## Calculations
Reported 13F equity assets sum disclosed non-option share positions in USD. Total reported 13F value is retained separately. The legacy value_thousands key contains dollars for this 2025+ dataset; SEC changed reporting units in January 2023. A 13F-disclosed equity universe is incomplete institution-wide AUM.

Turnover remains the prior agreed proxy: min(estimated buys, estimated sells) divided by average disclosed portfolio equity value, annualized by elapsed days. Prior value/share approximates trade price; new positions use current value/share. Corporate actions and intra-period trades are limitations. Historical profiles use only earlier reporting periods for the turnover calculation.

13F restatements replace a period; NEW HOLDINGS amendments add positions to the preceding base/restatement. Unknown amendment types require review. N-PORT keeps the latest filing version for each fund/report date while original accessions remain in the archive. fund_id equals the SEC series ID where reported. For standalone funds with matching registrant/series LEI and name, or explicitly N/A series name and LEI, fund_id is a distinct CIK-prefixed registrant key and series_id stays null. Identity evidence is preserved; ambiguous identities remain errors. Different standalone registrants never share an empty identity key. Different periods are never summed as simultaneous fund assets. History is latest-restated, not a claim about what was known on the report date; filing dates and original accessions support later point-in-time reconstruction.

Investment style remains unknown until sourced point-in-time fundamentals support holdings-weighted factors. Active/passive institution weights require verified fund attribution, non-overlapping equity assets and a same-date denominator. Explicit index-fund names provide limited passive evidence for fund samples; other names remain unclassified. Registrant entities are not automatically ultimate advisers. Partial sample ratios are not institution-wide percentages.

## Workers and boundaries
Backfill SEC filing history runs hourly at minute 37 UTC, resumes checkpoints and shares the SEC data workflow concurrency lock. It fetches up to 1,000 submissions / 60 MB compressed per run, at no more than 2.5 sequential requests per second. HTTP 403/429 stop the batch immediately. HTTP 503 receives at most three requests with 15/45-second pauses, respecting longer Retry-After values up to the bounded worker budget; persistent failures stop the batch, preserve progress and fail visibly. Access cooldowns remain intact. Legacy in-memory size-limit failures are eligible for the newer bounded streaming downloader; eligible failed accessions precede new ones. Failures retain retry state. Verified release uploads move raw submissions out of Git while keeping accession/checksum mappings in the repository. Shards are bounded by the batch size and releases rotate daily. A 750 MB staging-buffer guard stops ingestion if release publication is unavailable; it is not a cap on the release-backed archive. No paid storage or API is enabled. This is an explicit capacity boundary, not a completeness claim. Catalogue and reporting-period coverage must be checked independently.

Official sources:
- https://www.sec.gov/about/developer-resources
- https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f

Archive storage references:
- https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
- https://docs.github.com/en/actions/concepts/billing-and-usage

Verified November 7, 2026: initial release shard published at https://github.com/cstrohwork/aibank/releases/tag/sec-history-raw-2026-11-07 . The first archive asset contains 120 original submissions and an embedded checksum/source manifest. Subsequent batches continue from the accession checkpoint.

Large N-PORT originals use disk-backed XML extraction with 64 KiB source reads, full-original SHA-256 verification and incremental position parsing. Limits remain 512 MB of original data and 500,000 supported positions per filing. A source/checksum/identity/limit failure remains an explicit normalization error. Oversized 13F normalization still retains its explicit parser limit. Push-triggered runs use a 60-second download verification window; hourly and manual runs retain the 20-minute window. Normalization and release/checkpoint stages still execute.

Reaching a batch compressed-byte or time budget stops downloads and creates an explicit deferred record, not a filing failure or SEC cooldown. Previously mislabeled batch-limit failures retain their diagnostic history and become eligible for the next run. status.json exposes deferred_filings and the current batch_deferral separately from download_failures.
