#!/usr/bin/env python3
"""Evidence-gated investor classification and explainable issuer targeting.

No network, inferred mandates, fabricated forecasts, or firm-wide AUM estimates.
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'CapitalSignal/data'
VERSION = '1.0'
COVERAGE = 70.0


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def evidence(record, as_of):
    """Require attributable documentary evidence known at measurement time."""
    if not record or not record.get('source_url') or not record.get('evidence_excerpt'):
        return False
    try:
        available = dt.date.fromisoformat(record['available_date'])
        measured = dt.date.fromisoformat(as_of)
        effective = dt.date.fromisoformat(record['effective_from'])
        until = dt.date.fromisoformat(record['effective_to']) if record.get('effective_to') else None
        return available <= measured and effective <= measured and (until is None or measured < until)
    except (ValueError, KeyError, TypeError):
        return False


def classify_portfolio(metrics, mandate=None, as_of=None):
    """Metrics require source URLs, exact comparison date and explicit % coverage.

    Scores are portfolio value-weighted percentiles produced by the factor engine,
    not percentiles invented here. Yields are fractions; growth rates percentage
    points; coverage and concentration use 0..100. No caller data are mutated.
    """
    as_of = as_of or metrics.get('as_of')
    axes = dict.fromkeys(('valuation', 'growth', 'income', 'concentration', 'implementation', 'strategy'))
    result = {'axes': axes, 'orientation': 'unknown', 'primary_style': None,
              'factor_style': None, 'status': 'insufficient_data', 'reasons': [],
              'as_of': as_of, 'methodology_version': VERSION,
              'coverage_pct': metrics.get('both_dimensions_coverage_pct'),
              'editorial_style': metrics.get('editorial_style'), 'sources': []}
    verified = evidence(mandate, as_of)
    if verified:
        result['sources'].append(mandate['source_url'])
        orientation = mandate.get('orientation')
        if orientation in ('active', 'passive'):
            result['orientation'] = orientation
        strategy = mandate.get('strategy')
        if strategy in ('private_equity', 'venture_capital', 'hedge_fund', 'alternative', 'public_equity'):
            axes['strategy'] = strategy
        if mandate.get('implementation') == 'index':
            axes['implementation'] = 'index'
            result['orientation'] = 'passive'
    elif mandate:
        result['reasons'].append('mandate_evidence_missing_invalid_or_not_available_as_of')
    comparable = bool(as_of and metrics.get('as_of') == as_of and
                      metrics.get('benchmark_as_of') == as_of and metrics.get('source_urls'))
    if comparable:
        result['sources'].extend(metrics['source_urls'])
    else:
        result['reasons'].append('missing_same_date_benchmark_or_metric_provenance')
    def covered(name):
        v = metrics.get(name)
        return number(v) and COVERAGE <= v <= 100
    def valid(*names):
        return all(number(metrics.get(n)) for n in names)
    # Sector mapping can be used independently from value/growth, but must be
    # same-date and share the full eligible disclosed equity denominator.
    if comparable and covered('sector_coverage_pct') and valid('largest_sector_pct'):
        if 75 < metrics['largest_sector_pct'] <= 100 and metrics.get('largest_sector'):
            axes['concentration'] = {'sector': metrics['largest_sector'], 'weight_pct': metrics['largest_sector_pct']}
    full = comparable and covered('both_dimensions_coverage_pct') and valid('value_score', 'growth_score')
    full = full and 0 <= metrics['value_score'] <= 100 and 0 <= metrics['growth_score'] <= 100
    full = full and valid('value_factor_count', 'growth_factor_count') and metrics['value_factor_count'] >= 2 and metrics['growth_factor_count'] >= 2
    if full:
        delta = metrics['value_score'] - metrics['growth_score']
        result['factor_style'] = 'Value' if delta >= 15 else 'Growth' if delta <= -15 else 'Blend'
        axes['valuation'] = 'value' if delta >= 15 else 'blend'
        axes['growth'] = 'growth' if delta <= -15 else 'blend'
        if (covered('valuation_coverage_pct') and valid('earnings_yield', 'benchmark_earnings_yield', 'fcf_yield', 'benchmark_fcf_yield', 'sector_relative_value_score') and
            metrics['benchmark_earnings_yield'] > 0 and metrics['benchmark_fcf_yield'] > 0 and
            metrics['earnings_yield'] >= 1.5 * metrics['benchmark_earnings_yield'] and
            metrics['fcf_yield'] >= 1.5 * metrics['benchmark_fcf_yield'] and metrics['sector_relative_value_score'] >= 75):
            axes['valuation'] = 'deep_value'
        if (covered('growth_coverage_pct') and valid('growth_rate_pct', 'benchmark_growth_rate_pct') and
            metrics['benchmark_growth_rate_pct'] > 0 and metrics['growth_rate_pct'] >= 1.5 * metrics['benchmark_growth_rate_pct'] and metrics['growth_score'] >= 75):
            axes['growth'] = 'aggressive_growth'
        if (covered('forward_coverage_pct') and valid('forward_pe', 'benchmark_forward_pe', 'forward_eps_growth_pct', 'benchmark_forward_eps_growth_pct') and
            0 < metrics['forward_pe'] < metrics['benchmark_forward_pe'] and
            metrics['forward_eps_growth_pct'] > max(0, metrics['benchmark_forward_eps_growth_pct']) and
            metrics['forward_pe'] / metrics['forward_eps_growth_pct'] < 1):
            result['garp'] = True
            result['forward_peg'] = metrics['forward_pe'] / metrics['forward_eps_growth_pct']
    else:
        result['reasons'].append('requires_70pct_both_dimension_coverage_and_valid_scores')
    if (comparable and covered('yield_coverage_pct') and metrics.get('yield_basis') == 'regular_indicated_forward' and
        valid('dividend_yield', 'benchmark_dividend_yield') and metrics['benchmark_dividend_yield'] > 0 and
        metrics['dividend_yield'] >= 1.5 * metrics['benchmark_dividend_yield'] and
        metrics['dividend_yield'] >= metrics['benchmark_dividend_yield'] + .015):
        axes['income'] = 'yield'
    # Membership overlap alone never proves passive or index implementation.
    if (comparable and verified and mandate.get('benchmark_id') == metrics.get('benchmark_id') and
        covered('index_comparison_coverage_pct') and valid('index_overlap_pct', 'active_share_pct') and
        75 <= metrics['index_overlap_pct'] <= 100 and 0 <= metrics['active_share_pct'] <= 30):
        axes['implementation'] = axes['implementation'] or 'index_aligned'
    if axes['strategy'] in ('private_equity', 'venture_capital'):
        result['primary_style'] = axes['strategy'].replace('_', ' ').title()
    elif axes['implementation'] == 'index':
        result['primary_style'] = 'Index'
    elif axes['concentration']:
        result['primary_style'] = 'Sector'
    elif full:
        result['primary_style'] = ('GARP' if result.get('garp') else
            'Deep Value' if axes['valuation'] == 'deep_value' else
            'Aggressive Growth' if axes['growth'] == 'aggressive_growth' else
            'Yield' if axes['income'] else result['factor_style'])
    elif axes['strategy'] in ('hedge_fund', 'alternative'):
        result['reasons'].append('alternative_strategy_verified_factor_style_unresolved')
    if result['primary_style']:
        result['status'] = 'classified'
    result['sources'] = sorted(set(result['sources']))
    return result


def rollup_orientation(funds, institution_equity_assets_usd, as_of):
    """Use explicit same-date institution equity assets, never 13F exposure."""
    result = {'orientation': 'unknown', 'active_pct': None, 'passive_pct': None,
              'classified_coverage_pct': None, 'reasons': []}
    if not number(institution_equity_assets_usd) or institution_equity_assets_usd <= 0:
        result['reasons'].append('missing_verified_institution_equity_assets')
        return result
    active = passive = 0.0
    seen = set()
    for fund in funds:
        key = fund.get('fund_id')
        if not key or key in seen:
            result['reasons'].append('duplicate_or_missing_fund_id')
            return result
        seen.add(key)
        amount = fund.get('verified_equity_assets_usd')
        if (fund.get('as_of') != as_of or not evidence(fund.get('manager_mapping'), as_of) or
            not evidence(fund.get('asset_evidence'), as_of) or not number(amount) or amount < 0):
            result['reasons'].append('fund_excluded_missing_same_date_mapping_or_asset_evidence')
            continue
        mandate = fund.get('mandate')
        if not evidence(mandate, as_of):
            continue
        if mandate.get('orientation') == 'active':
            active += amount
        elif mandate.get('orientation') == 'passive' or mandate.get('implementation') == 'index':
            passive += amount
    if active + passive > institution_equity_assets_usd:
        result['reasons'].append('classified_fund_assets_exceed_institution_denominator')
        return result
    result.update(active_pct=100 * active / institution_equity_assets_usd,
                  passive_pct=100 * passive / institution_equity_assets_usd,
                  classified_coverage_pct=100 * (active + passive) / institution_equity_assets_usd)
    # Threshold uses institution denominator, never only classified sampled funds.
    if result['active_pct'] >= COVERAGE:
        result['orientation'] = 'active'
    elif result['passive_pct'] >= COVERAGE:
        result['orientation'] = 'passive'
    elif result['classified_coverage_pct'] >= COVERAGE:
        result['orientation'] = 'mixed'
    return result


def score_target(candidate, issuer):
    """Score an explicitly supplied issuer/candidate pair, never invent candidates.

    All component scores 0..100. Capacity uses verified equity assets and an
    explicit mandate position cap. Dollar liquidity is average daily value traded.
    This is a provisional prioritization model, not purchase likelihood.
    """
    result = {'investor_id': candidate.get('investor_id'), 'issuer_id': issuer.get('issuer_id'),
              'score': None, 'status': 'blocked', 'reasons': [], 'components': {}, 'methodology_version': VERSION}
    measured = issuer.get('as_of')
    if not measured or candidate.get('as_of') != measured:
        result['reasons'].append('candidate_issuer_date_mismatch')
    if not evidence(candidate.get('mandate'), measured):
        result['reasons'].append('unverified_or_unavailable_mandate')
    coverage = candidate.get('fundamental_coverage_pct')
    if not number(coverage) or not COVERAGE <= coverage <= 100:
        result['reasons'].append('fundamental_coverage_below_70pct_or_invalid')
    for name in ('peer_fit_score', 'mandate_fit_score'):
        v = candidate.get(name)
        if not number(v) or not 0 <= v <= 100 or not candidate.get(name + '_evidence'):
            result['reasons'].append('missing_or_invalid_' + name)
    for name in ('verified_equity_assets_usd', 'max_position_pct', 'proposed_position_usd'):
        v = candidate.get(name)
        if not number(v) or v <= 0:
            result['reasons'].append('missing_or_invalid_' + name)
    if not number(candidate.get('existing_position_usd')) or candidate['existing_position_usd'] < 0:
        result['reasons'].append('missing_or_invalid_existing_position_usd')
    for name in ('average_daily_dollar_volume_usd', 'max_participation_pct', 'max_days_to_build'):
        if not number(issuer.get(name)) or issuer[name] <= 0:
            result['reasons'].append('missing_or_invalid_' + name)
    for field in ('source_urls',):
        if not candidate.get(field) or not issuer.get(field):
            result['reasons'].append('missing_candidate_or_issuer_sources')
    if number(candidate.get('max_position_pct')) and candidate['max_position_pct'] > 100:
        result['reasons'].append('max_position_pct_exceeds_100')
    if number(issuer.get('max_participation_pct')) and issuer['max_participation_pct'] > 100:
        result['reasons'].append('max_participation_pct_exceeds_100')
    if result['reasons']:
        return result
    amount = candidate['proposed_position_usd']
    capacity = max(0, candidate['verified_equity_assets_usd'] * candidate['max_position_pct'] / 100 - candidate['existing_position_usd'])
    days = amount / (issuer['average_daily_dollar_volume_usd'] * issuer['max_participation_pct'] / 100)
    result.update(capacity_usd=capacity, days_to_build=days)
    if amount > capacity:
        result['reasons'].append('proposed_position_exceeds_mandate_capacity')
    if days > issuer['max_days_to_build']:
        result['reasons'].append('proposed_position_exceeds_liquidity_limit')
    if result['reasons']:
        return result
    result['components'] = {'peer_fit': candidate['peer_fit_score'], 'mandate_fit': candidate['mandate_fit_score'],
        'capacity': 100 * (1 - amount / capacity), 'liquidity': 100 * (1 - days / issuer['max_days_to_build'])}
    weights = {'peer_fit': .4, 'mandate_fit': .3, 'capacity': .15, 'liquidity': .15}
    result.update(score=round(sum(result['components'][k] * w for k, w in weights.items()), 2),
                  status='eligible', weights=weights, sources=sorted(set(candidate['source_urls'] + issuer['source_urls'] + [candidate['mandate']['source_url']])))
    result['reasons'] = ['passed_documented_mandate_coverage_capacity_and_liquidity_checks']
    return result


def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def discover_mandate_sources(entries, fetch_limit=0, fetch_documents=False, previous=None):
    """Queue real registrants, optionally retrieve SEC prospectus source candidates.

    Discovery is deliberately separate from mandate verification: a trust-level
    prospectus may contain many funds, and current text cannot establish history.
    """
    registrants = {}
    for e in entries:
        cik = e.get('registrant_cik')
        if not cik:
            continue
        cik = str(cik).zfill(10)
        r = registrants.setdefault(cik, {'registrant_cik': cik,
            'registrant_name': e.get('registrant_name'), 'funds': {},
            'submissions_url': f'https://data.sec.gov/submissions/CIK{cik}.json',
            'status': 'queued', 'prospectus_candidates': []})
        key = e.get('fund_id') or e.get('series_id')
        r['funds'][key] = {'fund_id': key, 'name': e.get('fund_name')}
    for prior in (previous or {}).get('registrants', []):
        if prior.get('registrant_cik') in registrants:
            current = registrants[prior['registrant_cik']]
            current.update({k: v for k, v in prior.items() if k not in ('funds', 'registrant_cik', 'registrant_name', 'submissions_url')})
    def get(url):
        time.sleep(.4)
        req = urllib.request.Request(url, headers={'User-Agent': os.getenv('SEC_USER_AGENT', 'CapitalSignal Research hello@ainvestmentbank.ai')})
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read()
    pending = [r for r in registrants.values() if r['status'] in ('queued', 'submissions_fetch_failed')]
    for r in sorted(pending, key=lambda r: (r['status'] != 'queued', r['registrant_cik']))[:fetch_limit]:
        try:
            payload = json.loads(get(r['submissions_url']))
            recent = payload.get('filings', {}).get('recent', {})
            for i, form in enumerate(recent.get('form', [])):
                if form not in ('497', '497K', '485APOS', '485BPOS', 'N-1A', 'N-1A/A', 'N-2', 'N-2/A'):
                    continue
                accession = recent['accessionNumber'][i]
                document = recent['primaryDocument'][i]
                if not document or '..' in document:
                    continue
                url = f"https://www.sec.gov/Archives/edgar/data/{int(r['registrant_cik'])}/{accession.replace('-', '')}/{document}"
                candidate = {'form': form, 'accession': accession,
                    'available_date': recent['filingDate'][i], 'source_url': url,
                    'status': 'document_queued', 'fund_attribution': 'unverified', 'effective_from': None}
                if fetch_documents:
                    try:
                        raw = get(url).decode('utf-8', errors='replace')
                        plain = re.sub(r'<[^>]*>', ' ', raw)
                        plain = re.sub(r'\s+', ' ', plain)
                        # Extract evidence for review, never convert text/name hints
                        # into a verified mandate or effective date automatically.
                        phrases = [m.group(0) for m in re.finditer(r'.{0,120}(?:seeks? to track|indexing investment|actively managed|investment objective|principal investment strateg)[^.;]{0,350}', plain, flags=re.I)]
                        candidate.update(status='retrieved_needs_fund_attribution_and_effective_date', evidence_candidates=phrases[:20], retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat())
                    except Exception as exc:
                        candidate.update(status='document_fetch_failed', error=str(exc))
                r['prospectus_candidates'].append(candidate)
                if len(r['prospectus_candidates']) >= 3:
                    break
            r['status'] = 'prospectus_candidates_found' if r['prospectus_candidates'] else 'no_recent_prospectus_historical_submissions_required'
            r['historical_submission_files'] = payload.get('filings', {}).get('files', [])
        except Exception as exc:
            r.update(status='submissions_fetch_failed', error=str(exc))
    rows = sorted(registrants.values(), key=lambda r: r['registrant_cik'])
    for r in rows:
        r['funds'] = list(r['funds'].values())
    return {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'policy': 'Candidate source queue only. Verify fund attribution, exact strategy claim and effective dates before importing mandates; retrieval dates are not historical availability dates.',
            'registrants': rows, 'registrant_count': len(rows)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mandates', type=Path, help='JSON {mandates:[{fund_id,...documentary evidence}]}')
    ap.add_argument('--targets', type=Path, help='JSON {issuer:{...}, candidates:[...]}')
    ap.add_argument('--output-dir', type=Path, default=DATA / 'intelligence')
    ap.add_argument('--discover-mandates', type=int, default=0, metavar='LIMIT', help='Fetch recent SEC submissions for up to LIMIT queued registrants')
    ap.add_argument('--fetch-prospectuses', action='store_true', help='Also fetch up to three candidate documents per selected registrant; evidence remains unverified')
    args = ap.parse_args()
    mandates = load(args.mandates, {}).get('mandates', []) if args.mandates else []
    grouped = {}
    for m in mandates:
        grouped.setdefault(m.get('fund_id'), []).append(m)
    entries = load(DATA / 'funds/index.json', {}).get('funds', [])
    latest = {}
    for e in entries:
        key = e.get('fund_id') or e.get('series_id')
        if not key:
            continue
        if key not in latest or e['report_date'] > latest[key]['report_date']:
            latest[key] = e
    funds = []
    for key, e in sorted(latest.items()):
        rows = [m for m in grouped.get(key, []) if evidence(m, e['report_date'])]
        # Ambiguous conflicting evidence is quarantined rather than last-write-wins.
        signatures = {(m.get('orientation'), m.get('strategy'), m.get('implementation'), m.get('benchmark_id')) for m in rows}
        mandate = rows[0] if len(signatures) == 1 else None
        classification = classify_portfolio({'as_of': e['report_date']}, mandate, e['report_date'])
        data = load(DATA / 'funds' / e['file'], {})
        eligible = sum(h['reported_value_usd'] for h in data.get('holdings', [])
            if h.get('asset_category') == 'EC' and number(h.get('reported_value_usd')) and h['reported_value_usd'] > 0)
        funds.append({'fund_id': key, 'fund_name': e['fund_name'], 'report_date': e['report_date'],
            'reported_common_equity_value_usd': round(eligible, 2), 'mandate_status': 'conflicting_evidence' if len(signatures) > 1 else 'verified' if mandate else 'missing_evidence',
            'source_url': e.get('source'), 'classification': classification})
    profiles = load(DATA / 'investor_profiles.json', {}).get('profiles', [])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'methodology_version': VERSION,
        'status': 'blocked_pending_documentary_mandates_and_point_in_time_factors',
        'counts': {'funds': len(funds), 'verified_mandates': sum(f['mandate_status'] == 'verified' for f in funds),
                   'managers': len(profiles), 'funds_orientation_unknown': sum(f['classification']['orientation'] == 'unknown' for f in funds)},
        'funds': funds,
        'manager_rollup_policy': 'Requires verified manager-fund relationship, same-date verified equity assets and complete institution denominator; do not weight funds equally or use 13F value as total firm AUM.',
        'blockers': ['Documentary mandates with effective and public availability dates', 'Point-in-time benchmark and issuer factor coverage',
                     'Verified manager-to-fund relationships and institution equity AUM', 'Dated market liquidity and explicit issuer target request'],
        'targeting': {'status': 'no_issuer_request', 'results': []}}
    if args.targets:
        request = load(args.targets, {})
        results = [score_target(c, request.get('issuer', {})) for c in request.get('candidates', [])]
        results.sort(key=lambda x: (x['score'] is None, -(x['score'] or 0), str(x['investor_id'])))
        output['targeting'] = {'status': 'evaluated', 'results': results}
    queue = discover_mandate_sources(entries, max(0, args.discover_mandates), args.fetch_prospectuses, load(args.output_dir / 'investor_mandate_queue.json', {}))
    (args.output_dir / 'investor_mandate_queue.json').write_text(json.dumps(queue, separators=(',', ':')))
    (args.output_dir / 'investor_readiness.json').write_text(json.dumps(output, separators=(',', ':')))
    print(json.dumps(output['counts'], sort_keys=True))


if __name__ == '__main__':
    main()
