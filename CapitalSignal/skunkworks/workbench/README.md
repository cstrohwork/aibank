# Insight Workbench

Six production-static experimental workflows at `/CapitalSignal/skunkworks/workbench/`.

| Workflow | User task | Evidence / output |
| --- | --- | --- |
| Issuer briefing | Summarize holders without manually reading every portfolio | CUSIP search, holder commitment, SEC links, Markdown brief, CSV |
| Peer ownership gaps | Find potential research candidates across analyst-chosen peers | Sampled non-holders ranked by peer count then peer weights, SEC sources |
| Meeting preparation | Assemble manager briefing packs | Browser-local shortlist, subject weight, top ten positions, sourced Markdown |
| Watchlist triage | Focus the next research session | Browser-local list, commitment/sparse-coverage prompts, manual baseline comparison |
| Investor comparison | Explain portfolio differences | Shared CUSIPs, weighted overlap, security weight gaps, CSV |
| Filing evidence review | Identify limitations before using an investor record | Newest full manager Atlas period, missing chronology, exclusions, multi-version and duplicate evidence |

The first five workflows read `../../data/atlas/skunkworks-security.json`, refreshed by `build_skunkworks.py` as part of successful Atlas builds. Security names are SEC filing labels, not a verified ticker/issuer master. Coverage is the existing 50 largest-manager candidate sample, with validation exclusions preserved. No institution-wide non-ownership, market ownership percentage, investment intent, active/passive classification or flows are inferred.

Evidence review reads the newest `managers-YYYY-MM-DD.json` selected from the published Atlas manifest. Its date/checkpoint may differ from the sample and is labeled separately. Watchlist changes are manual sample/cache comparisons, not an unattended monitor. localStorage unavailability leaves in-memory functionality intact and shows a warning.

Calculation checks: `node --test tests/insight-workbench.test.cjs tests/skunkworks-core.test.cjs tests/atlas-core.test.cjs`.

## Expansion priorities

1. Extend validated position coverage beyond 50 managers using bounded shards and source-version gates; do not pretend the current sample is the full market.
2. Add historical exact-version security snapshots and corporate-action mapping before attributing position changes to trading.
3. Reuse verified issuer/ticker/sector identities to suggest peers, retaining analyst overrides and an explanation of fit.
4. Add explicit investor mandates, geography and fund-parent attribution for more useful meeting/targeting filters.
5. Add consented account-backed workspaces and event-based watchlist alerts with idempotent delivery after a durable backend is available.
6. Build liquidity/exit-capacity scenarios only when dated ADV, float, price and shares-outstanding evidence meets existing quality gates.

These are future work, not running workers or completed capabilities.
