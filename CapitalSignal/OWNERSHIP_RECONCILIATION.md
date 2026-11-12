# Ownership reconciliation and point-in-time filing selection

Run `python scripts/reconcile_ownership.py` from the repository root. Optional `--as-of YYYY-MM-DD` reconstructs information available by the end of that day; use a timezone-aware ISO timestamp for a stricter intraday cutoff. `--root` selects a different data directory. The command performs no network requests and atomically writes `CapitalSignal/data/intelligence/reconciliation.json`.

## Outputs and integration

The JSON contains `managers` and `funds` as **separate entity/report-period views**. Each row includes reported matched-identifier equity value, excluded-position counts, selected source accessions and source URLs, separate report/filing/acceptance/public-availability/ingestion dates, and version-selection evidence. Different periods are never summed into a current total. The value field deliberately describes matched disclosed equity positions, not total firm AUM.

`potential_overlaps` records only exact same legal-filer CIK, report date, and common security CUSIP candidates. This is insufficient to establish that a fund is contained within a manager's 13F scope. The fields `verified_overlap_value_usd` and `combined_value_usd` remain null. There are no verified containment relationships in the current inputs. Registrant names, similar manager names and common security positions never establish adviser ownership or permit cross-view addition. `unresolved_fund_manager_mappings` is the actual attribution work queue. `blocked_selections` exposes source versions that cannot be safely reconstructed.

The consumer must choose either a manager view or a fund view. It must never sum them, including where a candidate relationship exists. No manager residual is inferred by subtracting the fund sample. Multiple manager entities may also share discretion; the output makes no claim that aggregating all managers yields unique institutionally owned shares. The current reconciliation output is the safety layer for downstream consumers; legacy `fund_firms.json` and ingestion caches are not rewritten by this command.

## Version-selection API

`scripts/point_in_time.py` exposes:

- `chronology(record)` returns distinct economic report, filing, acceptance, public availability and ingestion dates without filling unknown fields with run time.
- `available_by(record, as_of)` enforces explicit public availability where recorded. A public 13F filing date supports day-level reconstruction only; the same day is excluded for intraday queries without a public timestamp. An N-PORT filing date alone does not establish historical public availability. Current-cache runs without a historical cutoff can inspect cached N-PORT records while leaving that availability unknown.
- `select_versions(records, as_of=None)` accepts one entity/report-period's immutable filing versions and returns selected holdings, selected accessions, chronology and a status. Original filings and RESTATEMENT amendments replace prior versions; subsequent NEW HOLDINGS amendments append rows rather than replacing matching CUSIPs. NPORT-P/A is treated as a replacement report. A new-holdings amendment without a base, an unknown amendment type, conflicting copies of one accession, and ambiguous same-day order fail closed. Accession sorting is not treated as proof of intraday sequence.

The loader prefers immutable `history/normalized/{13f,funds}/*.json.gz` accessions and supplements them from current indexed caches. It preserves original immutable source files. The view retains only selected-version lineage; historical variants remain in their accession-addressed source files. This can be called by scheduled intelligence processing after ingestion. Rebuilding derived caches should adopt the same API rather than a last-accession-wins rule.

## Known evidence gaps

The current legacy N-PORT normalized cache does not preserve balance units, so its `balance` cannot safely be interpreted as shares. Legacy fund share counts remain null. New parsing retains actual position-level `balance_units`, `balance_units_description`, and `currency_code`; only SEC `units=NS` permits treating balance as shares. Nested derivative-leg units/currencies cannot fill missing position-level evidence. A mix of known and unknown units keeps the aggregate share count unknown. USD values are accepted only from explicit USD fields; the legacy 13F `value_thousands` field is never multiplied or treated as dollars without `value_usd`. Options and non-share 13F rows, non-equity fund rows, invalid identifiers, and missing/nonfinite USD values are excluded and counted.

As of this implementation, the existing cached files lack ingestion and precise public-availability timestamps. These fields remain null. New direct public fund and 13F downloads now capture `retrieved_at`, `ingested_at`, and `public_observed_at` separately. Observation of a successful public download establishes a conservative availability bound, not the original publication time. Streaming normalization preserves upstream evidence where supplied and never re-dates legacy originals. SEC acceptance/publication timestamps remain unknown without source evidence. The command does not reconstruct those timestamps from file modification time, current run time or an assumed disclosure delay.

Initial generated result: 4,554 manager/report periods; 210 fund/report periods; one potential same-legal-filer overlap; 209 unresolved fund-manager mappings; seven manager/report selections blocked (six ambiguous same-day sequences, one missing original base). These counts describe available cached coverage, not a completed ownership universe.

## Verification

`python -m unittest discover -s tests -p test_point_in_time.py -v`

`python -m unittest discover -s tests -p test_reconcile_ownership.py -v`

The point-in-time and reconciliation tests verify replacement and additive amendments, historical cutoffs, delayed-publication evidence, same-day ordering, conflicting accession rejection, invalid/naive temporal evidence quarantine, explicit null timestamp handling, USD and option handling, unknown N-PORT share units, and non-additive manager/fund views.

Additional verification: `python -m unittest discover -s tests -p test_fund_evidence.py -v` checks actual units/currencies, nested derivative isolation, conservative quantities, fresh-download evidence and legacy timestamp preservation. The existing streaming N-PORT regression suite also passes.
