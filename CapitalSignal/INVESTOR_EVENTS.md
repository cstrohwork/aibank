# Parsed investor filing events

`python scripts/parse_investor_events.py --fetch-release --max-shards 2` scans the SEC archive-state catalogue for Schedule 13D/G (including SC form aliases and amendments) and N-PX. It reads original local gzip bodies or bounded, SHA-256-verified GitHub release shards, then verifies each decompressed submission against its archived SHA-256 before parsing. It never fetches a substitute live filing body.

The CLI fetches up to two verified release shards by default; `--offline` disables retrieval. `--fetch-release` remains an accepted compatibility flag. Successful parsed filings and their records are checkpointed in the existing output and preserved across runs. Each subsequent run prioritizes unresolved accessions, so bounded runs advance through release shards rather than reprocessing the same completed sample. Unsupported documents remain explicit unresolved work. `--limit` defaults to 2,000 candidate archived filings. `--max-shards` defaults to 2, preferring a voting shard and an ownership shard; more shards expand coverage. Each shard download is capped at 100 MB and each decompressed submission at 10 MB. Missing files, oversized sources, checksum errors, and unselected release shards appear explicitly as unavailable. Legacy HTML/text and XML without usable records are unsupported, not silently converted to zero ownership or votes.

Output: `CapitalSignal/data/intelligence/parsed_events.json`.

- `summary`: candidate, selected, parsed, unavailable and unsupported filing counts; ownership record and proxy vote counts; verified release-shard count.
- `filings`: filing metadata, amendment flag, structured document count, extracted record counts and N-PX notice explanation when present.
- `beneficial_ownership`: structured reporting-person names and CIKs when reported; subject issuer, CUSIP, beneficial shares, percent of class, voting power and event date; Item 4 purpose excerpt with a truncation flag when available.
- `proxy_votes`: issuer, CUSIP, meeting date, proposal description/category, direction, record-level shares voted, shares on loan, management recommendation and fund series identifier where supplied. Split votes stay separate.
- Each extracted record preserves accession, source URL, document filename, XML element path and source excerpt. Dates retain their original filing representation; filing date, event date and meeting date are distinct concepts.

No activist intent is inferred from 13D form type or generic purpose wording; `activist_intent` is null. Joint reporting persons can report the same shares, so their amounts must not be summed. Amendments remain separate observations until an independently reviewed amendment reconciliation step resolves supersession. N-PX voting records establish votes, not portfolio ownership. All counts describe cached source coverage rather than the full SEC universe.

Tests: `python -m unittest discover -s tests -p test_investor_events.py`.
