# Identity publication sharding validation — November 14, 2026

## Trigger and scope

The current fundamentals ingestion is healthy, while the newest intelligence publication failed. Workflow [43597281350](https://github.com/cstrohwork/aibank/actions/runs/43597281350) executed its calculation stages and artifact upload, then GitHub rejected the production push because `identity_master.json` was 115,653,485 bytes (110.30 MiB), above the 100 MiB limit.

This implementation changes generated identity storage only. It does not add or infer issuer mappings, historical effective dates, adviser/parent relationships, benchmark membership, market capitalization, style or orientation.

## Implementation

- `identity_master.json` becomes a small manifest with publication schema version 2.
- Seven identity collections are serialized into deterministic, checksum-addressed JSON shards under `identity_master_shards/`.
- Every shard is capped at 20,000,000 bytes; any single record above the bound fails explicitly.
- The reader verifies each shard's byte count, SHA-256, collection name and record count before reconstructing data.
- Stale generated shard directories are replaced as a unit; the visible manifest is written last.
- `identity_status.json` records format, shard count and largest shard.
- The workflow rejects any generated intelligence/model-company file above 95,000,000 bytes before committing.

## Checks executed

- `python -m unittest discover -s tests -v`: **175 tests passed** in 1.325 seconds.
- New regression: exact shard round trip, per-file size cap, forced multiple shards, compact manifest and corruption detection.
- `git diff --check`: passed.
- No live SEC download or competing refresh was launched.

## Real failed-artifact replay

Source: failed workflow artifact [14115113358](https://github.com/cstrohwork/aibank/actions/runs/43597281350/artifacts/14115113358), digest reported by GitHub as `sha256:612b50d786b66147a0cb11871fbac953674d89923d3bd533b4b9aab5aa3e1b72`.

| Measure | Verified result |
|---|---:|
| Original monolith | 115,653,485 bytes |
| Manifest | 3,360 bytes |
| Shards | 12 |
| Largest shard | 19,999,969 bytes |
| Entities | 27,270 |
| Securities | 399,893 |
| Security/issuer observations | 3,011 |
| Relationships | 13,782 |
| Quarantine records | 12,756 |
| Exact reconstructed equality | Yes |

## Current fundamentals evidence

Dedicated ingestion [43595158674](https://github.com/cstrohwork/aibank/actions/runs/43595158674) completed successfully. Both source snapshots are dated November 12, 2026:

- SPTM current holdings proxy: State Street source checksum `1c91e529a268bbeb5754ef8d9bfad8079e61c89e7cf6d98c055609be9f983de3`.
- IWV current holdings proxy: iShares source checksum `08a8fa1a1b0a095c35d6c88b4de6fea57977fe2bd40adf2026a78b0697750fc1`.

The 2,592-security union is current ETF holdings proxy coverage, not official S&P Composite 1500 or Russell 3000 membership. It contains 2,579 CIK-matched securities, 2,561 distinct mapped issuers and 2,559 successful Companyfacts caches. SEC Companyfacts returned 404 for CIKs `0001492165` and `0001569650`; they remain pending. Large/mega-cap issuers outside both proxies remain excluded until dated market capitalization and U.S. exchange listing evidence are both verified.

## Remaining gates

Cloud PR execution and production publication of the new format are unverified at this checkpoint. Historical benchmark constituents/weights, point-in-time class prices and capitalization, complete sectors, two Companyfacts records, ownership history, and benchmark-aligned style inputs remain incomplete. No style or active/passive classification may pass until its existing coverage gates are met.

