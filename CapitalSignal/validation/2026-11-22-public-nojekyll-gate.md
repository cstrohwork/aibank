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

## Production follow-up

- Exact-head full-tree staging [45019655062](https://github.com/cstrohwork/aibank/actions/runs/45019655062) passed with 164,048 reviewed files / 2,367,136,008 bytes, 141,089/141,089 valid JSON files, 191,031 resolved local references, 30,145 resolved manifest references, `nojekyll_ready=true`, zero root-local references or code requests, and zero errors.
- [PR #47](https://github.com/cstrohwork/aibank/pull/47) merged as [d2feed3](https://github.com/cstrohwork/aibank/commit/d2feed341d7533e953a360c11ff3c8280fa6ee24).
- Post-merge publisher [45020170547](https://github.com/cstrohwork/aibank/actions/runs/45020170547) completed successfully and wrote destination [b66c640](https://github.com/cstrohwork/aibank_public/commit/b66c64002654a8cf25002408d23111172cc6ec6c).
- Independent readback confirms `.nojekyll` is empty and its inventory entry has zero bytes and SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. The inventory excludes the custom domain and raw SEC archives.
- Destination Pages still returns API and project-route HTTP 404. Enable Pages from `main` `/` without a custom domain, then run the committed live validator before any cutover.
