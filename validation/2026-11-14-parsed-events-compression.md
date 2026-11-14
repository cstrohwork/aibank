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
