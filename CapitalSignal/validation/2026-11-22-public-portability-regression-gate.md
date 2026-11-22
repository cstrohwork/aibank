# Public portability regression gate — November 22, 2026

## State inspected

- Current source base: `10df1283b78b29dc54f0bcdc95edd3a1cd58ff48`.
- Destination publication [bd60680](https://github.com/cstrohwork/aibank_public/commit/bd606806aaddc3a0e00587398f9e80b755caafd9) contains 47,621 staging-rewritten HTML attributes and sampled pages have no root-local attributes.
- Destination metadata still reports `has_pages=false`; source Pages/domain remain unchanged.

## Bounded implementation

- Expanded the pre-publication staged-tree validator to reject root-local HTML `href`, `src`, `poster`, `action`, `formaction` and `srcset` references after staging.
- Added rejection of root-local CSS `url(...)` dependencies.
- Added fail-closed scanning for JavaScript and inline HTML requests through `fetch`, dynamic `import`, `importScripts`, workers and service-worker registration.
- Protocol-relative and external references remain allowed. Existing missing-path, JSON and generated-manifest checks remain unchanged.

## Checks actually executed

- Audited current source JavaScript, CSS and inline HTML: zero root-local `fetch`, worker, import or CSS `url(...)` requests were found.
- Twelve focused publisher, staged-tree and live-deployment tests passed.
- All three validation/publisher modules compiled and whitespace validation passed.
- Regression fixtures prove relative/external references pass while root-local HTML, CSS and code requests fail with explicit counters.

## Next task and blocker

Pass exact-head cloud staging over the complete rendered public tree and merge only if `root_local_references=0` and `root_code_requests=0`. Destination Pages must still be enabled from `main` `/` without a custom domain before live deployment validation or cutover.

## Production follow-up

- Exact-head cloud review [45010411350](https://github.com/cstrohwork/aibank/actions/runs/45010411350) passed over 164,047 allowlisted files / 2,367,136,008 bytes: 22,946 HTML, 4 CSS, 9 JavaScript and 141,089 JSON files; all 141,089 JSON files parsed, 191,031 local references and 30,145 manifest references resolved, with `root_local_references=0`, `root_code_requests=0` and `error_count=0`.
- [PR #45](https://github.com/cstrohwork/aibank/pull/45) merged as [cd9282e](https://github.com/cstrohwork/aibank/commit/cd9282e6e934d5c74276f1be9c3de3068bc4ec29).
- Post-merge publisher [45010946010](https://github.com/cstrohwork/aibank/actions/runs/45010946010) completed successfully; every publish step passed. The reviewed destination tree was unchanged, so the destination correctly remained at [bd60680](https://github.com/cstrohwork/aibank_public/commit/bd606806aaddc3a0e00587398f9e80b755caafd9) rather than receiving a content-identical commit.
- Destination remains public on `main` and still reports `has_pages=false`. No `CNAME`, domain, source Pages, source visibility or NVIDIA data change was made. Enable destination Pages from `main` `/` without a custom domain, then run the committed live validator before any cutover.
