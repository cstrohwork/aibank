# Worker stability repair — November 13, 2026 (Eastern)

## Confirmed failures
- Backfill run 43527085112 archived 784 originals, then exhausted transient SEC 503 retries. Publication, rebuild, persistence and recovery dispatch succeeded. Its SEC cooldown expired at 2026-11-13T23:52:09Z.
- Intelligence run 43484159877 crashed at market_inputs.py:291 on a null CUSIP. PR #7 is now merged (c99ff3d); its cloud market acquisition step and regression suite passed. Final rebuild outcome is still pending at this checkpoint.
- Daily refresh shared a one-pending-run concurrency group with continuously chained backfills. The supervisor previously checked only backfill runs; an overdue/cancelled daily refresh could be displaced.

## Repairs
- Supervisor and direct continuation inspect both writers, reserve the daily refresh after 24 hours without a successful refresh, respect queued jobs and SEC cooldowns, and back off repeated failures. The daily refresh timer is owned by the five-minute supervisor rather than competing with its pending slot. Daily completion also wakes the supervisor.
- Every supervisor run retains its recovery decision, source-error counts and next retry time as a 14-day artifact. Storage blocks fail visibly.
- Parallel failures retain the longest Retry-After, independent of completion order.
- Normalization attempts rotate by last-attempt timestamp; 30 poison records can no longer starve later archived sources. Source errors remain visible rather than being silently discarded.
- Failed intelligence runs retain artifacts but cannot publish partially rebuilt production outputs.
- Pull requests changing scripts/tests/workflows run the complete regression and data-health checks on the proposed head.

## Validation executed
174 tests passed locally, including eight new stability cases for daily starvation/cancellation, active-run protection, cooldowns, recovery after failure, fair normalization retries and competing parallel Retry-After values. All workflow YAML files parsed; git diff --check passed. Cloud deployment/recovery of this additional patch is pending at this checkpoint.

## Remaining limitations and next verification
SEC service interruptions remain external failures; resumption is scheduled and cooldown-aware, not guaranteed error-free. At the inspected archive checkpoint: 62,322 archived, 947,310 pending, 2 retained download failures, 61 normalization errors. Replay the entire rotated parser queue and diagnose unresolved source identities/empty holdings/large release shards from checksum-verified originals. Confirm a successful daily refresh, supervisor dispatch, new backfill checkpoint and full intelligence run after this release. No paid services or credentials were added.

## Cloud verification after release
- PR #9 merged as f4cfb94a86867a098c222b1a341858f1dc0a815d.
- Final proposed head health run 43537624969 succeeded: 174 cloud tests and retained cache integrity validation passed. Earlier code-identical regression run 43537527214 also passed.
- Recovery run 43537733021 succeeded and retained its decision artifact. It observed the active backfill and queued daily refresh, returned wait, and avoided duplicate dispatch. Retained report exposes 61 normalization errors and two download failures rather than treating them as resolved.
- Backfill 43537732976 is running and refresh 43537732960 is queued behind it in the shared writer group. Outcomes and a new archived-filing count are not yet verified.
- PR #7 market acquisition regression is cleared in cloud run 43537024444; its complete intelligence rebuild remains running. New intelligence run 43537733003 is queued.
- These checks verify deployed recovery behavior and regressions; they do not certify complete ingestion, removal of SEC outages, or resolution of retained normalization errors.
