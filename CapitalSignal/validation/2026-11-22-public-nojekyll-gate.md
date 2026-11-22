# Public static-site `.nojekyll` gate — November 22, 2026

## State inspected

- Source base: `4a1dcfe67aa18afae1e281ac28a5a71d14d9b816`.
- Destination `cstrohwork/aibank_public` is public on `main`; its Pages API and both project-site routes return HTTP 404.
- The reviewed destination tree contains roughly 164,000 already-rendered files but no `.nojekyll` marker.

## Bounded implementation

- Generate an empty `.nojekyll` only inside the reviewed staging tree so branch-based Pages serves the static output directly.
- Record the marker's zero bytes and SHA-256 in `public-site-inventory.json`.
- Fail staged-tree validation if `.nojekyll` is missing or non-empty.
- Preserve the existing exclusions for `CNAME`, raw SEC archives, worker state, source code, workflows, tests, validation evidence and secrets.

## Validation and next gate

- Run focused publisher and staged-tree tests, Python compilation and whitespace validation locally.
- Require full-tree cloud staging to report `nojekyll_ready=true` before merge.
- After publication, independently confirm the destination marker and inventory hash. Destination Pages must still be enabled from `main` `/` without a custom domain before the live validator can run. Do not change the domain, source Pages or repository visibility before that live gate passes.
