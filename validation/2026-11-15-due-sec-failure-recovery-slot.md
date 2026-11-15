# Due SEC failure recovery slot — November 15, 2026

## Production evidence inspected

The committed history checkpoint at `2026-11-15T07:42:23.244186Z` reports 91,290 archived filings, 920,024 pending filings, 74 deferred capacity records, one download failure, zero normalization failures, and `storage_blocked=false`. Current/recent and June 2026 investor intake are complete; the active September 2025 intake window has 14,099 records outstanding.

The single retained failed record is SEC accession `0001493152-26-051754`, CIK `0001722731`, FDCTECH, INC., form 10-Q, filed November 13, 2026. Its preserved public source is `https://www.sec.gov/Archives/edgar/data/1722731/0001493152-26-051754.txt`; its exact error is `HTTP Error 503: Service Unavailable`; its persisted retry time is `2026-11-14T22:21:27.555614Z`. This is a source-access failure, not evidence that the filing was downloaded or normalized.

The serialized backfill run [43691538354](https://github.com/cstrohwork/aibank/actions/runs/43691538354) was already active during inspection. No duplicate ingestion was dispatched.

## Bounded implementation

`select_download_queue` now reserves exactly one early batch slot for a due failed download. This prevents an eligible transient SEC/network failure from starving indefinitely behind every newly discovered non-investor filing. The remaining batch retains the established active investor-period priority and non-investor reservation. A retry cannot monopolize more than one reserved recovery slot.

Legacy configured-size failures are excluded from the early recovery slot: they remain ordinary streaming-capable backlog work. SEC cooldowns remain authoritative because only records already admitted by `retry_due` enter the available queue. Original accession, CIK, form, filing date, source URL, error and retry evidence remain unchanged.

The status checkpoint now publishes `due_failure_recovery_queued` and `failure_recovery_slots` under `investor_ingestion_priority`, so monitoring can distinguish a scheduled recovery attempt from successful download or normalization.

## Validation actually executed

- `python -m unittest tests.test_worker_recovery.RecoveryTests -v` — 9 passed.
- `python -m unittest discover -s tests -v` — 204 passed.
- `python -m py_compile scripts/sec_history.py` — passed.
- `git diff --check` — passed.

The new regression proves an overdue HTTP 503 record receives the first recovery slot while the five-record batch remains bounded and continues active-period investor intake. The existing regression proves legacy size retries still do not displace new priority filings.

## Limits and next task

This change schedules an eligible attempt; it does not claim the SEC source has recovered. Production clearance requires a later committed archive record with `status=archived`, a retained checksum and raw/release storage evidence. If SEC again returns an access error, the existing cooldown and failure evidence remain explicit.

Next: pass cloud review, merge against the current main SHA, then inspect a serialized worker checkpoint for the exact accession. Continue September 2025, December 2025 and March 2026 intake in order. Point-in-time market prices, share-class market capitalizations, float denominators and historical official benchmark constituents/weights remain unavailable. The 2,592-security fundamentals universe remains current SPTM/IWV ETF holdings proxies—not official index membership—and outside-proxy large/mega issuers remain excluded without dated market-cap and U.S.-exchange listing evidence.
