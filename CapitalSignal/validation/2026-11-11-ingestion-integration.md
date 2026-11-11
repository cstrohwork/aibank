# Ingestion integration validation — November 11, 2026

Pinned base: https://github.com/cstrohwork/aibank/commit/f65dfc2970173fd2116c9246871a46b1e3e930a7

## Bounded implementation
Integrate the three already implemented open ingestion fixes into current main on an isolated branch. This is the pending integration task recorded by PR #3, not a reimplementation. Apply N-PORT report cutoff before position/identity checks; stop and persist evidence on HTTP 403/429/503 even after progress; stream original submissions to atomic bounded gzip archives with original SHA-256 and explicit normalization gaps. Preserve all prior reports/checkpoints.

Source PR heads:
- #1: 9f8397ac34aa4735c2fe64f3bf2ba4d6f96d4df5
- #2: e768fee1723e8f3cbe142a72070b19117ac548bd
- #3: 8df30b6e07e1e5f8fda700b174638d6b1595e1ad

Integration-specific work adapts access fixtures from fetch() to urllib streaming transport and adds test_ingestion_integration.py. The combined test exercises actual local streaming, old-report exclusion, partial progress followed by 503, retained retry evidence, simulated release asset upload verification, staging cleanup and checksum-verified original recovery. No source identities, holdings, classification values or runtime counters are invented.

## Checks actually executed
- Authorized GitHub reads: backlog first, all recursive tree paths (no AGENTS.md), SEC_HISTORY.md, workflows, pinned source/tests, all open PRs and their diffs, current status, base64 archive state, workflow run state. All fetched sources stored freshly for this run.
- Baseline: python -m unittest discover -s tests -v — 11 passed, exit 0.
- Direct git apply of the second and third patches encountered overlapping EOF context. Substantive patch application plus a three-way local merge resolved the integration without conflict markers. An initial incomplete combination failed, as expected; it is not a passing result.
- An unadapted access fixture intercepted fetch() while the streaming path used urllib, reaching the real request path; that test was interrupted (exit 130). No live SEC ingestion success or resulting publication is claimed. Fixtures were corrected to intercept urlopen; final validation uses local/mocked responses.
- Adapted combined suite — 26 passed, exit 0.
- Final suite: python -m unittest discover -s tests -v — 27 passed, exit 0, Python 3.12.14. Output: 2026-11-11-integration-tests.txt.
- git diff --check — exit 0 after redundant EOF whitespace removal.
- Final tests include all original history tests, cutoff cases, 403/429/503 with/without prior progress, accession-specific 404 continuation, generated 81 MB source streaming, size/deadline/truncation/connection cleanup, failed publication preservation, large-holdings deferral and the combined publication test.
- Main and all three PR heads were re-read unchanged immediately before preparing publication; in-progress workflow query returned no runs.
- No production workflow dispatch, live release upload, data refresh, main-branch mutation, or deployment was performed. Tests simulate GitHub release responses. Existing workflows use Python 3.11; this run tested 3.12.14 locally, so actual cloud-version validation remains pending.

## Observed workflow state
All were completed with conclusion success, and predate this patch:
- Refresh: https://github.com/cstrohwork/aibank/actions/runs/42854266039 — updated November 10, 16:26:04 UTC.
- Backfill: https://github.com/cstrohwork/aibank/actions/runs/42985194865 — updated November 11, 08:21:52 UTC.
- Health: https://github.com/cstrohwork/aibank/actions/runs/42986441075 — updated November 11, 08:22:12 UTC.
- Pages: https://github.com/cstrohwork/aibank/actions/runs/42986429653 — updated November 11, 08:23:06 UTC.

## Coverage, exact blockers and next task
Pinned status updated 2026-11-11T08:21:12.039409+00:00: 996,473 catalogued; 8,675 archived; 987,798 pending; 16 download failures; seven normalization failures; zero index errors; storage_blocked=false; git_raw_bytes=0. Catalogue membership does not establish downloaded history or complete calculations.

Decoded archive state (7fd8c88927ed175de6d2e535f25060e88ba68d4e) confirms seven oversized submissions, nine HTTP 503s, six missing series identifiers and the old-report error addressed by PR #1. Exact accession, source, error, retry, and checksum/release metadata are preserved in 2026-11-11-retained-errors.json. All failed downloads have retry_after=2026-11-12.

Review this integrated PR instead of independently merging the three overlapping backlog edits; reconcile original PRs after acceptance. Then observe the existing serialized backfill, verify original publication/recovery and old-report reparse, and measure actual retry outcomes. Oversized submissions remain subject to bounded storage/time/512 MB raw limits, and holdings normalization remains deferred above 80 MB. Missing series IDs require authoritative SEC identity evidence. Style, institution-wide active/passive weights, adviser attribution, complete historical coverage and browser-level refreshed-data verification remain incomplete.
