# Parsed event checkpoint publication repair — 2026-11-14

## Failure evidence

- Intelligence workflow run [43619849245](https://github.com/cstrohwork/aibank/actions/runs/43619849245) completed calculation stages, then failed its publication guard because `CapitalSignal/data/intelligence/parsed_events.json` exceeded 95,000,000 bytes.
- Retained workflow artifact [14123719304](https://github.com/cstrohwork/aibank/actions/runs/43619849245/artifacts/14123719304) contains the failed output. The artifact is evidence of a completed calculation attempt, not a published production checkpoint.

## Bounded repair

- Replaced the growing monolithic JSON publication with a compact JSON status/index and a deterministic gzip-compressed, content-addressed record file.
- The compressed record file preserves filings, SEC source URLs and hashes, beneficial-ownership observations, proxy votes, unavailable records, unsupported accessions, unknown values and limitations without filtering or classification inference.
- The index records compressed and uncompressed sizes and SHA-256 digests. Loading verifies both digests before records are used. A new index is published only after its content-addressed file is durable; obsolete content-addressed files are then removed.
- Legacy monolithic checkpoints remain readable for the one-time migration. A corrupt or mismatched compressed checkpoint fails explicitly instead of silently reverting to an empty dataset.

## Validation actually executed

- `python -m unittest discover -s tests -v`: 188 tests passed on Python 3.12.
- `node --test tests/atlas-core.test.cjs`: 4 tests passed.
- `python -m py_compile scripts/parse_investor_events.py`: passed.
- `git diff --check`: passed.
- Replayed the retained production artifact through the new writer and reader. The 343,905,424-byte JSON became a 13,691,798-byte gzip record file with exact object round-trip equality. Preserved counts: 4,006 filing rows; 7,951 beneficial-ownership records; 308,764 proxy-vote records; 18,178 unavailable filings. Compressed SHA-256: `2936a75c69ceb86c6482d272f1fe347712318ebbc32b99aefdb7d5ec1f59ddab`.

## Remaining work and limits

- This checkpoint precedes PR/cloud execution. Do not claim publication recovery until a completed workflow passes the guard and commits the new index and record file.
- The SEC history backfill was already active during development and was not duplicated or interrupted.
- Next: verify the PR checks, merge only if current-main compatibility remains clean, then verify the production intelligence workflow publishes the compressed checkpoint. After that, address retained normalization errors, including release shards that exceed the reader's current 100 MB byte budget, from exact archive evidence.
- Historical coverage remains incomplete. Proxy membership remains current SPTM/IWV ETF holdings proxy coverage, not official index membership. Unsupported classifications and unverified market inputs remain unknown.

## Cloud publication verification

- [PR #13](https://github.com/cstrohwork/aibank/pull/13) passed cloud health [43624579719](https://github.com/cstrohwork/aibank/actions/runs/43624579719) and merged as [e6d3f81](https://github.com/cstrohwork/aibank/commit/e6d3f8158a036fbd25fc6b71e321f04a3bd6838b).
- Production intelligence [43624823470](https://github.com/cstrohwork/aibank/actions/runs/43624823470) passed 188 Python tests, four Node tests, all calculation stages, the 95 MB guard, artifact preservation and publication. Derived data commit: [44e5485](https://github.com/cstrohwork/aibank/commit/44e5485d7b30b5723971ae7cdf6be09bcca077af).
- Production index generated at 2026-11-14T18:15:14Z points to `parsed_events-3625ce110fe48ef9.json.gz`: 13,695,286 compressed bytes / 343,966,134 uncompressed bytes. Production status remains `partial`: 22,527 archived candidate filings; 3,942 parsed; 64 unsupported; 18,585 remaining archived filings. This is stable publication, not complete event coverage.
- Merge health [43624823412](https://github.com/cstrohwork/aibank/actions/runs/43624823412) and Pages deployment [43624823042](https://github.com/cstrohwork/aibank/actions/runs/43624823042) completed successfully. Browser behavior was not separately asserted.
- Concurrent backfill [43623377878](https://github.com/cstrohwork/aibank/actions/runs/43623377878) remained active and was not interrupted. Last committed checkpoint before this documentation update: 1,011,314 catalogued / 75,257 archived / 936,057 pending; 656 downloaded in the saved run; zero download failures; 71 normalization failures; storage not blocked. June 2026 remained the active target with 7,338 outstanding.
