# Public Pages custom-workflow size gate — November 22, 2026

## Finding

The reviewed destination tree is 2,367,136,008 bytes. GitHub documents a
1 GB limit for published branch-source Pages sites. GitHub separately documents
that a custom Pages workflow may upload a tar artifact under 10 GB. Enabling
`main` `/` as a branch source would therefore leave a known deployment risk.

## Bounded implementation

- Generate one fixed destination-owned `.github/workflows/deploy-pages.yml`.
- Grant only `contents: read`, `pages: write`, and `id-token: write`.
- Use GitHub's `configure-pages@v5`, `upload-pages-artifact@v4`, and
  `deploy-pages@v4` actions.
- Keep `.nojekyll`, the reviewed inventory, all secret/internal-data exclusions,
  and the no-CNAME hold intact.
- Require the configured 3 GB publisher cap to remain below the documented
  10 GB custom-artifact limit.

The workflow contains no credential and cannot broaden the source publisher's
destination-only Contents token. Initial Pages enablement remains a one-time
administrator operation with `build_type: workflow` and no custom domain.

## Validation

- `python3 -m unittest tests/test_sync_public_site.py tests/test_validate_public_site.py tests/test_validate_public_deployment.py`: 15 passed.
- Three publisher/validator modules compiled successfully.
- `git diff --check`: passed.
- Workflow assertions confirmed least-privilege permissions and no CNAME move.

Exact code-head [run 45030164082](https://github.com/cstrohwork/aibank/actions/runs/45030164082)
passed its complete staging gate at `1109d779f700b604dffa2b24c37f8ae829c0ff8e`:

- 164,049 reviewed files / 2,367,136,649 bytes;
- 22,946 HTML, 4 CSS, 9 JavaScript and 141,089/141,089 valid JSON files;
- 191,031 local references and 30,145 manifest references resolved;
- `nojekyll_ready=true`, `pages_workflow_ready=true`;
- zero root-local references, root-code requests or validation errors.

Destination publication and live deployment remain pending. A workflow file in
the destination is not evidence that Pages is enabled or deployed; live success
still requires the committed hash/MIME/forbidden-path validator.
