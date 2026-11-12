# Model

The separate `/CapitalSignal/model/` workspace is prepared for automatic activation after the full current universe has valid, fresh fundamental inputs. It is not linked from other pages while blocked. Existing publication navigation and AIBank branding are preserved.

## Build and activation

Run `python scripts/build_model_data.py` after fundamentals ingestion, including failed attempts that saved partial checkpoints. It reads the universe and compressed SEC fact caches without making network requests and writes:

- `CapitalSignal/data/fundamentals/model_status.json`: canonical machine-readable gate and coverage.
- `CapitalSignal/data/fundamentals/model_data.json`: the same gate, lightweight searchable securities and per-company file references.
- `CapitalSignal/data/fundamentals/model_companies/<CIK>.json`: one sourced company history and compatible baseline, loaded only when that company is selected.

`activation.ready` remains false unless the universe is nonempty, every security maps to an issuer, every issuer cache is present and valid, and each issuer has positive USD annual revenue plus reported net income for an identical annual period available by the universe date. Loss-making companies are supported. Every source record and the universe must have a timezone-aware retrieval timestamp within 36 hours; the universe membership date must be within seven days. Missing or unsupported taxonomy data blocks readiness instead of silently exempting issuers. Coverage includes exact pending, unsupported, stale and invalid identifiers. The universe remains explicitly described as an SPTM ETF proxy, not official S&P index membership.

The browser fetches the current status without cache, blocks any manifest older than 36 hours or beyond its earliest source/membership expiry (`expires_at`), and loads the modeling dataset only after the gate succeeds. Status/index/company build timestamps must agree, so a deployment race fails closed. The builder atomically replaces each company object, then the lightweight index, then status last as the commit gate; it does not download the full universe of histories into the browser. The check runs on each page load. The parent workflow must regenerate and publish both files after each ingestion attempt to activate without manual follow-up.

## Modeling behavior

- Company search by ticker or name; historical annual revenue/net income; reported baseline values with filing dates, taxonomy tags and SEC source links.
- Editable annual revenue growth and net margin project five years of revenue and net income.
- Diluted EPS uses a separate explicit EPS growth assumption. It is not inferred from a questionable share-class denominator. EPS projections are unavailable when the baseline does not contain diluted EPS for the identical annual period.
- Free cash flow uses operating cash flow less capital expenditure from that same period. Missing either input leaves FCF unavailable; no missing fact becomes zero. The initial FCF margin is derived from these reported values and remains editable when supported.
- Base/bull/bear scenarios apply visible user growth and margin adjustments. Initial growth (5%), P/E (15x), EV/revenue (2x), growth adjustment (5 percentage points) and margin adjustment (2 percentage points) are explicitly hypothetical user assumptions, not observed market data or consensus.
- Year-five EV/revenue and P/E valuation outputs, plus P/E sensitivity. P/E values require positive EPS. EV is not presented as equity market cap, and no current-price return is inferred.
- CSV export includes source, baseline date, universe date, all assumptions, scenario and annual outputs. Inputs remain in browser session memory.

## Verification

`python -m unittest discover -s tests -p test_model_data.py -v` covers activation, pending/unmapped/stale/invalid inputs, loss companies, incompatible periods, future restatements, non-USD/nonfinite inputs and scenario mathematics. The JavaScript calculation check runs when Node is available. `node --check CapitalSignal/model/model.js` and `node --check CapitalSignal/model/model-core.js` validate syntax.

The prepared site remains blocked against the current six-of-1,500 issuer cache. Full public browser operation must not be claimed until the completion gate passes. Forecasts are scenarios, not investment recommendations.
