# S&P 1500 fundamentals ingestion

Priority from November 11, 2026: ingest S&P 1500 fundamentals first; then benchmark matching and portfolio calculations. Tomorrow morning's update is attached to the existing 8 a.m. Eastern development task (November 12); a separate task could not be created because the five-active-task limit was reached.

## Sources and scope
- Current universe: State Street SPTM daily holdings XLSX, explicitly a fund-holdings proxy for S&P Composite 1500, not licensed official or historical index membership. The November 10 file contains 1,506 eligible equity securities matching 1,500 unique SEC CIKs. Cash, money-market positions and CVRs are excluded. Preserve dates and source checksum.
- Identifier mapping: exact unique normalized ticker match against SEC company_tickers; CUSIP comes from SPTM. Current identifiers must not silently establish historical membership. Multiple share classes retain separate security records and share one issuer ingestion.
- SEC Companyfacts: selected standard US-GAAP/DEI concepts with all reported observations, units, accession, period and availability dates. Store gzip per issuer with retrieval time, source URL and original response SHA-256. Extract revenue, net income, equity, assets, liabilities, operating income/cash flow, capex, EPS, shares and dividends. Custom tags/IFRS, non-USD and missing concepts remain explicit gaps.
- Annual observations are not trailing-twelve-month values. Snapshot selectors require filed/end dates at or before measurement date, annual durations for income/cash flow/EPS/dividends, and compatible units. No future restatements. Derived ratios require matching start/end periods.

## Execution
`python scripts/ingest_sp1500_fundamentals.py` resumes fresh issuer caches, retries transient failures, checkpoints each 25 attempts, and stops on SEC 403/429. `--limit 5` supports a real-data smoke pass. Refresh eligibility uses persisted retrieval dates, never checkout file timestamps.

`.github/workflows/sp1500-fundamentals.yml` starts on this implementation push and runs daily at 05:43 UTC. Data writes are limited to `CapitalSignal/data/fundamentals/`, with artifacts even on failure and rebase/retry for concurrent repository updates. The cloud job has a 40-minute ingestion bound and preserves checkpoints for the next run. A completed job does not imply 100% data coverage; inspect status.json.

## Benchmark and portfolio start
`scripts/match_fundamental_portfolios.py` joins eligible 13F ordinary-share holdings by CUSIP, calculates matched value and fundamental coverage, and produces annual net/operating margin diagnostics weighted by position market value. Current-identifier matching is diagnostic only; no historical membership inferred. No style is published. Benchmark diagnostics normalize field coverage over eligible equity weights.

Next: obtain dated historical membership/weights and documented prices/share-class market caps; populate sector data (SPTM currently reports dashes); derive validated TTM and multiyear growth factors; calculate sector-relative percentiles and portfolio factors with the methodology's 70% gate. Forward PEG remains blocked without genuine estimates. Preserve Berkshire editorial labels independently.

## Morning evidence
Read status.json, benchmark_status.json, portfolio_diagnostics.json and the dedicated GitHub Actions run. Report security/issuer/CIK counts, successfully ingested versus pending and failed issuers, field coverage, source dates and actual calculation blockers. Initial local pass downloaded real SEC records and six regression tests passed. Do not claim the full universe complete from the smoke pass.
