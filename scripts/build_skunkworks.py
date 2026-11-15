#!/usr/bin/env python3
"""Bounded security sample from exact-version validated Atlas manager positions."""
import collections
import datetime as dt
import json
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from reconcile_ownership import aggregate
ROOT = pathlib.Path(__file__).resolve().parents[1]

def build(root=ROOT, limit=50):
    data = root/'CapitalSignal/data'
    manifest = json.loads((data/'atlas/manifest.json').read_text())
    period = manifest['lenses']['managers'][0]['report_date']
    source = json.loads((data/'atlas'/manifest['lenses']['managers'][0]['file']).read_text())
    counts = collections.Counter(r['entity_id'] for r in source['managers'])
    candidates = sorted((r for r in source['managers'] if counts[r['entity_id']] == 1), key=lambda r: (-r['reported_matched_identifier_equity_value_usd'], r['entity_id']))[:limit]
    securities, portfolios, skipped = {}, [], []
    for row in candidates:
        path = data/'13f'/f"{row['entity_id']}-{period}.json"
        try:
            snapshot = json.loads(path.read_text())
            assert snapshot['accession'] in row['selected_accessions'] and len(row['selected_accessions']) == 1
            assert snapshot['report_date'] == period and snapshot['value_unit'] == 'USD'
            assert str(snapshot['manager_cik']).zfill(10) == str(row['entity_id']).zfill(10)
            assert not snapshot.get('amendment_review_required')
            positions, _ = aggregate(snapshot['holdings'])
            total = sum(h['value_usd'] for h in positions.values())
            assert len(positions) == row['security_count'] and abs(total-row['reported_matched_identifier_equity_value_usd']) < .011
            assert total > 0
        except (OSError, ValueError, KeyError, AssertionError):
            skipped.append(row['entity_id']); continue
        names = {str(h.get('cusip','')).strip().upper(): h.get('issuer') for h in snapshot['holdings']}
        weights = sorted((h['value_usd']/total for h in positions.values()), reverse=True)
        portfolios.append(dict(entity_id=row['entity_id'], name=row['name'], total=total, count=len(weights), top1=weights[0], top5=sum(weights[:5]), top10=sum(weights[:10]), hhi=sum(w*w for w in weights), source=row['versions'][0]['source']))
        for cusip, h in positions.items():
            s = securities.setdefault(cusip, dict(cusip=cusip, name=names.get(cusip) or cusip, holders=[]))
            s['holders'].append(dict(entity_id=row['entity_id'], weight=round(h['value_usd']/total,12)))
    return dict(schema_version=1, updated_at=manifest['updated_at'], built_at=dt.datetime.now(dt.timezone.utc).isoformat(), report_date=period, candidate_limit=limit, candidate_count=len(candidates), validated_count=len(portfolios), skipped=skipped, portfolios=portfolios, securities=list(securities.values()), basis='Top 50 managers by reported matched-CUSIP equity exposure at one date; only exact-version validated cached positions. Counts and portfolio weights apply only to this sample. Manager discretion can overlap; no market ownership percentages or total AUM inferred.')

def publish(root=ROOT):
    result=build(root); out=root/'CapitalSignal/data/atlas/skunkworks-security.json'
    temp=out.with_suffix('.tmp'); temp.write_text(json.dumps(result,separators=(',',':'),allow_nan=False));temp.replace(out)
    return result

if __name__ == '__main__':
    result=publish()
    print(json.dumps({k:result[k] for k in ['report_date','candidate_count','validated_count','skipped']}))
