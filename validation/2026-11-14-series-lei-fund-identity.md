# SEC series-LEI fund identity — November 14, 2026

## Bounded rule

When an N-PORT filing omits `seriesId` but reports a valid, nonzero 20-character `seriesLei` that differs from `regLei`, the parser now uses the SEC-reported series LEI as the stable fund identifier. The normalized identifier is `LEI<seriesLei>`, `series_id` remains null/unknown, the registrant CIK and both reported LEIs remain attached, and identity provenance is `sec_series_lei_without_series_id`.

The identity master publishes these as `fund:lei:<seriesLei>` entities registered under the filing registrant. It does not collapse them to a registrant CIK, manufacture an SEC series ID, or fuzzy-match names. Blank, malformed, all-zero, or equal registrant/series LEIs continue through the existing evidence rules or remain explicit errors.

## Retained SEC-original replay

All nine remaining missing-series originals were read from their checksum-addressed repository release shards and replayed through `sec_history.normalize`:

| accession | SEC series LEI / result | positions | original SHA-256 |
|---|---:|---:|---|
| `0001193125-25-332684` | `2549004018I6K1D84P65` | 108 | `5b94891eae395ddc3366ca58d22fd97ed4ea577ca44d77fc2739cc2da2309ee2` |
| `0001193125-25-332686` | `254900DGKUAQ21QT3855` | 124 | `b79255ff2f1b49f95b4bef52cc251f5213349774d38b0d8d85504aa025df069c` |
| `0001193125-26-406659` | `549300F0T6P9SK1RUD31` | 490 | `5c7188ab8ce824d4a6a0996f75f1f27ec9c5962be8531fed2558ce0055acaa45` |
| `0001410368-26-088527` | `549300KR7BCWAQBKVZ78` | 72 | `4ec83957c7262dcb754e2febe0b76ef93c7bb14ba18e7b92986e06338b2cc043` |
| `0001410368-26-089927` | `254900XO9MI3JWD3TK53` | 108 | `728273c14616fad4e246e8d07e3893d388dc8858055937a4b9a7af3376712253` |
| `0002008638-26-000020` | `254900DGKUAQ21QT3855` | 118 | `f9ce115dbfa6420b98542aed6545b90dcc7eb734fd1f62196eb3153441e214ae` |
| `0002022674-26-000017` | `549300VKWK774XXSGI69` | 37 | `d9fc13df77d1132d6eaeabcb779912838dcb7619e2dd73f1fb3a948011086ad5` |
| `0002035632-26-000020` | `2549004018I6K1D84P65` | 139 | `23c682907569aafd6d0a494e5fce6b1f9a4bcb648cf430b0950cda482abe7752` |
| `0001193125-26-365227` | blocked: all-zero placeholder series LEI | — | `953ee1016b6016892580966376dd9dd92663177bb4902feb4a00b3850547b716` |

The eight valid records produced 1,196 positions across six distinct series LEIs. Repeated John Hancock series LEIs remained stable across 2025 and 2026 filings. The StepStone zero-placeholder record stayed `Missing/invalid N-PORT series identifier`.

Release assets used were the repository's `sec-history-raw-2026-11-12`, `sec-history-raw-2026-11-13`, and `sec-history-raw-2026-11-14` checksum-addressed shards recorded in `archive_state.json.gz`. No SEC source or retained original was modified.

## Validation actually executed

- `python -m unittest tests.test_worker_recovery.StandaloneIdentityTests -v` — 10 passed.
- `python -m unittest tests.test_identity_master.IdentityTests -v` — 5 passed.
- `python -m unittest discover -s tests -v` — 195 passed after extracting the current repository's model fixtures into the isolated tree.
- `python -m py_compile scripts/refresh_funds.py scripts/build_identity_master.py` — passed.
- Nine retained-original normalization replays — eight parsed, one explicitly blocked as described above.

An initial full-suite attempt in a deliberately partial source extraction lacked `CapitalSignal/model` fixtures and produced three `FileNotFoundError`/Node module errors. After the unmodified current-main model assets were extracted, the complete suite passed; those setup errors were not product-code failures.

## Current incomplete state and next task

Before this patch, production held 19 normalization failures: nine missing-series and ten unsupported-position filings. This implementation is expected to resolve eight missing-series records only after an existing serialized worker retries and commits them; no production clearance is claimed here.

Next: verify the cloud review and merge, then inspect an actual serialized checkpoint. The remaining zero-placeholder identity and unsupported-position filings stay blocked unless their exact SEC originals provide additional evidence. Current SPTM/IWV membership remains a dated ETF-holdings proxy rather than official index membership. Outside-proxy large/mega-cap issuers remain excluded without verified point-in-time market capitalization and U.S. exchange listing.
