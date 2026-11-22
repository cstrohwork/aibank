# Public destination Pages enablement runbook

Last verified: 2026-11-22 07:54 EST

## Purpose

Enable the already-reviewed static tree in `cstrohwork/aibank_public` for temporary project-path validation at `https://cstrohwork.github.io/aibank_public/`. This is a pre-cutover gate only. It must not move `www.ainvestmentbank.ai`, add a `CNAME`, disable source Pages, or change either repository's visibility.

## Verified preconditions

- Source repository: `cstrohwork/aibank`, public.
- Destination repository: `cstrohwork/aibank_public`, public, default branch `main`.
- Reviewed destination commit: `b66c64002654a8cf25002408d23111172cc6ec6c`.
- Destination contains an empty `.nojekyll` recorded in the reviewed SHA-256 inventory.
- Full-tree review passed for 164,048 files / 2,367,136,008 bytes, 141,089 JSON files, 191,031 local references and 30,145 manifest references, with zero validation, root-local URL, or root-code-request errors.
- Raw SEC archives, worker/history state, ingestion source, workflows, tests, validation evidence, credentials, and `CNAME` are excluded.
- Destination Pages API and project URL return HTTP 404; Pages is not enabled.

## Least-privilege enablement

Preferred one-time UI operation:

1. Open destination **Settings → Pages**.
2. Under **Build and deployment**, choose **Deploy from a branch**.
3. Select branch **main** and folder **/(root)**.
4. Save.
5. Leave **Custom domain** empty.

Equivalent REST operation, only when an authenticated token is explicitly available:

```http
POST /repos/cstrohwork/aibank_public/pages
Accept: application/vnd.github+json

{"source":{"branch":"main","path":"/"}}
```

GitHub requires an administrator/maintainer (or the manage-Pages permission). A fine-grained token requires destination-only repository access with **Pages: write** and **Administration: write**. Do not expand the existing publishing token or store a token in the repository merely to perform this one-time setting.

## Required verification before cutover

1. Confirm the Pages API reports source `main` / `/`, no custom domain, and a completed build.
2. Confirm `https://cstrohwork.github.io/aibank_public/` returns the destination content rather than 404.
3. Run **Validate public Pages deployment** in the source repository.
4. Require all 14 critical route SHA-256 and MIME checks to pass.
5. Require all four forbidden internal routes to return HTTP 404.
6. Record the exact workflow run, deployment commit, route counts, and failures in `CapitalSignal/WORKER_BACKLOG.md`.

A scheduled or queued build is not proof of deployment. Any hash, MIME, link, JSON, forbidden-path, or prefix failure blocks cutover.

## Cutover hold

Until every verification above passes:

- do not create or move `CNAME`;
- do not change DNS or the custom domain;
- do not disable source Pages;
- do not make the source private;
- do not resume NVIDIA issue #40 or lower-priority development.

## Current access blocker

At 2026-11-22 07:52 EST, the authorized GitHub connector exposed repository administration but no Pages create/update endpoint. The permitted browser fallback reached GitHub signed out and returned the settings route as 404. No Pages setting changed. User action or a connector/token with the exact destination Pages and Administration write permissions is required.
