# Release-shard normalization reader repair — November 14, 2026

## Retained production evidence

- Main inspected at `66e2a6ef6af96d510fa60c637c613f15bc93d35d` while backfill [43628634547](https://github.com/cstrohwork/aibank/actions/runs/43628634547) was already active. No duplicate ingestion was launched.
- Saved history checkpoint at 18:42:56 UTC: 1,011,314 catalogued; 76,574 archived; 934,740 pending; 6,072 June-2026 intake-window filings outstanding; live feed `ok`; zero download failures; 71 normalization failures; `storage_blocked=false`.
- The 71 retained failures comprise 39 missing/invalid N-PORT series identifiers, 23 release-response byte-limit failures and nine filings with no supported N-PORT positions. Those categories remain separate and are not relabelled as successful.
- The 23 byte-limit records reference six checksum-addressed repository release assets. GitHub reports exact sizes of 119,920,640; 100,935,680; 100,710,400; 100,659,200; 100,474,880; and 100,229,120 bytes. Each published asset digest matches the digest retained in archive state.

## Bounded implementation

- Raised only the release-asset retrieval ceiling from 100,000,000 to 125,000,000 bytes. The SEC download/archive batch budget remains 100,000,000 bytes; this does not increase intake volume or Git storage.
- The existing full release SHA-256 check remains mandatory before tar access, and the original decompressed SEC submission SHA-256 remains mandatory before normalization.
- Added a regression asserting the exact 125,000,000-byte ceiling, coverage of the measured 119,920,640-byte maximum, and continued bounded retrieval.

## Validation actually executed

- `python -m unittest tests.test_sec_history -v`: 12 tests passed.
- `python -m unittest discover -s tests -v`: 189 tests passed.
- Downloaded the largest retained release asset through the patched reader: 119,920,640 bytes; release SHA-256 verified. Extracted accession `0000910472-26-015636`: 30,452 decompressed bytes; original SHA-256 verified.
- The replay then reached the source parser and reported `Missing/invalid N-PORT series identifier`. That filing therefore remains an explicit identity error; the byte-limit repair does not falsely mark it normalized.

## Remaining work

- This checkpoint precedes PR/cloud execution. Do not claim the 23 production records cleared until a completed serialized backfill publishes a new checkpoint.
- After cloud checks and merge, let the existing serialized worker retry retained normalization records. Compare error categories and inspect any records that transition from transport limits to missing-series or unsupported-position evidence.
- Next bounded implementation after production replay: resolve only missing series identities supported by exact SEC registrant/series evidence; otherwise preserve unknown identity. Historical coverage and reported-investor calculations remain incomplete.
