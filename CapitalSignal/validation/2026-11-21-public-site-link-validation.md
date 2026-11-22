# Public-site link and content validation — November 21, 2026

## State inspected

- Current source base: `98202784cf875cca86f93dc5b011a5921546222b`.
- Destination publication remains [2eb7d5c](https://github.com/cstrohwork/aibank_public/commit/2eb7d5cc18bd8396ef46ae38a55879e644c5bc1c).
- Raw destination metadata still reports `has_pages=false`; no live destination deployment or cutover is claimed.
- Source remains public with Pages enabled. No `CNAME`, DNS, Pages setting, repository visibility, SEC ingestion, or worker state was changed.

## Bounded implementation

- Added deterministic validation of all staged HTML `href`, `src`, `srcset`, `poster`, and form-action references plus CSS `url(...)` dependencies. Absolute paths are checked against the future custom-domain root; relative paths are normalized without allowing traversal outside the staged tree. External URLs remain a post-Pages network test.
- Added UTF-8/JSON parsing across the staged JSON output and explicit existence checks for the public Atlas, 13F, fundamentals/model and Skunkworks manifests.
- Added cross-reference checks for every Atlas period file, manager 13F index file, and model-company data file named by its published manifest.
- Integrated the validator after allowlisted staging and before destination authentication/write. A broken public tree therefore fails before any destination mutation. Pull-request runs continue without destination credentials.

## Checks actually executed before publication

- `python3 -m unittest tests/test_sync_public_site.py tests/test_validate_public_site.py` — six tests passed.
- `python3 -m py_compile scripts/sync_public_site.py scripts/validate_public_site.py` — passed.
- Workflow YAML parse and 30-minute timeout assertion — passed.
- `git diff --check` — passed.

The first local validator test correctly exposed an inaccurate reference-count assertion (external links were counted as local). The implementation was corrected to count only resolved local references; the complete six-test suite then passed. Exact-head validation over the complete staged site is pending and is not claimed here.

## Next task and blocker

Pass exact-head cloud validation over all 162,229 reviewed outputs and merge only if the full tree has zero local-link, JSON or manifest-reference errors. Destination Pages still requires user-side repository administration: enable Pages for `cstrohwork/aibank_public` from `main` `/` without setting a custom domain. Then run live HTTP, redirects, MIME, asset, JSON and external-link checks before any domain or visibility change.

## Exact-head and destination verification — November 22, 2026

- Exact-head pull-request validation [44996176828](https://github.com/cstrohwork/aibank/actions/runs/44996176828) completed successfully at head `08dd85d9054e357a7056ca25bec9bf3ae003c842`.
- [PR #42](https://github.com/cstrohwork/aibank/pull/42) merged as [bc212ea](https://github.com/cstrohwork/aibank/commit/bc212eaa4cd43ef7c000d80941512ae75bdba44d).
- Main publication [44996966602](https://github.com/cstrohwork/aibank/actions/runs/44996966602) completed successfully and wrote destination [c025be6](https://github.com/cstrohwork/aibank_public/commit/c025be69a21c002548e2d5f1c066ca3e340d5309).
- Independent tree-only destination clone confirmed 164,048 paths, zero forbidden source/workflow/test/validation/history-worker-state/CNAME paths, and all ten sampled required pages/manifests present.
- The destination currently contains zero `CapitalSignal/ownership/data/*.json` files. NVIDIA issue #40 therefore remains incomplete and no live ownership-data deployment is claimed.
- Destination repository metadata still reports `has_pages=false`. Enable Pages from `main` root without a custom domain, then run live HTTP, MIME, redirect, asset, JSON and external-link validation. Do not move `CNAME`, disable source Pages, or make source private before that gate passes.
