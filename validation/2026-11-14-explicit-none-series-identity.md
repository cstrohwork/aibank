# Explicit `None` N-PORT series identity — November 14, 2026

## Scope and evidence

This bounded repair covers only SEC N-PORT XML that reports all of: no `seriesId`; `seriesName` exactly `None` (case-insensitive); `seriesLei` exactly `00000000000000000000`; a valid nonzero 20-character `regLei`; a valid registrant CIK; and a non-empty registrant name.

It does not infer a series from issuer size, ticker, filing form, or name similarity. The normalized `series_id` stays null and the fund identifier remains registrant-scoped (`CIK##########`). Any near miss remains `Missing/invalid N-PORT series identifier`.

Retained public SEC original replayed:

- accession `0001493152-26-051149`, CIK `0000027367`, source `https://www.sec.gov/Archives/edgar/data/27367/000149315226051149/daxor-20260930.txt`;
- repository release asset `https://github.com/cstrohwork/aibank/releases/download/sec-history-raw-2026-11-12/sec-aab42f2b705f737bdedcf07f.tar`;
- original SHA-256 `943ac45e367334ff259ebd6d50ab7d24fe9a7af04278e357ea464a9cd8cd56e5`;
- release SHA-256 `aab42f2b705f737bdedcf07f0eef3df2a76ba766328966ffe7645dc3081cb26f`.

Observed fields were `regCik=0000027367`, `regName=DAXOR CORP`, `regLei=984500B839ED8XIK6792`, no `seriesId`, `seriesName=None`, and `seriesLei=00000000000000000000`. Patched replay produced fund `CIK0000027367`, null `series_id`, identity basis `explicit_none_series_zero_lei`, fund name `DAXOR CORP`, report date `2026-09-30`, and two supported positions.

## Validation actually executed

- `python -m unittest tests.test_worker_recovery.StandaloneIdentityTests -v` — 9 passed.
- `python -m unittest discover -s tests -v` — 193 passed.
- `python -m py_compile scripts/refresh_funds.py scripts/build_identity_master.py` — passed.
- `git diff --check` — passed.
- Checksum-retained source replay through `sec_history.normalize` — passed with two positions and the exact identity above.

The negative regression confirms a zero series LEI with any series name other than explicit `None` remains unknown/error. Existing differing-LEI, unmatched-name and blank-LEI cases also remain blocked.

## Remaining gaps and next task

At the inspected production checkpoint there were 46 normalization failures: 37 missing/invalid series identities and nine filings with no supported N-PORT positions. This repair is expected to clear only exact explicit-`None`/zero-LEI records after an existing serialized backfill retries them; no production clearance is claimed here.

Next, inspect the post-merge retry checkpoint and subtract only records actually normalized. Then examine one remaining SEC-original identity pattern at a time. Do not accept name-only identities, differing registrant/series LEIs, blank evidence, or unsupported positions as successful. The current SPTM/IWV universe remains a dated ETF-holdings proxy, not official index membership; outside-proxy large/mega-cap additions still require verified point-in-time market capitalization and U.S. exchange listing.
