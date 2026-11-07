# Capital Signal cloud workers

## Enabled services
- Existing SEC refresh: GitHub Actions `.github/workflows/refresh-sec.yml`, daily 08:17 UTC. Refreshes cached filings and builds derived profiles.
- Cache integrity: `.github/workflows/capitalsignal-health.yml`, daily 09:47 UTC, after the SEC workflow completes, and after changes to its own code/configuration. Read-only worker; validates committed snapshots and saves `worker-health.json` as a 14-day artifact and run summary. Health scope is structural/numeric integrity, not completeness, SEC freshness or full live-site verification.
- Development: enabled ChatGPT scheduled task `Capital Signal development worker`, daily around 08:00 America/New_York, beginning November 8, 2026. Resumes WORKER_BACKLOG.md and implements one validated task per run through existing GitHub connection.
- Monitoring: enabled ChatGPT scheduled task `Capital Signal health monitor`, daily around 10:00 America/New_York, beginning November 8, 2026. Reports material failures/staleness in the setup conversation. Local timezone schedules adjust for daylight saving; GitHub UTC schedules do not.

## State and recovery
Repository source and WORKER_BACKLOG.md are durable state. Every development run must record evidence, next task and blockers there. GitHub jobs are bounded runs, not continuous daemons. Scheduled agent runs depend on the ChatGPT scheduler, available execution tools, connection permissions and account usage limits. Creating the tasks does not establish that a future unattended development run has succeeded. Their first results must be verified.

Open GitHub Actions to inspect logs and artifacts. If a refresh fails, diagnose its failing step before retrying; do not create concurrent ingestion runs. If a development run cannot execute tests or write source, report that actual blocker. Existing paid API access is not required or configured by this setup; do not enable paid services without authorization.

## Setup checkpoint, November 7, 2026
GitHub writes succeeded. First cloud health run 42426204128 executed and uploaded its report. It exposed an overly strict validator rule rejecting legitimate signed N-PORT derivative values; the checker was corrected to allow finite signed N-PORT values while rejecting negative 13F long-position values. Follow-up health run [42426250634](https://github.com/cstrohwork/aibank/actions/runs/42426250634) completed successfully, verifying checkout, validation, artifact publication and summary generation in a GitHub-hosted runner. The ChatGPT development and monitor tasks have not yet completed their first unattended runs.

Latest committed cache observed during setup: 6 indexed 13F snapshots, 9,827 13F holdings rows; 12 N-PORT fund snapshots, 23,454 fund holdings rows; 2 investor profiles; 3 registrant groups. These repository counts supersede earlier unverified larger coverage claims for the deployed cache.
