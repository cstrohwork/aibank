#!/usr/bin/env python3
"""Small per-period views of reconciled SEC ownership; never combine manager/fund totals."""
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'CapitalSignal/data'
FIELDS = ('entity_id', 'name', 'report_date', 'selected_accessions', 'versions',
          'reported_matched_identifier_equity_value_usd', 'security_count', 'excluded_position_counts')


def publish(source, destination):
    destination = pathlib.Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {'schema_version': 1, 'updated_at': source['updated_at'],
                'source': '../intelligence/reconciliation.json',
                'basis': 'Incomplete latest-restated matched-CUSIP equity views; not total institutional AUM. Manager and fund views must not be added.',
                'lenses': {}}
    for kind in ('managers', 'funds'):
        groups = collections.defaultdict(list)
        for row in source[kind]:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', row.get('report_date', '')):
                raise ValueError('Invalid reporting date')
            groups[row['report_date']].append({key: row.get(key) for key in FIELDS})
        manifest['lenses'][kind] = []
        for period, rows in sorted(groups.items(), reverse=True):
            filename = f'{kind}-{period}.json'
            report = {'updated_at': source['updated_at'], kind: rows,
                      'blocked_selections': [r for r in source.get('blocked_selections', [])
                                             if r['view'] == kind and r['report_date'] == period]}
            content = json.dumps(report, separators=(',', ':'), allow_nan=False)
            if len(content.encode()) > 20_000_000:
                raise ValueError('Atlas period exceeds 20 MB cap; shard before publication')
            (destination/filename).write_text(content)
            manifest['lenses'][kind].append({'report_date': period, 'file': filename, 'count': len(rows)})
    # Publish the discovery manifest only after every referenced period exists.
    (destination/'manifest.json').write_text(json.dumps(manifest, separators=(',', ':'), allow_nan=False))
    return manifest


if __name__ == '__main__':
    report = publish(json.loads((ROOT/'intelligence/reconciliation.json').read_text()), ROOT/'atlas')
    print(json.dumps(report))
