# Destination project-Pages path portability — November 22, 2026

## State inspected

- Current source base: `e9d03283a082a591720c4649dac0907846bb29ea`.
- Destination remains public commit [c025be6](https://github.com/cstrohwork/aibank_public/commit/c025be69a21c002548e2d5f1c066ca3e340d5309), with repository metadata `has_pages=false`.
- GitHub's documented custom-workflow bootstrap requires Pages to be enabled first. `actions/configure-pages` automatic enablement requires a token other than `GITHUB_TOKEN`; for a GitHub App it requires both `administration:write` and `pages:write`. The existing destination token remains contents-only and was not broadened.

## Defect and bounded implementation

- Audited the allowlisted HTML and found 47,614 absolute-root `href`, `src` or form-action references across 9,517 files. These preserve the current custom-domain paths but would resolve outside the temporary `/aibank_public/` project path, preventing a meaningful pre-cutover browser test.
- The public staging layer now converts only quoted, root-local HTML `href`, `src`, `action`, `formaction` and `poster` attributes to document-relative paths. Protocol-relative and fully qualified external URLs are unchanged. Query strings, fragments and trailing directory slashes are preserved.
- Source files and current source Pages are unchanged. Destination-relative links work under both the project-Pages prefix and the eventual custom-domain root.
- The destination inventory hashes and byte counts are calculated from the rendered portable bytes, so the live validator continues to compare the deployed response with the exact reviewed output.

## Checks actually executed

- Eleven focused publisher, staged-tree and live-deployment tests passed.
- All three modules compiled and whitespace validation passed.
- Added regression coverage for nested pages, root home links, Capital Signal section links with query/fragment, protocol-relative assets, external canonical URLs and rendered inventory hashes.

## Next task and blocker

Pass exact-head cloud staging over the complete allowlisted tree and verify the reported rewrite count, then merge and confirm the destination publication commit. Destination Pages administration remains a user-side blocker; after enabling `main` `/` without a custom domain, run the live validator before any `CNAME`, DNS, source Pages or visibility change.
