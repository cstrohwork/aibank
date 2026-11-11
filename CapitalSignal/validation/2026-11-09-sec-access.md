# SEC access circuit breaker validation — November 9, 2026

Base: https://github.com/cstrohwork/aibank/commit/8ec624b91b36e53a87966678ff38aa3f285199a5

## Bounded implementation
Stop the submission-download batch on HTTP 503 as well as existing 403/429 access interruptions. Save the accession, source URL, HTTP status, error and retry date in status.json as download_interruption. Persist the archive/checkpoint before exiting nonzero even when earlier downloads succeeded. Existing workflow always() stages still publish retained originals, rebuild and persist checkpoints. No workflow dispatch, duplicate ingestion, runtime-counter rewrite, holdings/classification change, or paid service.

Selected because current priority calls for actionable SEC access/error handling and archive records show eight HTTP 503 failures while the latest job concluded success. PR #1 already handles old N-PORT report-date exclusions and was not duplicated.

## Checks actually executed
- All repository tree paths inspected for AGENTS.md: none. Backlog, SEC_HISTORY.md, history status, current main, open PRs and workflow state read through authorized GitHub plugin.
- Current-main sources fetched at the pinned base SHA into a fresh isolated directory. Baseline: python -m unittest discover -s tests -v — 11 passed.
- New regression suite before the fix: three test methods, four failing assertions/subtests and one error. Reproduced missing interruption evidence, continued 503 requests, and false success after partial progress.
- After fix: python -m unittest discover -s tests -v — 14 passed, exit 0.
- Separate compatibility directory combined this change with PR #1 parser normalization function and tests at 9f8397ac34aa4735c2fe64f3bf2ba4d6f96d4df5: same command — 20 passed, exit 0. This was local compatibility validation, not a merge or cloud run.
- Cases cover 403/429/503 after successful archival, 503 without progress, retained original checksum round-trip, retry evidence, untouched pending accessions, and accession-specific 404 continuation.
- An initial discovery in the shared scratch directory encountered residual PR #1 tests against main and failed (two errors, one failure); those files were not used as current repository source. The isolated main and compatibility results above resolve that contamination.
- The plugin's fetch_blob could not decode gzip (UnicodeDecodeError); fetch_file with encoding=base64 successfully retrieved archive_state at its current SHA for local decoding.
- One workflow-by-filename API URL was rejected as an unsupported fetch endpoint. Repository-wide run listing succeeded and supplied the refresh state below.
- No live SEC request, ingestion, deployment, or cloud test of this patch was executed.

## Verified existing workflow state
| Workflow | Completed conclusion | Run |
| --- | --- | --- |
| Refresh SEC EDGAR public-data cache | success, 2026-11-08 15:10:17 UTC | https://github.com/cstrohwork/aibank/actions/runs/42493354266 |
| Backfill SEC filing history | success, 2026-11-09 12:05:12 UTC | https://github.com/cstrohwork/aibank/actions/runs/42613306615 |
| Capital Signal cloud health worker | success, 2026-11-09 12:05:32 UTC | https://github.com/cstrohwork/aibank/actions/runs/42614081941 |
| Pages build and deployment | success, 2026-11-09 12:06:02 UTC | https://github.com/cstrohwork/aibank/actions/runs/42614069565 |

Refresh is within 36 hours and backfill within 6 hours at inspection on November 9 around 13:48 UTC. No in-progress run was returned. Backfill job 129146918397 steps and logs were inspected: 564 downloaded this run; archive publication, rebuild and checkpoint steps concluded success, but logs warned retained retry/error records require review. These existing runs predate this patch. Browser-level deployed-data verification remains outstanding.

## Measured incomplete coverage and errors
status.json updated 2026-11-09T12:04:50.212245+00:00: 993,066 catalogued, 6,260 archived, 986,806 pending; 11 download failures, 3 normalization failures. archive_bytes=442710114; git_raw_bytes=0; storage_blocked=false. Catalogue presence does not establish document download or calculated history completion.

Decoded current archive_state evidence:
- Eight HTTP Error 503: Service Unavailable records: 0001084380-25-000254, 0001193125-25-252365, 0001378872-25-000322, 0001907480-25-000007, 0000894189-25-012328, 0000894189-25-012412, 0000894189-25-012562, 0000894189-25-012585. All have retry_after=2026-11-10. Example source: https://www.sec.gov/Archives/edgar/data/1084380/0001084380-25-000254.txt . 503 is service unavailability; no 403/429 was recorded in this inspected state.
- Three oversized-response errors: 0000929638-25-003679, 0000929638-25-003681, 0000929638-25-003682; exact error: Response exceeds configured byte limit; requires larger archive storage. Existing cap is 80,000,000 response bytes. Next implementation: bounded streaming archive, checksum verification and explicit size limits, without increasing Git raw growth.
- Normalization: 0002071691-25-002515 — No supported N-PORT positions (old-report exclusion addressed by pending PR #1); 0000894189-25-011392 and 0000850027-25-000007 — Missing/invalid N-PORT series identifier. Do not fabricate series IDs or adviser/classification mappings.
- Runtime failure counts are unchanged by this PR. Source fundamentals/adviser evidence remains absent, so style and institution orientation remain unknown. Backlog main checkpoint from November 7 is under 72 hours old at inspection; PR #1 includes a November 8 checkpoint awaiting review.

## Next task and blockers
Review/merge PR #1 and this independent circuit-breaker change, preserving both backlog checkpoints. Observe the next existing serialized backfill; confirm source publication/checkpoints survive a future interrupted run before claiming cloud validation. Then implement bounded streaming for oversized originals. Missing series identifiers need verified SEC identity evidence. Full history remains incomplete. No GitHub connection/write or local execution blocker was observed after the documented read fallbacks.
