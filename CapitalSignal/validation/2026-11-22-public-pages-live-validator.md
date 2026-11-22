# Public Pages live-deployment validator — November 22, 2026

## State inspected

- Source base: `3a607ef49372c1fdd74e57d58ff52cd0fea639c9`.
- Reviewed destination publication: [c025be6](https://github.com/cstrohwork/aibank_public/commit/c025be69a21c002548e2d5f1c066ca3e340d5309).
- Destination metadata reports `has_pages=false`. Source Pages, `CNAME`, DNS and repository visibility remain unchanged.

## Bounded implementation

- Added a credential-free, manual live-deployment validator for the future destination Pages URL.
- It reads the public destination's reviewed SHA-256 inventory, requires proof that `CNAME` and raw SEC archives are excluded, and checks 14 critical pages/data routes byte-for-byte against that inventory.
- It checks expected MIME types and requires HTTP 404 for `CNAME`, the worker backlog, history worker status and publisher source.
- The workflow has read-only repository permission, a ten-minute bound, no secrets, serialized validation and a 14-day evidence artifact.

## Checks actually executed

- `python3 -m unittest tests/test_validate_public_deployment.py tests/test_sync_public_site.py tests/test_validate_public_site.py` — ten tests passed.
- All three publisher/validator modules compiled.
- Workflow YAML parsed; `permissions: contents: read` and the ten-minute job bound were asserted.
- `git diff --check` passed.
- A real probe of `https://cstrohwork.github.io/aibank_public/` read the destination inventory (164,047 reviewed files; 2,366,821,289 bytes) and failed as expected because all 14 critical routes returned HTTP 404. All four forbidden paths also returned 404. This is evidence that repository publication exists but Pages is not deployed; it is not relabeled success.

## Next task and exact blocker

Enable Pages on `cstrohwork/aibank_public` from `main` `/` with no custom domain, then run the new workflow and require a real pass before planning `CNAME`/DNS cutover. The authorized connector exposes no Pages-administration write operation. Do not disable source Pages, move the domain, make the source private or resume NVIDIA issue #40 before the live gate passes.
