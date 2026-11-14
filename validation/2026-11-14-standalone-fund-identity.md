# Source-evidenced standalone fund identity — November 14, 2026

## Production evidence reviewed

- Main inspected at `6ceb411d9eb2064df930029e5e8ffbafa33d9882`. Release-reader production run [43630401127](https://github.com/cstrohwork/aibank/actions/runs/43630401127) succeeded and committed a checkpoint at 19:40:01 UTC: 77,826 archived / 933,488 pending; 4,799 June-window filings outstanding; zero download failures; 71 normalization failures; storage not blocked.
- The prior 23 release byte-limit records became eight remaining byte-limit records and 15 source-level identity errors. Total errors remained 71 because those sources were no longer hidden behind transport failures. Current categories: 54 missing/invalid N-PORT series identifiers, eight release byte-limit records awaiting their rotation slot, and nine filings with no supported N-PORT positions.
- Serialized successor backfill [43633787406](https://github.com/cstrohwork/aibank/actions/runs/43633787406) was already active. No duplicate ingestion was launched.

## Bounded implementation

- For an N-PORT filing without a valid SEC series ID, accept a registrant-scoped fund identity only when public filing evidence establishes one of these conditions: a valid 20-character registrant LEI exactly equals the series LEI; or the normalized registrant and series names exactly match while the filing explicitly reports series LEI `N/A`.
- Preserve the existing stricter basis when both name and LEI match. Preserve explicit `N/A` series-name handling. Record distinct identity-basis values for equal-LEI/name-mismatch and equal-name/no-series-LEI evidence.
- Different valid registrant and series LEIs still fail. Name mismatch with unavailable series LEI still fails. `series_id` remains null; no SEC series identifier is invented.
- The identity master recognizes only the three evidenced registrant-scoped bases. Other CIK-shaped fund IDs remain quarantined as unverified.

## Validation actually executed

- `python -m unittest tests.test_worker_recovery.StandaloneIdentityTests -v`: seven tests passed.
- `python -m unittest discover -s tests -v`: 191 tests passed.
- Replayed 11 checksum-verified retained SEC originals across two repository release assets. Ten parsed successfully into 2,264 positions using explicit evidence: eight equal-LEI identities and two exact-name/series-LEI-`N/A` identities.
- Accession `0001193125-26-406659` remains `Missing/invalid N-PORT series identifier` because its registrant and series LEIs differ. It was not force-mapped.

## Remaining work

- This checkpoint precedes PR/cloud execution. Do not claim production errors cleared until a serialized backfill publishes a new archive-state checkpoint.
- After merge, inspect exact category transitions and identity-master quarantine counts. Continue reviewing remaining missing-series records by checksum-verified SEC evidence; ambiguous or contradictory evidence stays unknown.
- Fundamentals remain the current dated SPTM/IWV ETF holdings proxy union, not official index membership. Outside-proxy large/mega-cap issuers remain excluded without point-in-time market-cap and U.S.-listing evidence.
