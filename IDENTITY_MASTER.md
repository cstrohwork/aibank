# Capital Signal identity master

Run `python scripts/build_identity_master.py` after refreshing cached 13F, N-PORT, and fundamentals-universe data. Optional `--data-root PATH` and `--output-dir PATH` support isolated builds. No network, dependencies, or estimates are required. Tests: `python -m unittest discover -s tests -p test_identity_master.py`.

The builder writes `CapitalSignal/data/intelligence/identity_master.json` and the compact `identity_status.json`. The current cached build has 6,248 entities, 32,457 validated CUSIP securities, 208 fund-to-registrant relationships, and 1,506 issuer mapping observations. These counts describe the cached dataset, not market-wide completeness.

## Contract

- `entities`: deterministic `cik:0000320193` legal-entity IDs shared across issuer, manager, and registrant roles; `series:S000011998` fund IDs; and `fund:registrant:<CIK>` only when the parser explicitly verified the registrant/series LEI and name identity. Reported name aliases do not create matches.
- `securities`: deterministic `cusip:037833100` IDs with validated CUSIP check digits. Names, share classes, tickers, ISINs and reporting-date observations retain separate values. Different CUSIPs, including multiple classes of the same issuer, remain distinct.
- `security_issuer_observations`: CUSIP-to-issuer CIK evidence from dated fundamentals universe snapshots; source URL, mapping basis, and observation date are retained. Conflicting issuer mappings are quarantined across all snapshots rather than silently resolving to the latest row.
- `relationships`: `registered_under` links between fund and SEC registrant, with report-date/source evidence. Registrant means the filing legal entity, not an assumed adviser, investment manager, parent or ultimate corporate owner.
- `quarantine`: malformed/missing CUSIPs, failed CUSIP check digits, unverified fund identities and invalid legal identifiers are excluded from authoritative mappings and counted by source and identifier.
- `missing_cached_files`: missing indexed holdings files are surfaced, never treated as empty portfolios.

`valid_from` and `valid_to` are intentionally null. They mean **unknown**, not unlimited validity. A current mapping observed on November 10 does not establish issuer identity for a September 30 holding. Reported historical security-name aliases cannot establish historical issuer CIKs. Historical effective identifier dates, corporate-action linkages, adviser relationships and ultimate parent hierarchies need independently verified evidence before production historical joins can use them.

Source-type aggregates in `securities` are discovery metadata. The indexed 13F and N-PORT cache files remain the source of individual filing/accession evidence and ownership amounts. The master makes no ownership attribution, deduplication, or institution-wide AUM assertion.
