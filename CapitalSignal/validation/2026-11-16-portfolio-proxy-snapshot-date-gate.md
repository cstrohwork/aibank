# Portfolio proxy snapshot date gate — November 16, 2026

## Defect

Portfolio diagnostics published one union-wide `proxy_snapshot_as_of` value even though the current SPTM and IWV ETF holdings proxies are separate provider observations. The production snapshots are dated November 12 and November 13, 2026. A union-wide date could therefore misstate the temporal evidence even while the production classification gate remained closed.

## Correction

- Publish every provider snapshot date in `proxy_snapshots_as_of`.
- Publish a common snapshot date only when every provider date is valid and identical.
- Fail closed with `blocked_misaligned_current_proxy_snapshots` when provider dates differ.
- Fail closed when any provider date is missing or invalid.
- Preserve `historical_membership_verified=false`, `historical_benchmark_gate_passed=false`, and `calculated_style=null`.

This does not convert ETF holdings into official index membership and does not authorize benchmark comparison, style classification, or portfolio calculation for historical report dates.

## Validation executed

- 42 focused benchmark, union, publication, and intelligence-health tests passed.
- The first full-suite run correctly exposed an outdated test fixture that supplied only a union-wide date. The fixture was corrected to provide two dated proxy snapshots; no production gate was weakened.
- All 221 Python tests passed after correction.
- Python compilation and `git diff --check` passed.

