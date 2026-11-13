#!/usr/bin/env python3
"""Separate current ETF proxy field coverage; no historical membership or style inference."""
import argparse
import datetime as dt
import gzip
import json
import math
from ingest_sp1500_fundamentals import OUT, TAGS, dump, now, snapshot


def valid_weight(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def proxy_coverage(universe, records, as_of=None):
    cutoff = as_of or universe['as_of']
    dt.date.fromisoformat(cutoff)
    result = {'updated_at': now(), 'as_of': cutoff,
        'membership_basis': 'Current SPTM and IWV ETF holdings proxies; not official index membership or historical constituents',
        'benchmarks': {}, 'calculated_style': None,
        'historical_comparison_status': 'blocked_missing_historical_membership_weights_and_market_factors'}
    proxies = universe.get('proxy_snapshots')
    if not proxies:
        result['status'] = 'blocked_missing_separate_provider_snapshots'
        return result
    for label, provider in proxies.items():
        source = {k: provider.get(k) for k in ('as_of', 'retrieved_at', 'source_url', 'source_sha256', 'membership_basis')}
        row = {'source': source, 'field_weight_coverage_pct': None, 'calculated_style': None}
        result['benchmarks'][label] = row
        try:
            provider_date = dt.date.fromisoformat(provider['as_of'])
        except (KeyError, TypeError, ValueError):
            row['status'] = 'blocked_invalid_provider_date'
            continue
        if provider_date > dt.date.fromisoformat(cutoff):
            row['status'] = 'blocked_provider_snapshot_after_cutoff'
            continue
        if not all(source.get(k) for k in ('source_url', 'source_sha256', 'retrieved_at')):
            row['status'] = 'blocked_missing_source_provenance'
            continue
        members = provider.get('securities', [])
        if not members or any(not valid_weight(s.get('weight_pct')) for s in members):
            row['status'] = 'blocked_invalid_provider_weights'
            continue
        total = sum(s['weight_pct'] for s in members)
        if not total:
            row['status'] = 'blocked_zero_provider_weight'
            continue
        # Use this provider's holdings date, never a newer union-wide date.
        cache = {}
        covered = {field: 0. for field in TAGS}
        counts = {field: set() for field in TAGS}
        mapped_weight = 0.
        for member in members:
            cik = member.get('cik')
            if cik:
                mapped_weight += member['weight_pct']
            if cik in records:
                if cik not in cache:
                    cache[cik] = snapshot(records[cik], provider['as_of'])
                for field in cache[cik]:
                    covered[field] += member['weight_pct']
                    counts[field].add(cik)
        row.update(status='current_proxy_field_diagnostics_only', security_count=len(members),
            unique_mapped_issuers=len({s['cik'] for s in members if s.get('cik')}),
            denominator_provider_weight_pct=total,
            mapped_provider_weight_coverage_pct=100*mapped_weight/total,
            field_weight_coverage_pct={k:100*v/total for k,v in covered.items()},
            field_issuer_coverage={k:len(v) for k,v in counts.items()},
            fact_cutoff=provider['as_of'], field_basis='Reported annual USD facts available by provider holdings date; annual is not TTM',
            historical_membership_verified=False)
    result['status'] = 'current_proxy_diagnostics_only' if all(r['status']=='current_proxy_field_diagnostics_only' for r in result['benchmarks'].values()) else 'partial_or_blocked'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', help='Date cutoff; later provider snapshots are blocked')
    args = parser.parse_args()
    universe = json.loads((OUT/'universe.json').read_text())
    records = {}
    for path in (OUT/'companyfacts').glob('*.json.gz'):
        record = json.loads(gzip.decompress(path.read_bytes()))
        if record.get('cik') != path.name.split('.')[0]:
            raise ValueError('Companyfacts cache identity mismatch: '+path.name)
        records[record['cik']] = record
    report = proxy_coverage(universe, records, args.as_of)
    dump(OUT/'proxy_benchmark_coverage.json', report)
    print(json.dumps(report, allow_nan=False))


if __name__ == '__main__':
    main()
