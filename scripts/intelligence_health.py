#!/usr/bin/env python3
"""Offline intelligence readiness and source-event catalogue; no completeness claims."""
import argparse
import collections
import datetime as dt
import gzip
import heapq
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'CapitalSignal/data'
EVENT_FORMS = {
    'beneficial_ownership_13d': {'SC 13D', 'SC 13D/A', 'SCHEDULE 13D', 'SCHEDULE 13D/A'},
    'beneficial_ownership_13g': {'SC 13G', 'SC 13G/A', 'SCHEDULE 13G', 'SCHEDULE 13G/A'},
    'insider_disclosure': {'3', '3/A', '4', '4/A', '5', '5/A'},
    'proxy_voting': {'N-PX', 'N-PX/A'},
}


def read(path, default, errors):
    try:
        raw = path.read_bytes()
        return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)
    except (OSError, ValueError, EOFError) as exc:
        errors.append({'path': str(path), 'error': str(exc)})
        return default


def age_hours(value, now):
    try:
        stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            return None
        return (now - stamp).total_seconds() / 3600
    except (ValueError, TypeError, AttributeError):
        return None


def file_exists(root, relative):
    if not relative:
        return False
    path = root / relative
    return path.resolve().is_relative_to(root.resolve()) and path.is_file()


def build_events(root, archive, now, limit=500):
    errors = []
    counters = {k: collections.Counter() for k in EVENT_FORMS}
    heaps = {k: [] for k in EVENT_FORMS}
    seen = set()
    for path in sorted((root / 'history/catalogue').glob('*.json.gz')):
        rows = read(path, [], errors)
        for row in rows:
            accession = row.get('accession')
            if not accession or accession in seen:
                continue
            seen.add(accession)
            category = next((k for k, forms in EVENT_FORMS.items() if row.get('form') in forms), None)
            if not category:
                continue
            if not row.get('filing_date') or row['filing_date'] > now.date().isoformat():
                counters[category]['future_or_missing_filing_date'] += 1
                continue
            state = archive.get(accession, {})
            archived = state.get('status') == 'archived'
            normalized = [p for p in state.get('normalized_files', []) if file_exists(root, p)]
            counters[category]['catalogued_filings'] += 1
            counters[category]['archived_filings'] += int(archived)
            counters[category]['normalized_filings'] += bool(normalized)
            event = {k: row.get(k) for k in ('accession', 'cik', 'name', 'form', 'filing_date', 'source')}
            event.update(category=category, evidence_level='filing_metadata_only',
                         archived=archived, normalized_files=normalized,
                         interpretation_status='requires_document_parsing_and_entity_linkage',
                         activist_intent=None, transaction_direction=None, vote_direction=None)
            item = (row['filing_date'], accession, event)
            if limit > 0:
                heapq.heappush(heaps[category], item)
                if len(heaps[category]) > limit:
                    heapq.heappop(heaps[category])
    streams = {}
    events = []
    for category in EVENT_FORMS:
        streams[category] = dict(counters[category])
        streams[category].update(retained_events=len(heaps[category]),
                                 parsed_signal_status='not_implemented',
                                 filing_stream_status='catalogued' if counters[category]['catalogued_filings'] else 'missing')
        events.extend(item[2] for item in heaps[category])
    events.sort(key=lambda e: (e['filing_date'], e['accession']), reverse=True)
    return {'schema_version': 1, 'updated_at': now.isoformat(), 'streams': streams,
            'events': events, 'retention_limit_per_stream': limit,
            'errors': errors, 'scope': 'Existing EDGAR catalogue metadata; latest events retained per stream. Counts cover the full local catalogue, not all SEC filings. Filing types do not establish activist intent, purchases, sales, or voting direction.'}


def build_health(root, now, stale_hours=36):
    errors = []
    fundamentals = read(root / 'fundamentals/status.json', {}, errors)
    universe = read(root / 'fundamentals/universe.json', {}, errors)
    history = read(root / 'history/status.json', {}, errors)
    archive = read(root / 'history/archive_state.json.gz', {}, errors)
    required_ciks = {s['cik'] for s in universe.get('securities', []) if s.get('cik')}
    records, corrupt, freshness = {}, [], {}
    for cik in sorted(required_ciks):
        path = root / 'fundamentals/companyfacts' / (cik + '.json.gz')
        if path.exists():
            record = read(path, {}, errors)
            if record.get('cik') != cik or not isinstance(record.get('fields'), dict):
                corrupt.append(cik)
            else:
                records[cik] = record
                freshness[cik] = age_hours(record.get('retrieved_at'), now)
    missing = sorted(required_ciks - records.keys())
    unmapped = [s.get('ticker') for s in universe.get('securities', []) if not s.get('cik')]
    # Recompute fact coverage from stored observations rather than trusting a successful job/status.
    from ingest_sp1500_fundamentals import snapshot
    coverage = collections.Counter()
    for cik, record in list(records.items()):
        try:
            coverage.update(snapshot(record, universe.get('as_of', now.date().isoformat())).keys())
        except (KeyError, ValueError, TypeError) as exc:
            corrupt.append(cik)
            errors.append({'cik': cik, 'error': 'Invalid fact observations: ' + str(exc)})
    fresh = sum(v is not None and 0 <= v <= stale_hours and cik not in corrupt for cik, v in freshness.items())
    expected = len(required_ciks)
    sources = {}
    for name, status in [('fundamentals', fundamentals), ('history', history)]:
        age = age_hours(status.get('updated_at'), now)
        sources[name] = {'updated_at': status.get('updated_at'), 'age_hours': round(age, 2) if age is not None else None,
                         'freshness': 'unknown' if age is None else 'future_timestamp' if age < 0 else 'stale' if age > stale_hours else 'fresh'}
    ownership = {}
    for folder, key in [('13f', 'managers'), ('funds', 'funds')]:
        index = read(root / folder / 'index.json', {}, errors)
        entries = index.get(key, [])
        absent = [e.get('file') for e in entries if not file_exists(root / folder, e.get('file'))]
        ownership[folder] = {'indexed_snapshots': len(entries), 'cached_snapshots': len(entries)-len(absent),
                            'missing_cached_files': absent, 'source_errors': index.get('errors', []),
                            'latest_report_date': max((e.get('report_date', '') for e in entries), default=None),
                            'all_market_completeness': 'unknown_incomplete_backfill',
                            'expected_snapshots': None,
                            'expected_basis': 'No complete expected manager/fund/report-period manifest; indexed snapshots are not the market denominator.'}
    events = build_events(root, archive, now)
    errors.extend(events['errors'])
    parsed_events = sum(s.get('normalized_filings', 0) for s in events['streams'].values())
    blocking = []
    if any(not o['indexed_snapshots'] or o['missing_cached_files'] or o['source_errors'] for o in ownership.values()):
        blocking.append('ownership_cache_missing_or_source_errors')
    if not expected or missing or corrupt or unmapped:
        blocking.append('fundamentals_universe_not_fully_ingested_and_mapped')
    if fresh < expected:
        blocking.append('fundamentals_records_stale_or_missing')
    if any(s['freshness'] != 'fresh' for s in sources.values()):
        blocking.append('source_status_stale_or_unknown')
    if history.get('pending_filings', 0) or history.get('status') != 'complete':
        blocking.append('historical_filing_archive_incomplete')
    benchmark = read(root / 'fundamentals/benchmark_status.json', {}, errors)
    if benchmark.get('historical_benchmark_status') != 'complete':
        blocking.append('historical_benchmark_unavailable')
    if benchmark.get('style_calculation_status') != 'complete':
        blocking.append('style_inputs_not_complete')
    if errors:
        blocking.append('cache_read_errors')
    pipeline_path = root / 'intelligence/pipeline_status.json'
    pipeline = read(pipeline_path, {}, errors) if pipeline_path.exists() else {}
    pipeline_state = pipeline.get('status')
    # In-progress status is informational: this module runs inside that same pipeline.
    pipeline_observation = {'status': pipeline_state or 'not_observed',
                            'in_progress_is_blocker': False,
                            'failures': pipeline.get('failures', []),
                            'steps': pipeline.get('steps', [])}
    if pipeline_state in ('failed', 'error'):
        blocking.append('previous_pipeline_failed')
    # The model builder owns activation. Health observes its canonical gate only.
    model_path = root / 'fundamentals/model_status.json'
    model_status = read(model_path, {}, errors) if model_path.exists() else {}
    model_fields = ('revenue', 'net_income', 'shares_outstanding')
    model_missing_fields = {field: expected-coverage[field] for field in model_fields}
    model_ready = model_status.get('activation', {}).get('ready') is True
    archive_states = collections.Counter(s.get('status', 'unknown') for s in archive.values())
    parsed_path = root / 'intelligence/parsed_events.json'
    parsed_signals = read(parsed_path, {}, errors) if parsed_path.exists() else {}
    health = {'schema_version': 1, 'checked_at': now.isoformat(),
              'status': 'blocked' if blocking else 'ready', 'blocking_reasons': blocking,
              'job_success_is_data_complete': False, 'sources': sources, 'pipeline': pipeline_observation,
              'fundamentals': {'security_count': len(universe.get('securities', [])), 'expected_mapped_issuers': expected,
                               'valid_cached_issuers': len(records) - len(set(corrupt) & records.keys()), 'fresh_cached_issuers': fresh,
                               'coverage_pct': round(100*len(records)/expected, 4) if expected else None,
                               'missing_issuers': missing, 'corrupt_issuers': corrupt, 'unmapped_securities': unmapped,
                               'field_issuer_coverage': dict(coverage),
                               'field_issuer_coverage_pct': {field: round(100*count/expected, 4) if expected else None for field, count in coverage.items()}, 'reported_ingested_issuers': fundamentals.get('ingested_issuers'),
                               'reported_count_matches_cache': fundamentals.get('ingested_issuers') == len(records),
                               'source_failures': fundamentals.get('failed_attempts', [])},
              'ownership': ownership,
              'history': {**{k: history.get(k) for k in ('catalogued_filings','archived_filings','pending_filings','download_failures','normalization_failures','deferred_filings','storage_blocked','download_interruption')},
                          'cached_archive_state_counts': dict(archive_states),
                          'archived_catalogue_coverage_pct': round(100*history.get('archived_filings', 0)/history['catalogued_filings'], 4) if history.get('catalogued_filings') else None},
              'readiness': {'fundamentals_ingestion_complete': bool(expected and not missing and not corrupt and not unmapped),
                            'model_ready': model_ready, 'model_observed_fields': list(model_fields),
                            'model_missing_field_issuers': model_missing_fields,
                            'model_gate_basis': 'Canonical fundamentals/model_status.json activation.ready; health does not independently authorize model activation.',
                            'model_status_observed': bool(model_status),
                            'production_style_ready': not blocking,
                            'activism_signals_ready': False, 'parsed_event_filing_count': parsed_events},
              'event_streams': events['streams'],
              'parsed_event_signals': {'observed': bool(parsed_signals), 'status': parsed_signals.get('status'),
                                       'summary': parsed_signals.get('summary'),
                                       'activist_intent_inferred': False}, 'errors': errors,
              'limits': ['Fundamental universe is an SPTM ETF holdings proxy, not certified official S&P 1500 membership.',
                         'Fresh ingestion is distinct from the economic age of a reported financial fact.',
                         'No workflow API queried; this report measures committed data and records source-reported failures.',
                         'No automatic publication is authorized by an empty or absent gate.']}
    return health, events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data-root', type=pathlib.Path, default=ROOT)
    ap.add_argument('--as-of', help='Timezone-aware ISO timestamp for reproducible checks')
    ap.add_argument('--stale-hours', type=float, default=36)
    ap.add_argument('--strict', action='store_true', help='Exit 1 when intelligence readiness is blocked')
    args = ap.parse_args()
    now = dt.datetime.fromisoformat(args.as_of.replace('Z', '+00:00')) if args.as_of else dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or args.stale_hours <= 0:
        ap.error('as-of requires a timezone and stale-hours must be positive')
    health, events = build_health(args.data_root, now, args.stale_hours)
    out = args.data_root / 'intelligence'
    out.mkdir(parents=True, exist_ok=True)
    for name, value in [('health', health), ('events', events)]:
        path = out / (name + '.json')
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(value, separators=(',', ':'), allow_nan=False))
        tmp.replace(path)
    print(json.dumps({'status': health['status'], 'fundamentals_coverage_pct': health['fundamentals']['coverage_pct'],
                      'model_ready': health['readiness']['model_ready'], 'blocking_reasons': health['blocking_reasons'],
                      'retained_events': len(events['events'])}))
    return 1 if args.strict and health['status'] != 'ready' else 0


if __name__ == '__main__':
    raise SystemExit(main())
