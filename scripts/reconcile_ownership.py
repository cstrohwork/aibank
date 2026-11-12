#!/usr/bin/env python3
"""Publish separate manager/fund holdings views and an evidence-driven overlap queue."""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import gzip
import json
import math
import pathlib
from point_in_time import select_versions, chronology
ROOT = pathlib.Path(__file__).resolve().parents[1] / 'CapitalSignal/data'


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (ValueError, TypeError):
        return None


def aggregate(holdings, fund=False):
    result = collections.defaultdict(lambda: {'shares': 0., 'value_usd': 0., 'position_rows': 0})
    excluded = collections.Counter()
    for h in holdings:
        if fund and h.get('asset_category') not in ('EC', 'EP'):
            excluded['non_equity'] += 1; continue
        if not fund and (h.get('put_call') or h.get('share_type', 'SH') != 'SH'):
            excluded['options_or_non_share_units'] += 1; continue
        cusip = str(h.get('cusip') or '').strip().upper()
        if len(cusip) != 9 or not cusip.isalnum():
            excluded['unresolved_identifier'] += 1; continue
        value = number(h.get('reported_value_usd') if fund else h.get('value_usd'))
        if value is None:
            excluded['missing_or_invalid_dollar_value'] += 1; continue
        row = result[cusip]; row['position_rows'] += 1; row['value_usd'] += value
        shares = number(h.get('balance') if fund else h.get('shares'))
        # SEC NS explicitly means number of shares; legacy missing units stay unknown.
        if (fund and h.get('balance_units') != 'NS') or shares is None:
            row['shares'] = None
        elif row['shares'] is not None:
            row['shares'] += shares
    return dict(result), dict(excluded)


def load_groups(root, kind):
    groups = collections.defaultdict(list)
    seen = set()
    for path in sorted((root/'history/normalized'/kind).glob('*.json.gz')):
        r = json.loads(gzip.decompress(path.read_bytes())); accession = r.get('accession')
        if accession: seen.add(accession)
        entity = r.get('manager_cik') if kind == '13f' else r.get('fund_id') or r.get('series_id')
        if entity and r.get('report_date'): groups[(entity, r['report_date'])].append(r)
    index = json.loads((root/kind/'index.json').read_text())
    for entry in index['managers' if kind == '13f' else 'funds']:
        path = root/kind/entry['file']
        if not path.exists(): continue
        r = dict(entry, **json.loads(path.read_text()))
        if r.get('accession') in seen: continue
        if not r.get('accession'): continue
        r.setdefault('form', '13F-HR' if kind == '13f' else 'NPORT-P')
        entity = r.get('manager_cik') if kind == '13f' else r.get('fund_id') or r.get('series_id')
        if entity and r.get('report_date'): groups[(entity, r['report_date'])].append(r)
        seen.add(r['accession'])
    return groups


def build(root=ROOT, as_of=None):
    views = {'managers': [], 'funds': []}; blocked = []
    positions = {}; availability = collections.Counter()
    for kind, view in [('13f', 'managers'), ('funds', 'funds')]:
        for (entity, report), records in sorted(load_groups(root, kind).items()):
            for r in records:
                c = chronology(r)
                for key in ('accepted_at', 'public_available_at', 'ingested_at'):
                    if c[key] is None: availability[kind + '_' + key + '_missing'] += 1
            selection = select_versions(records, as_of)
            if selection['status'] != 'selected':
                blocked.append({'view': view, 'entity_id': entity, 'report_date': report, 'reason': selection['status']}); continue
            base = selection['base']; p, excluded = aggregate(selection['holdings'], kind == 'funds')
            positions[(view, entity, report)] = p
            views[view].append({'entity_id': entity, 'name': base.get('manager_name') or base.get('fund_name'),
                'registrant_cik': base.get('registrant_cik'), 'standalone_identity_basis': base.get('identity_basis'),
                'report_date': report, 'selected_accessions': selection['selected_accessions'], 'versions': selection['versions'],
                'reported_matched_identifier_equity_value_usd': round(sum(h['value_usd'] for h in p.values()), 2),
                'security_count': len(p), 'excluded_position_counts': excluded,
                'consolidation': 'separate_view_do_not_add_to_other_view',
                'source_version_count': selection['available_version_count']})
    manager_lookup = {(m['entity_id'], m['report_date']): m for m in views['managers']}
    candidates = []; unresolved = []
    for fund in views['funds']:
        # A registrant is not an adviser. Equal legal CIK is evidence of entity identity only.
        key = (fund['registrant_cik'], fund['report_date'])
        manager = manager_lookup.get(key)
        if not manager:
            unresolved.append({'fund_id': fund['entity_id'], 'registrant_cik': fund['registrant_cik'], 'report_date': fund['report_date'],
                'reason': 'no_same_date_same_legal_filer_manager; adviser_relationship_unverified'})
            continue
        fp = positions[('funds', fund['entity_id'], fund['report_date'])]
        mp = positions[('managers', manager['entity_id'], manager['report_date'])]
        common = sorted(set(fp) & set(mp))
        candidates.append({'manager_cik': manager['entity_id'], 'fund_id': fund['entity_id'], 'report_date': fund['report_date'],
            'basis': 'same_legal_filer_cik_and_report_date', 'common_security_count': len(common),
            'fund_common_security_value_usd': round(sum(fp[k]['value_usd'] for k in common), 2),
            'status': 'potential_overlap_not_verified_containment',
            'verified_overlap_value_usd': None, 'combined_value_usd': None,
            'blockers': ['shared_discretion_and_fund_scope_not_verified', 'nport_balance_unit_not_retained'],
            'sources': manager['selected_accessions'] + fund['selected_accessions']})
    return {'schema_version': 1, 'updated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'as_of': as_of,
        'status': 'separate_views_ready_overlap_attribution_pending', 'combined_ownership_value_usd': None,
        'methodology': 'Separate manager and fund-period views. No cross-view sums or inferred adviser attribution. Immutable originals/restatements/new-holdings retained. Latest available period is not silently mixed with older periods.',
        'historical_availability': '13F filing-date reconstruction is end-of-day only; N-PORT historical eligibility requires explicit public availability. Missing ingestion timestamps remain null.',
        **views, 'potential_overlaps': candidates, 'unresolved_fund_manager_mappings': unresolved,
        'blocked_selections': blocked, 'missing_temporal_evidence_counts': dict(availability),
        'counts': {'manager_periods': len(views['managers']), 'fund_periods': len(views['funds']), 'potential_overlap_pairs': len(candidates),
                   'verified_overlap_pairs': 0, 'unresolved_fund_manager_mappings': len(unresolved), 'blocked_selections': len(blocked)}}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--root', type=pathlib.Path, default=ROOT); ap.add_argument('--as-of'); args = ap.parse_args()
    result = build(args.root, args.as_of)
    out = args.root/'intelligence/reconciliation.json'; out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix('.tmp'); temporary.write_text(json.dumps(result, separators=(',', ':'), allow_nan=False)); temporary.replace(out)
    print(json.dumps(result['counts'], sort_keys=True))

if __name__ == '__main__': main()
