# Market-input source-audit dependency repair — November 15, 2026

## Observed production evidence

Post-fundamentals intelligence run [43770504124](https://github.com/cstrohwork/aibank/actions/runs/43770504124) completed and published commit [724220b](https://github.com/cstrohwork/aibank/commit/724220b5f55355577abf26444d9969d801d5e24d). Its committed market-readiness output reports 2,592 current ETF-proxy securities, 2,557 cached issuers with dated share facts, and zero verified prices, class market caps, float denominators or liquidity calculations. Issuer XBRL share facts remain deliberately unassigned to security classes without corroboration.

The acquisition cache recorded `ModuleNotFoundError: No module named 'openpyxl'` while attempting to inspect the dated SPTM holdings provider schema. This is an execution dependency failure, not missing-provider evidence. Separately, Stooq returned a public HTTP-200 browser-challenge document, retained zero observations and established a 24-hour source cooldown. The challenged response remains quarantined and is not treated as a price success.

## Bounded correction

The intelligence workflow now installs pinned `openpyxl==3.1.5` before running any tests or market-evidence acquisition. The existing serialized `capitalsignal-intelligence` concurrency group and `cancel-in-progress: false` setting are unchanged. No source acceptance rule changed: prices still require verified unadjusted-close and unadjusted-share-volume bases, dated availability and USD currency; market capitalization still requires share-class outstanding shares; float and liquidity still require their own denominators and complete corporate-action coverage.

## Checks actually executed

- Workflow YAML parsed successfully.
- Structural assertions confirmed the pinned dependency precedes `market_inputs.py --acquire` and serialized concurrency remains enabled.
- `python -m unittest -v tests.test_market_inputs`: 13 passed.
- `python -m unittest discover -s tests -v`: 215 passed.
- `python -m py_compile scripts/market_inputs.py`: passed.
- `git diff --check`: passed.

## Non-claims and next verification

This change restores the provider-file schema audit only. It does not resolve Stooq's browser challenge and does not produce verified prices, market caps, float ownership or liquidity. A completed post-merge intelligence run must be read back before the source check is called repaired. Production styles remain unknown/null until point-in-time benchmark and market-factor gates pass.
