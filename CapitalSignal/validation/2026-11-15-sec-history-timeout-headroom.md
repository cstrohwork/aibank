# SEC history timeout-headroom validation — November 15, 2026

## Observed production evidence

The historical worker is serialized by the `sec-edgar-cache` concurrency group with `cancel-in-progress: false`; the cancellations were therefore not caused by a newer backfill replacing an active one.

Recent workflow runs ended about 32.5 minutes after creation while the job limit was 30 minutes:

- [43765416582](https://github.com/cstrohwork/aibank/actions/runs/43765416582): created 21:45:13Z, updated 22:17:20Z; workflow conclusion `cancelled` after productive steps completed.
- [43768430459](https://github.com/cstrohwork/aibank/actions/runs/43768430459): created 22:17:13Z, updated 22:49:59Z; source acquisition failed closed, but recovery, publication, rebuild and persistence completed before the workflow was labelled `cancelled`.
- [43771453006](https://github.com/cstrohwork/aibank/actions/runs/43771453006): created 22:49:53Z, updated 23:22:33Z; all listed workflow steps completed successfully, but the workflow conclusion was `cancelled`.

The bounded SEC acquisition budget remains 1,200 seconds. Tests, artifact/release publication, derived rebuilding, rebase/push, summaries and cleanup require additional time. The job timeout is raised from 30 to 45 minutes; acquisition scope, worker count and SEC request behavior are unchanged.

## Safeguards retained

- concurrency group: `sec-edgar-cache`
- `cancel-in-progress: false`
- acquisition budget: `SEC_HISTORY_SECONDS=1200`
- three parallel download workers
- active/queued-run duplicate guard in `sec_worker_control.py`
- recoverable artifact and release publication steps
- SEC retry/cooldown, provenance and unknown-normalization behavior

## Validation executed

- PyYAML parse plus structural assertions for the 45-minute timeout, serialized concurrency and unchanged 1,200-second acquisition budget: passed.
- Focused SEC history, recovery, stability, parallel recovery and access tests: 59 passed.
- Full repository suite: 210 passed.
- `scripts/sec_worker_control.py`, `scripts/sec_history.py` and `scripts/rebuild_history.py` compiled.
- `git diff --check` passed for the workflow change.

## Non-claims

The timeout change does not prove a future backfill will succeed, does not expand historical coverage, and does not convert catalogued filings into downloaded or normalized records. Production confirmation requires a run to complete under the new limit and publish a later status checkpoint.
