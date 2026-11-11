# N-PORT report cutoff validation — November 8, 2026

Base inspected: https://github.com/cstrohwork/aibank/commit/108306a41bd3fd0d8f77d1e27788352d403d3f75

## Problem and bounded change
All-form filing-date discovery includes amendments for older report dates. The N-PORT normalizer required supported positions before checking the report date. An archived May 31, 2025 zero-asset amendment therefore raised a holdings error despite being outside the September 30, 2025 holdings window. Read and validate the XML report date first, apply the cutoff, then validate holdings and identifiers for in-scope reports. Original raw submissions and provenance remain unchanged. Missing dates and in-scope missing positions/series remain errors. No identity or classification is inferred.

## Checks actually executed in this chat
- Retrieved source and archive state through the authorized GitHub plugin; the full repository tree contained no AGENTS.md. Applied the user-supplied project instructions.
- Existing baseline: `python -m unittest discover -s tests -v`: 11 passed.
- Before fixing the implementation: `python -m unittest discover -s tests -p test_nport_cutoff.py -v`: six cases, two errors and one failure. The two old-report cases reproduced the holdings-validation defect; the missing-date case demonstrated the old error ordering.
- After fixing: `python -m unittest discover -s tests -v`: all 17 passed, exit 0.
- Downloaded retained release shard and verified its SHA-256, then verified both original submission SHA-256 values against its embedded manifest and repository archive state. Replayed both originals locally with the patched normalizer and September 30, 2025 cutoff:
  - 0002071691-25-002515: returned [] for the 2025-05-31 report; correctly excluded from holdings normalization.
  - 0000894189-25-011392: still raised Missing/invalid N-PORT series identifier; unresolved identity preserved.
- No refresh or backfill was launched. Latest eight observed runs were completed and successful; the in-progress run query was empty. No open PRs existed when work began.

## Public source provenance
Release shard: https://github.com/cstrohwork/aibank/releases/download/sec-history-raw-2026-11-08/sec-202a0700c0d62251a002f9c9.tar

Shard SHA-256: `202a0700c0d62251a002f9c9b29365a6df468efaac8ad7c27b68e625142a6507`

| Accession | SEC complete-submission source | Original SHA-256 |
| --- | --- | --- |
| 0002071691-25-002515 | https://www.sec.gov/Archives/edgar/data/1100663/0002071691-25-002515.txt | e1af86d2ef8063a8e6b40839efd53c70fd836454e70d1cb3c8526e3a2073620d |
| 0000894189-25-011392 | https://www.sec.gov/Archives/edgar/data/2007649/0000894189-25-011392.txt | fbc3b1400ede802b51879de6ad836705a1caafe64114194a6dbab55efec617d8 |

## Observed completed cloud runs (existing, not runs of this patch)
- Refresh: https://github.com/cstrohwork/aibank/actions/runs/42493354266
- Backfill: https://github.com/cstrohwork/aibank/actions/runs/42486674927
- Health: https://github.com/cstrohwork/aibank/actions/runs/42493438391
- Pages deployment: https://github.com/cstrohwork/aibank/actions/runs/42493430787

These conclusions were read from GitHub run state. They do not certify complete coverage or execution/deployment of this patch. Browser-level deployed-data verification was not performed.

## Remaining work and exact blockers
The inspected main status still reports 993,066 catalogued, 3,096 archived, 989,970 pending, three download failures and two normalization failures. This PR does not rewrite runtime data or clear those counters manually. After review/merge, observe the normal serialized backfill reparse and verify the old amendment's error clears before reporting a new failure count. Existing retry logic already revisits normalization errors; a normalizer version bump is unnecessary for this change because previously successful records are unaffected.

One genuine normalization blocker remains: 0000894189-25-011392 has no seriesId in the retained N-PORT XML. Design sourced standalone-registrant identity handling or obtain verified SEC series evidence; do not fabricate an S identifier.

Three source downloads exceeded the existing 80,000,000-byte response limit: 0000929638-25-003679, 0000929638-25-003681, and 0000929638-25-003682. A future bounded task should implement streamed, size-controlled archival with checksum-preserving publication; merely retrying with the same cap cannot resolve them.

The earlier generic scheduled-task failure has no diagnostic details in this conversation. GitHub reads and isolated-branch writes work in this session; this is not evidence that the unattended development worker's execution environment has recovered.
