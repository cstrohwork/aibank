# Zero-placeholder standalone N-PORT identity — November 15, 2026

## Production evidence and bounded rule

The only normalization failure in the committed `2026-11-15T06:41:54Z` history checkpoint is SEC accession `0001193125-26-365227`, filed by StepStone Private Credit Co-Investment Fund (CIK `0002059105`). The retained source is the public SEC submission:

- `https://www.sec.gov/Archives/edgar/data/2059105/0001193125-26-365227.txt`
- repository release asset: `sec-7099e712af0ea39fe717e808.tar`
- release asset SHA-256: `7099e712af0ea39fe717e808829f489a511965b79de760601c20637d97383035`
- decompressed original SHA-256: `953ee1016b6016892580966376dd9dd92663177bb4902feb4a00b3850547b716`

The checksum-verified SEC XML reports:

- registrant name `StepStone Private Credit Co-Investment Fund`;
- series name `StepStone Private Credit Co-Investment Fund` (exact normalized-name match);
- valid nonzero registrant LEI `635400AX1GSEOLMETX34`;
- all-zero placeholder series LEI `00000000000000000000`;
- no series ID;
- report date `2026-06-30`; and
- 356 investment-position elements.

The new rule permits a registrant-scoped fund identity only for this evidence pattern: valid registrant CIK, nonempty registrant name, exact normalized registrant/series-name equality, valid nonzero registrant LEI, absent series ID, and an all-zero 20-character series LEI. The normalized fund ID is `CIK0002059105`; `series_id` remains null; the explicit basis is `matching_registrant_series_name_zero_placeholder_series_lei`.

This does not infer an adviser or parent, and it does not treat an all-zero LEI as a valid identifier. A different series name, missing/invalid registrant LEI, two all-zero LEIs, malformed series ID, or other incomplete evidence remains an error/unknown. Identity-master publication accepts only the exact new basis and retains the fund/registrant relationship as `registered_under`.

## Validation actually executed

- `python -m unittest tests.test_worker_recovery.StandaloneIdentityTests -v` — 14 passed.
- `python -m unittest tests.test_identity_master.IdentityTests -v` — 6 passed.
- `python -m unittest discover -s tests -v` — 201 passed.
- `python -m py_compile scripts/refresh_funds.py scripts/build_identity_master.py` — passed.
- `git diff --check` — passed.
- Exact retained-original replay through `sec_history.normalize` — one normalized fund record, 356 holdings, `reported_position_count=356`, `position_coverage=parsed_supported_positions`, report date `2026-06-30`, null series ID, and the explicit new identity basis.

The first targeted run exposed that equal all-zero registrant and series LEIs were previously accepted by the generic equality predicate. The predicate now requires both LEIs to be valid and nonzero; the new negative regression confirms placeholder-only evidence remains unknown.

## Incomplete state and next task

This checkpoint precedes pull-request cloud validation and production replay. It does not claim the final normalization failure has cleared. The existing serialized backfill remains the only active writer and was not duplicated.

Next: pass cloud review, merge safely against current `main`, then inspect a committed serialized retry before reporting zero normalization failures. Continue the September 2025 queue, followed by December 2025 and March 2026. Retain any new SEC/download/normalization errors individually.

Historical ownership coverage remains incomplete. Point-in-time prices, share-class market capitalizations, float denominators, and historical official benchmark constituents/weights remain unavailable. The fundamentals universe remains the current dated SPTM/IWV ETF-holdings proxy union, not official index membership; outside-proxy large/mega issuers remain excluded without verified dated market capitalization and U.S.-exchange listing evidence.
