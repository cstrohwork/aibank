# SEC workflow budget regression guard — November 15, 2026

## Purpose

Protect the repaired historical-worker runtime contract from regression. The bounded acquisition budget is only one part of the job: tests, recovery, release publication, derived history/profile builds, rebasing, checkpoint pushes, summaries and cleanup need separate headroom.

The test derives the minimum permitted job timeout from the configured `SEC_HISTORY_SECONDS` value and requires at least 15 additional minutes. It does not hard-code the current 1,200-second budget as the only valid future budget.

A second test protects the serialized/recovery invariants:

- `sec-edgar-cache` concurrency group
- `cancel-in-progress: false`
- unconditional recovery paths
- immediate continuation through `sec_worker_control.py continue`
- recovery-workflow dispatch after every run outcome

## Validation executed

- New workflow-budget tests plus worker stability and parallel recovery suites: 23 passed.
- Full repository suite including the new tests: 212 passed.
- New test module compiled.
- `git diff --check` passed.

## Scope and non-claims

This is a preventive regression test. It does not download SEC filings, alter worker scope, extend the acquisition budget, classify unknown holdings, or prove the currently running production backfill completed. Production completeness still depends on committed status counters and actual run conclusions.


## Cloud failure and correction

Exact-head cloud health [43783333699](https://github.com/cstrohwork/aibank/actions/runs/43783333699) failed during the Python regression suite. The new test correctly detected that the previous contents-API edit had written literal `\n` characters inside a YAML comment, leaving the intended `timeout-minutes: 45` text commented out. The production run [43777908896](https://github.com/cstrohwork/aibank/actions/runs/43777908896) completed successfully, but it used GitHub's default job timeout rather than the intended explicit 45-minute setting; it is not proof of the exact bounded limit.

The workflow is corrected on the same review branch with real line breaks. The regression test now protects both the presence and the budget relationship of the active timeout setting. A new exact-head cloud result is required before merge.
