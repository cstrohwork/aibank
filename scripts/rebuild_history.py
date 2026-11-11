#!/usr/bin/env python3
"""Materialize latest-restated report periods while keeping every accession."""
import collections
import json
import pathlib
import re
from sec_history import ROOT, load, save

def choose_13f(versions):
    holdings, sources, latest = None, [], None
    unresolved = False
    for item in sorted(versions, key=lambda x: (x['filing_date'], x['accession'])):
        amendment = item.get('form') == '13F-HR/A'
        kind = item.get('amendment_type', '').upper()
        if not amendment or kind == 'RESTATEMENT':
            holdings = list(item['holdings'])
            sources = [item['source']]
            latest = item
            unresolved = False
        elif kind == 'NEW HOLDINGS' and holdings is not None:
            holdings += item['holdings']
            sources.append(item['source'])
            latest = item
        else:
            unresolved = True
    if latest is None:
        return None
    output = dict(latest, holdings=holdings, source_filings=sources,
                  amendment_review_required=unresolved)
    return output

def rebuild(root=ROOT):
    history = root / 'history'
    # Seed from current cached periods; retain accessions and never discard history.
    managers = {}
    for entry in load(root / '13f' / 'index.json', {}).get('managers', []):
        data = load(root / '13f' / entry['file'])
        if data:
            managers[(entry['manager_cik'], entry['report_date'])] = data
    grouped = collections.defaultdict(list)
    for path in (history / 'normalized' / '13f').glob('*.json.gz'):
        d = load(path)
        grouped[(d['manager_cik'], d['report_date'])].append(d)
    for key, versions in grouped.items():
        existing = managers.get(key)
        if existing and existing.get('accession') not in {x['accession'] for x in versions}:
            versions.append(dict(existing, form='13F-HR'))
        selected = choose_13f(versions)
        if selected:
            managers[key] = selected
    entries = []
    for (cik, date), data in sorted(managers.items()):
        if date < '2025-09-30':
            continue
        filename = f'{cik}-{date}.json'
        save(root / '13f' / filename, data)
        entries.append(dict(manager_cik=cik, manager_name=data['manager_name'],
            report_date=date, filing_date=data['filing_date'],
            holdings_count=len(data['holdings']), file=filename))
    save(root / '13f' / 'index.json', {'start_report_date': '2025-09-30', 'managers': entries,
        'value_unit': 'USD', 'limitations': 'Incomplete backfill. Latest-restated periods; original accessions retained separately. Legacy value_thousands field contains USD for this 2025+ history. See history/status.json.'})

    funds = {}
    for entry in load(root / 'funds' / 'history_index.json', {}).get('funds', []) + load(root / 'funds' / 'index.json', {}).get('funds', []):
        data = load(root / 'funds' / entry['file'])
        if data:
            funds[(data.get('fund_id') or data['series_id'], data['report_date'])] = data
    for path in (history / 'normalized' / 'funds').glob('*.json.gz'):
        data = load(path)
        key = (data.get('fund_id') or data['series_id'], data['report_date'])
        old = funds.get(key, {})
        if (data['filing_date'], data['accession']) >= (old.get('filing_date', ''), old.get('accession', '')):
            funds[key] = data
    entries = []
    for (series, date), data in sorted(funds.items()):
        if date < '2025-09-30':
            continue
        data['fund_id'] = series
        filename = f'{series}-{date}.json'
        save(root / 'funds' / filename, data)
        entries.append({k: data.get(k) for k in ('fund_id', 'series_id', 'identity_basis', 'fund_name', 'registrant_cik',
            'registrant_name', 'report_date', 'filing_date', 'accession', 'source')} |
            {'file': filename, 'holdings_count': len(data['holdings'])})
    save(root / 'funds' / 'history_index.json', {'funds': entries, 'start_report_date': '2025-09-30',
        'basis': 'Latest filed version per series/report date; original accessions retained in history/normalized. Not an as-known-on-report-date dataset.'})
    latest = {}
    for entry in sorted(entries, key=lambda x: (x['report_date'], x['filing_date'])):
        latest[entry['fund_id']] = entry
    save(root / 'funds' / 'index.json', {'funds': list(latest.values()),
        'filings_parsed': len(entries), 'errors': [], 'limitations': 'Incomplete all-market backfill; latest period per fund. See history/status.json for archive/parse errors.'})
    # Keep registrant history grouped by exact report date; never add quarters together.
    by_period = collections.defaultdict(dict)
    for data in funds.values():
        key, date = data['registrant_cik'], data['report_date']
        firm = by_period[date].setdefault(key, {'registrant_cik': key, 'registrant_name': data['registrant_name'],
            'equity_assets_usd': 0, 'passive_equity_assets_usd': 0, 'active_equity_assets_usd': 0,
            'unclassified_equity_assets_usd': 0, 'funds': [], 'institution_wide_equity_aum_usd': None})
        amount = sum(max(0, float(h['reported_value_usd'])) for h in data['holdings'] if h['asset_category'] in ('EC', 'EP'))
        orientation = 'passive' if re.search(r'\b(index fund|index etf|index portfolio)\b', data['fund_name'], re.I) else 'unclassified'
        firm['equity_assets_usd'] += amount
        firm[orientation + '_equity_assets_usd'] += amount
        firm['funds'].append({'fund_id': data.get('fund_id') or data['series_id'], 'series_id': data['series_id'], 'equity_assets_usd': amount,
            'orientation': orientation, 'source': data['source']})
    for date, firms in by_period.items():
        for firm in firms.values():
            total = firm['equity_assets_usd']
            for kind in ('active', 'passive', 'unclassified'):
                firm[kind + '_pct_of_disclosed_sample_equity_assets'] = round(100 * firm[kind + '_equity_assets_usd'] / total, 2) if total else None
        save(history / 'registrants' / (date + '.json'), {'report_date': date, 'firms': list(firms.values()),
            'coverage': 'Sampled disclosed funds only; registrants are not assumed to be ultimate advisers.'})
    dates = sorted({date for cik, date in managers} | {date for series, date in funds})
    save(history / 'index.json', {'start_report_date': '2025-09-30',
        'reporting_periods': [{'report_date': date,
            'manager_count': sum(d == date for cik, d in managers),
            'fund_count': sum(d == date for series, d in funds),
            'investor_profiles': 'investor_profiles/' + date + '.json' if any(d == date for cik, d in managers) else None,
            'registrant_profiles': 'registrants/' + date + '.json' if date in by_period else None} for date in dates],
        'filing_archive_status': 'status.json',
        'basis': 'Latest-restated reporting periods; incomplete backfill, not as-known-at-report-date history.'})
    print('Historical manager periods:', len(managers), 'fund periods:', len(funds))

if __name__ == '__main__':
    rebuild()
