# Capital Signal health workflow timeout headroom — November 15, 2026

## Production evidence

The corrected PR-head health run [43800891934](https://github.com/cstrohwork/aibank/actions/runs/43800891934) was created and marked started at `2026-11-16T03:54:28Z`, then completed at `2026-11-16T04:03:19Z`. During observation, checkout consumed most of the former five-minute job limit before the Python, Node, data-health and artifact steps could run.

The job timeout is raised from five to ten minutes. This remains bounded and changes no ingestion, calculation, provenance or classification policy.

## Safeguards retained

- serialized `capitalsignal-health` concurrency
- `cancel-in-progress: false`
- complete Python regression discovery
- ownership visualization Node tests
- committed-data validation
- health artifact required with `if-no-files-found: error`
- validation/report/summary steps retained on failure paths

## Validation executed

- Health, SEC workflow-budget and worker-stability tests: 12 passed.
- Full Python repository suite: 214 passed.
- Ownership visualization Node suite: four passed.
- New test module compiled.
- `git diff --check` passed.

The first local Node attempt exposed a stale scratch checkout missing `CapitalSignal/atlas/atlas-core.js`. The current-main source file was retrieved solely for local validation; the subsequent four-test result above passed. No generated or synthetic data was added.

## Non-claims

This change does not certify data completeness, SEC availability, Pages deployment or portfolio classification readiness. A completed exact-head cloud health run is required before merge.
