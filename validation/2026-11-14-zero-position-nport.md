# SEC-reported zero-position N-PORT observations — November 14, 2026

## Bounded normalization rule

An in-scope N-PORT filing with zero investment-position elements is now retained only when the complete XML provides:

- a source-evidenced fund identity under the existing identity rules;
- a valid reporting period;
- finite reported total assets, total liabilities, and net assets; and
- exactly zero `invstOrSec` / `investmentOrSecurity` elements.

The normalized record contains an empty `holdings` list, `reported_position_count=0`, and `position_coverage=sec_reported_no_investment_positions`. This is not a claim that total assets are equity holdings. Reported total assets remain a separate source field; reported equity exposure and ownership remain zero because no investment positions were reported.

If one or more investment nodes exist but none can be parsed, normalization still fails explicitly. Missing identity, missing period, missing/nonfinite balance facts, malformed XML, and pre-cutoff periods also retain their existing failure/exclusion behavior.

The coverage label is propagated into both direct fund indexes and rebuilt history indexes. The large-file streaming parser now emits the corresponding `parsed_supported_positions` label/count for nonempty schedules so streaming and regular normalized records remain schema-equivalent.

## Retained-original evidence

All eleven current `No supported N-PORT positions` records were extracted from their checksum-addressed repository release shards. Each complete XML contained zero investment-position elements and valid finite balance facts. Patched replay produced eleven empty, explicitly labelled fund observations:

| accession | report date | fund ID | reported total assets | original SHA-256 |
|---|---|---|---:|---|
| `0000908834-26-000457` | 2026-06-30 | `CIK0002103519` | 121843 | `774f01c898722e2000aefe6ff324b39dcb0ba81ec4712d916a70acc7b7de9a83` |
| `0000940400-25-014305` | 2025-10-31 | `S000089295` | 2000025.00 | `8c2fa2dccc6ef92307a4b203b46d37f566b7ad04154458b449d08edc4eb07e7c` |
| `0000940400-26-035918` | 2026-06-30 | `S000045498` | 0.00 | `0584d922bb77a3e78b27174c25bfecd96fada3b45c6c4af87289c2ee469449c1` |
| `0001193125-26-363409` | 2026-06-30 | `S000105751` | 250000.000000000000 | `3e8966ad12603b09ae50540e243a14a1ca059000d3fc359bc78c416838f4a4e6` |
| `0001193125-26-363423` | 2026-06-30 | `S000105755` | 250000.000000000000 | `53494a71ed522213b9ae8499ef40c9bd63f2b1e20155d62dc1acefcc63150788` |
| `0001193125-26-363448` | 2026-06-30 | `S000103189` | 250000.000000000000 | `c652e7bfadd299db3349a580969776210f570fdbd7547e219900d6681258ac04` |
| `0001193125-26-363459` | 2026-06-30 | `S000105758` | 250000.000000000000 | `39af61808a754442a4418a029b58a1e1a23fba7983db73fec36befc7bea8d6d4` |
| `0001398344-26-015953` | 2026-06-30 | `S000069963` | 4613264.92 | `fdf19ec91b2133382cd053863e2fe3b3ae475efea1b6e25d79914e35bda7db5f` |
| `0001398344-26-015961` | 2026-06-30 | `S000097909` | 369447.87 | `b22e8698413d261280499c4233beb4986f73a43a77eccb938b1bc1dc7ff231f2` |
| `0001398344-26-015962` | 2026-06-30 | `S000097910` | 244448.67 | `13617151c7e0ddf929303d08016d1433e3a0af127a28fe2d22789f9af84dc60e` |
| `0001936157-25-000135` | 2025-10-31 | `S000095135` | 0 | `00aba2d384146a899d602c47ecd6479e03bc68477ba8eee05d6a70299efb34de` |

These originals came from six repository release assets dated November 13–15. Asset and original checksums remain enforced by the existing release reader. No source document was modified.

## Validation actually executed

- `python -m unittest tests.test_worker_recovery.StandaloneIdentityTests -v` — 12 passed.
- `python -m unittest tests.test_nport_cutoff.NportCutoffTests -v` — 6 passed.
- `python -m unittest tests.test_stream_nport.StreamingNportTests -v` — 5 passed.
- `python -m unittest discover -s tests -v` — 197 passed in the isolated source tree.
- `python -m py_compile scripts/refresh_funds.py scripts/rebuild_history.py scripts/stream_nport.py` — passed.
- Eleven retained-original replays through `sec_history.normalize` — all eleven produced zero holdings with the explicit coverage label.

During development, the first full-suite run exposed a regular/streaming schema mismatch after adding coverage metadata. The streaming parser was updated, its dedicated regression passed, and the final complete suite passed. This was resolved before publication.

## Incomplete state and next task

The latest inspected production checkpoint predates this patch and still reports 20 normalization failures: nine identity records awaiting replay and eleven zero-position records. No production reduction is claimed until a serialized worker commits a new checkpoint.

Next: pass cloud review and merge safely, then verify that an actual serialized retry clears only the evidence-backed identity and zero-position records. Continue investigating any newly retained errors individually. One all-zero series-LEI placeholder and SEC 503 retries remain explicit blockers unless later source/retry evidence resolves them.
