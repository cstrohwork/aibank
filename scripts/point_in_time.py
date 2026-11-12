#!/usr/bin/env python3
"""Conservative selection of immutable filing versions; no intraday dates invented."""
from __future__ import annotations
import datetime as dt


def chronology(record):
    """Keep economic, filing, public-availability and ingestion dates separate."""
    return {
        'report_date': record.get('report_date'),
        'filed_date': record.get('filing_date') or record.get('filed_date'),
        'accepted_at': record.get('accepted_at') or record.get('acceptance_datetime'),
        'public_available_at': record.get('public_available_at') or record.get('available_at'),
        'public_observed_at': record.get('public_observed_at'),
        'ingested_at': record.get('ingested_at') or record.get('retrieved_at'),
        'date_precision': 'day' if record.get('filing_date') or record.get('filed_date') else 'unknown',
    }


def temporal_error(record):
    """Return malformed or timezone-ambiguous temporal evidence, never guess a zone."""
    for key, value in chronology(record).items():
        if key == 'date_precision' or value is None:
            continue
        try:
            if not isinstance(value, str):
                raise ValueError('expected ISO string')
            if len(value) == 10:
                dt.date.fromisoformat(value)
            else:
                parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
                if parsed.tzinfo is None:
                    raise ValueError('timestamp has no timezone')
        except (ValueError, TypeError):
            return key + ': invalid ISO date or timezone-aware timestamp'
    return None


def available_by(record, as_of=None):
    if temporal_error(record):
        return False
    if as_of is None:
        return True
    dates = chronology(record)
    if dates['report_date'] and dates['report_date'] > as_of[:10]:
        return False
    available = dates['public_available_at'] or dates['public_observed_at']
    if available:
        if len(as_of) == 10:
            return available[:10] <= as_of
        if len(available) == 10:
            # Day precision cannot establish availability earlier that same day.
            return available < as_of[:10]
        return dt.datetime.fromisoformat(available.replace('Z', '+00:00')) <= dt.datetime.fromisoformat(as_of.replace('Z', '+00:00'))
    # Public 13F filing dates support end-of-day (not intraday) reconstruction.
    # N-PORT filing dates do not establish when a delayed-publication filing became public.
    if record.get('form', '').startswith('13F-HR') and dates['filed_date']:
        return dates['filed_date'] <= as_of if len(as_of) == 10 else dates['filed_date'] < as_of[:10]
    return False


def select_versions(records, as_of=None):
    """Select one entity/period's base/restatement plus subsequent new-holdings amendments.

    Unknown amendment semantics, missing base, and ambiguous same-day ordering fail closed.
    NEW HOLDINGS entries remain separate rows; identical security keys are not overwritten.
    """
    records = list(records)
    errors = [{'accession': r.get('accession'), 'reason': temporal_error(r)} for r in records if temporal_error(r)]
    if errors:
        return {'status': 'blocked_invalid_temporal_evidence', 'holdings': [], 'selected_accessions': [], 'errors': errors}
    records = [r for r in records if available_by(r, as_of)]
    by_accession = {}
    for r in records:
        accession = r.get('accession')
        if not accession:
            continue
        if accession in by_accession and by_accession[accession].get('holdings') != r.get('holdings'):
            return {'status': 'blocked_conflicting_accession', 'holdings': [], 'selected_accessions': []}
        by_accession[accession] = r
    records = sorted(by_accession.values(), key=lambda r: (r.get('filing_date') or r.get('filed_date') or '', r.get('accepted_at') or '', r['accession']))
    if not records:
        return {'status': 'unavailable', 'holdings': [], 'selected_accessions': []}
    # Accession numbers are identifiers, not proof of ordering within a filing day.
    for left, right in zip(records, records[1:]):
        if chronology(left)['filed_date'] == chronology(right)['filed_date'] and not (left.get('accepted_at') and right.get('accepted_at')):
            return {'status': 'blocked_same_day_order', 'holdings': [], 'selected_accessions': []}
    selected = []
    for record in records:
        form = record.get('form', '')
        amendment = str(record.get('amendment_type', '')).upper().strip()
        is_amendment = form.endswith('/A') or bool(amendment)
        if not is_amendment or amendment == 'RESTATEMENT' or form == 'NPORT-P/A':
            selected = [record]
        elif amendment == 'NEW HOLDINGS':
            if not selected:
                return {'status': 'blocked_missing_base', 'holdings': [], 'selected_accessions': []}
            selected.append(record)
        else:
            return {'status': 'blocked_unknown_amendment', 'holdings': [], 'selected_accessions': []}
    return {'status': 'selected', 'holdings': [h for r in selected for h in r.get('holdings', [])],
            'selected_accessions': [r['accession'] for r in selected],
            'versions': [{'accession': r['accession'], 'form': r.get('form'), 'source': r.get('source'), **chronology(r)} for r in selected],
            'base': {k: v for k, v in selected[0].items() if k != 'holdings'},
            'available_version_count': len(records)}
