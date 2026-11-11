# Bounded streaming SEC archive — November 10, 2026

Base: https://github.com/cstrohwork/aibank/commit/77682834abd4a9eb77d4e56f93ff55ece68e1a94

## Change
Stream complete SEC submissions in 64 KiB reads into temporary gzip staging. Hash the exact uncompressed original; validate the SEC document prefix and Content-Length when provided. Atomically replace the destination only after validation. Delete temporary files on HTTP, network, size, deadline or validation failures; preserve any existing destination. Enforce a 512,000,000-byte raw limit, remaining 60,000,000-byte compressed batch budget, remaining 750,000,000-byte staging allowance and 20-minute batch deadline (network reads retain the 60-second socket timeout). Raw blobs remain release-backed.

Only supported holdings forms enter the existing parser. Originals over its 80,000,000-byte memory limit retain an explicit normalization_error and are not reloaded during reparse; archive completion never implies calculated-history completion. The status remains in_progress while normalization/download/index errors exist. Source URLs, SHA-256 provenance, unknown classifications and report-period logic remain intact. No workflow, runtime data, classification, account or deployment was changed.

## Checks actually executed
- Read backlog, SEC_HISTORY.md, status, repository tree, main head, open PRs and current workflow runs via authorized GitHub plugin. Recursive tree was not truncated and contained no AGENTS.md.
- Downloaded current-main Python sources from pinned base. Existing main suite: 11 tests passed.
- Six new test methods passed, including 81,000,000-byte generated streaming input (above the previous limit), exact digest/gzip round-trip, bounded read sizes, raw/compressed caps, truncation, invalid SEC prefix, deadline, connection interruption, HTTP 503 propagation, atomic cleanup and preservation of an existing original.
- Integration test verifies oversized N-PORT remains archived with explicit normalization error and in_progress status; repeat reparse does not load it into memory.
- Fresh isolated directory containing current-main scripts and only repository baseline plus new tests: python -m unittest discover -s tests -v — 17 passed, exit 0. Full output: 2026-11-10-streaming-tests.txt.
- Initial discovery in shared scratch encountered residual PR #1 tests against main (two errors, one failure); resolved by the isolated suite above. No stale tests or sources are included in this PR.
- Binary read fallback: fetch_blob raised UnicodeDecodeError and generic fetch rejected binary; fetch_file encoding=base64 succeeded, followed by local decoding. An oversized command argument failed before execution; writing the base64 to a local scratch file resolved it.
- Workflow-by-filename fetch was rejected as unsupported; repository-wide run listing succeeded.
- No live SEC download, refresh dispatch, cloud execution or deployment of this patch occurred. Actual oversized accessions remain unresolved until this patch is merged and existing serialized backfill retries them. Large holdings normalization beyond the parser cap remains future work. PR #1 and PR #2 remain open and are not duplicated or merged here.

## Current measured state
status.json at 2026-11-10T04:47:21.973127+00:00: 996,473 catalogued; 6,349 archived; 990,124 pending; 47 downloaded in latest run; three download failures; three normalization failures; zero index errors; git_raw_bytes=0; storage_blocked=false. Catalogue membership is not download or calculation completion.

Decoded archive_state from blob 79c4289ffcba7b5c75d7075a53cd851c64352f67:
- 0000929638-25-003679, 0000929638-25-003681, 0000929638-25-003682: "Response exceeds configured byte limit; requires larger archive storage"; retry_after=2026-11-10.
- 0002071691-25-002515: "No supported N-PORT positions" (pending PR #1).
- 0000894189-25-011392 and 0000850027-25-000007: "Missing/invalid N-PORT series identifier".
Exact records including source and release provenance: 2026-11-10-retained-errors.json.

Existing completed runs (pre-patch):
- Refresh: https://github.com/cstrohwork/aibank/actions/runs/42676752137 — success, November 9 13:46 ET.
- Backfill: https://github.com/cstrohwork/aibank/actions/runs/42757849608 — success, November 9 23:47 ET; job 129636296722 stages confirmed completed, including publication/rebuild/checkpoint.
- Health: https://github.com/cstrohwork/aibank/actions/runs/42758103239 — success, November 9 23:48 ET.
- Pages: https://github.com/cstrohwork/aibank/actions/runs/42758094632 — success, November 9 23:48 ET.
No running job was returned at inspection. These results do not validate the proposed patch or browser-level website behavior.

## Next task and exact blockers
Review/merge PR #1, PR #2 and this streaming change, preserving each backlog appendix. PR #2's download tests mock the old fetch path; adapt those mocks to archive_submission when integrating and run the combined suite before merge. Observe the next existing serialized backfill and verify the three actual oversized submissions publish with matching original and release checksums. If they exceed the new raw or compressed bounds, retain explicit failures and measure them before adjusting limits. Verify the two missing fund series identities from public SEC evidence; never invent IDs. Full coverage, sourced adviser mappings, style fundamentals and institution-wide orientation denominators remain unavailable.

