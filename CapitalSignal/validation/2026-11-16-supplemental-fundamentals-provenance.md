# Supplemental fundamentals provenance correction — November 16, 2026

## Defect

Committed fundamentals status simultaneously reported:

- a verified current large/mega-cap screen outside the ETF proxies with 218 mapped issuers and 216 successful Companyfacts caches; and
- proxy-universe text stating that no separate large/mega-cap screen was available.

The counts and dated source evidence were preserved, but the inherited proxy-universe description was stale and contradictory.

## Implementation

The SPTM/IWV union remains exactly the deduplicated union of current ETF holdings proxies. Its description now states that any separately verified current large/mega-cap screen:

- is stored separately;
- may expand only the Companyfacts acquisition queue;
- is not proxy membership;
- contributes no provider weights;
- is excluded from benchmark matching; and
- is not historical constituent evidence.

No supplemental security is added to `universe.json`, either provider-weight denominator, benchmark matching or a historical classification.

## Validation executed

- Fundamental proxy, union and publication suites: 22 passed.
- Full Python repository suite: 214 passed.
- Ingestion module compiled.
- `git diff --check` passed.

## Production requirement and non-claims

A completed dedicated fundamentals workflow must regenerate `universe.json`, `status.json` and downstream intelligence metadata before the committed contradiction is considered cleared. A scheduled or running workflow is not publication proof.

The current supplemental snapshot remains a current Nasdaq screener observation dated November 12, 2026, retrieved November 15, and not official index membership or evidence before retrieval. No market capitalization is inferred from ticker or issuer size.
