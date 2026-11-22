# Public-site staging repair — November 21, 2026

## Verified state before this change

- Source `cstrohwork/aibank` remains public at `4bb803cffa3129e94b6aff2d6f29ce9f784f73c1`.
- Destination `cstrohwork/aibank_public` remains public at `0f2112a0010f1b4ce46b0ccbaef603f64390f7b9` and contains only `README.md`, `index.html`, and `CapitalSignal/index.html` (plus the `CapitalSignal` tree entry). It is not a complete site.
- Publish runs [44920172189](https://github.com/cstrohwork/aibank/actions/runs/44920172189) and [44920178799](https://github.com/cstrohwork/aibank/actions/runs/44920178799) both failed. The destination-only token was present, but the publisher collected 22,949 files and deliberately stopped at its 300-file safety cap. Neither run is treated as a deployment success.
- No `CNAME`, Pages setting, DNS record, repository visibility, or source Pages configuration was changed.

## Bounded implementation

- Replaced per-file GitHub API publication with an exact staged tree and one authenticated Git push to the destination. The workflow credential remains restricted to the destination checkout; the source workflow token stays read-only.
- Added explicit page roots for daily, weekly, spotlight, ownership, fundamentals, model, Skunkworks, Worker Dashboard, tools, Ownership Atlas, and subscriptions.
- Added narrowly scoped public JSON rules for browser-consumed normalized 13F, Atlas, fundamentals model, ownership, Skunkworks catalog, and generated investor/fund profile outputs.
- Explicitly excludes `CNAME`, raw SEC archives, history worker state, scripts, tests, workflows, validation evidence, credentials, and other unreviewed data.
- Added high-confidence credential scanning, per-file/total/file-count bounds, required-page checks, SHA-256 inventory output, sparse source checkout, and exact destination synchronization. A destination `CNAME`, if manually added during a later approved cutover, is preserved but is never staged here.
- Pull requests run the complete collection/audit/staging checks without access to or writes with the destination token. Only main pushes or manual runs may publish.

## Checks actually executed in this work session

- `python3 -m unittest tests/test_sync_public_site.py` — 3 tests passed.
- `python3 -m py_compile scripts/sync_public_site.py` — passed.
- PyYAML parse and assertion of the 30-minute workflow timeout — passed.
- `git diff --check` — passed.
- A Ruby YAML validation attempt was unavailable because Ruby is not installed locally; it was replaced by the successful PyYAML validation above.

## Remaining gates and next task

This checkpoint precedes pull-request cloud execution and destination publication. Next, obtain an exact-head cloud staging pass, merge only if current main remains compatible, then inspect the destination commit and file inventory. Enable/test destination Pages without a custom domain, run link/content checks, and only after those pass plan the separate `CNAME`/Pages cutover. Do not make the source private or resume NVIDIA issue #40 until migration and cutover are verified.

### Exact-head cloud correction

[Run 44965004279](https://github.com/cstrohwork/aibank/actions/runs/44965004279) completed sparse checkout and all three unit tests, then measured 162,229 explicitly allowlisted files and stopped at the initial 75,000-file bound. No destination write steps ran. The count is driven by generated public investor/fund profile pages and their versioned public JSON dependencies, not raw SEC archives or worker state. Raised the bounded file ceiling to 200,000 while retaining the 2 GB aggregate limit, 25 MB per-file limit, exact path rules, secret scan, and SHA-256 inventory. A replacement exact-head run is required; the failed run is not a deployment success.

[Replacement run 44965391469](https://github.com/cstrohwork/aibank/actions/runs/44965391469) again passed sparse checkout and all unit tests, measured the complete reviewed tree at 2,295,635,565 bytes, and failed closed at the 2 GB aggregate bound before any destination write. Raised the aggregate ceiling to 3 GB, approximately 30% measured headroom. The 200,000-file, 25 MB per-file, exact path, secret scan, inventory and domain exclusions remain unchanged. A further exact-head pass is required.
