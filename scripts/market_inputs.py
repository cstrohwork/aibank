#!/usr/bin/env python3
"""Validate dated market inputs and calculate class-specific ownership/liquidity.

The default run audits repository coverage; it never invents provider prices,
class share counts, float, or corporate action history.
"""
import argparse
import csv
import datetime as dt
import gzip
import io
import json
import math
import hashlib
import time
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'CapitalSignal/data/intelligence'


def finite(value, positive=False):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and (value > 0 if positive else value >= 0)


def date(value):
    return dt.date.fromisoformat(value)


def available(row, as_of):
    """A date-only cutoff means end of that UTC date; unknown availability fails."""
    try:
        return date(row['date']) <= date(as_of) and date(row['available_at'][:10]) <= date(as_of) and bool(row['source_url'])
    except (KeyError, TypeError, ValueError):
        return False


def validate_price(row, as_of):
    return (available(row, as_of) and bool(row.get('security_id')) and
            row.get('currency') == 'USD' and row.get('price_basis') == 'unadjusted_close' and
            row.get('volume_basis') == 'unadjusted_shares' and
            finite(row.get('close'), True) and finite(row.get('volume')))


def split_factor(security_id, start, end, actions, as_of):
    """Factor to convert pre-split shares to end-date share units.

    Callers must separately establish complete action coverage for this interval.
    Merger/spinoff conversions are deliberately unsupported.
    """
    factor = 1.
    for action in actions:
        if action.get('security_id') != security_id:
            continue
        event_date = action.get('date')
        if not event_date or not start < event_date <= end:
            continue
        if not available(action, as_of):
            raise ValueError('corporate action unavailable at cutoff')
        if action.get('type') != 'split':
            raise ValueError('unsupported corporate action requires explicit security conversion')
        if not finite(action.get('new_shares'), True) or not finite(action.get('old_shares'), True):
            raise ValueError('invalid split ratio')
        factor *= action['new_shares'] / action['old_shares']
    return factor


def action_coverage(security_id, start, end, coverage, as_of):
    return any(c.get('security_id') == security_id and c.get('complete') is True and
               c.get('start', '9999') <= start and c.get('date', '') >= end and
               available(c, as_of) for c in coverage)


def denominator(row, security_id, as_of, kind, price_date, max_age_days=45):
    if not available(row, as_of) or row.get('security_id') != security_id:
        return False
    if row.get('scope') != 'share_class' or row.get('unit') != 'shares' or row.get('kind') != kind:
        return False
    try:
        age = (date(price_date) - date(row['date'])).days
    except (ValueError, KeyError):
        return False
    return 0 <= age <= max_age_days and finite(row.get('value'), True)


def calculate_security(security_id, bundle, as_of, position_shares=None, participation=.1, window=20):
    if not finite(participation, True) or participation > 1:
        raise ValueError('participation must be in (0, 1]')
    if not isinstance(window, int) or isinstance(window, bool) or window < 2:
        raise ValueError('window must be at least two trading observations')
    if position_shares is not None and not finite(position_shares):
        raise ValueError('position shares must be nonnegative')
    rows = [r for r in bundle.get('prices', []) if r.get('security_id') == security_id and validate_price(r, as_of)]
    result = {'security_id': security_id, 'as_of': as_of, 'currency': 'USD', 'market_cap_usd': None,
              'ownership_pct_outstanding': None, 'ownership_pct_float': None,
              'liquidity': None, 'blockers': [], 'sources': []}
    if not rows:
        result['blockers'].append('missing_verified_unadjusted_price_volume')
        return result
    # Conflicting provider observations on a date are not silently chosen.
    grouped = {}
    for row in rows:
        grouped.setdefault(row['date'], []).append(row)
    if any(len({(r['close'], r['volume']) for r in values}) > 1 for values in grouped.values()):
        result['blockers'].append('conflicting_price_observations')
        return result
    rows = [values[0] for _, values in sorted(grouped.items())]
    latest = rows[-1]
    result.update(price_date=latest['date'], close_usd=latest['close'])
    result['sources'].append(latest['source_url'])
    price_age = (date(as_of) - date(latest['date'])).days
    result['price_age_calendar_days'] = price_age
    if price_age > 7:
        result['blockers'].append('stale_price_over_7_calendar_days')
        return result
    for kind, output in [('outstanding', 'ownership_pct_outstanding'), ('float', 'ownership_pct_float')]:
        candidates = [r for r in bundle.get('denominators', []) if denominator(r, security_id, as_of, kind, latest['date'])]
        if not candidates:
            result['blockers'].append('missing_dated_share_class_' + kind)
            continue
        newest = max(r['date'] for r in candidates)
        candidates = [r for r in candidates if r['date'] == newest]
        if len({r['value'] for r in candidates}) != 1:
            result['blockers'].append('conflicting_' + kind + '_denominator')
            continue
        d = candidates[0]
        if d['date'] != latest['date'] and not action_coverage(security_id, d['date'], latest['date'], bundle.get('action_coverage', []), as_of):
            result['blockers'].append('unverified_actions_since_' + kind + '_date')
            continue
        try:
            count = d['value'] * split_factor(security_id, d['date'], latest['date'], bundle.get('actions', []), as_of)
        except ValueError as exc:
            result['blockers'].append(str(exc))
            continue
        result[kind + '_shares'] = count
        result[kind + '_date'] = d['date']
        result['sources'].append(d['source_url'])
        if kind == 'outstanding':
            result['market_cap_usd'] = latest['close'] * count
        if position_shares is not None:
            result[output] = 100 * position_shares / count
    if result.get('float_shares', 0) > result.get('outstanding_shares', float('inf')):
        result['ownership_pct_float'] = None
        result.pop('float_shares', None)
        result['blockers'].append('float_exceeds_outstanding')
    sample = rows[-window:]
    if len(sample) < window:
        result['blockers'].append('insufficient_daily_observations')
    elif not action_coverage(security_id, sample[0]['date'], latest['date'], bundle.get('action_coverage', []), as_of):
        result['blockers'].append('unverified_actions_in_liquidity_window')
    else:
        try:
            volumes = [r['volume'] * split_factor(security_id, r['date'], latest['date'], bundle.get('actions', []), as_of) for r in sample]
            adv = sum(volumes) / window
            # Actual daily dollar volume is invariant to split share conversion.
            addv = sum(r['close'] * r['volume'] for r in sample) / window
            result['liquidity'] = {'observations': window, 'start': sample[0]['date'], 'end': latest['date'],
                'average_daily_volume_shares_latest_basis': adv, 'average_daily_dollar_volume_usd': addv,
                'participation_rate': participation, 'days_to_trade_estimate': position_shares / (adv * participation) if position_shares is not None and adv > 0 else None,
                'basis': 'Daily close times volume estimates dollar volume; days are trading days, not execution guarantees.'}
        except ValueError as exc:
            result['blockers'].append(str(exc))
    result['sources'] = sorted(set(result['sources']))
    return result


def fetch_stooq_response(symbol, security_id, currency, mapping_source_url):
    """Optional end-of-day CSV transport, quarantined until basis is verified.

    Stooq CSV lacks explicit adjustment metadata, so these observations are never
    accepted as unadjusted inputs automatically. No API key is required.
    """
    import urllib.parse
    if currency != 'USD' or not mapping_source_url:
        raise ValueError('verified USD listing mapping required')
    url = 'https://stooq.com/q/d/l/?' + urllib.parse.urlencode({'s': symbol.lower(), 'i': 'd'})
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'CapitalSignal Research hello@ainvestmentbank.ai'}), timeout=30) as response:
        raw = response.read()
        body = raw.decode('utf-8')
        status = response.status
    retrieved = dt.datetime.now(dt.timezone.utc).isoformat()
    output = []
    for row in csv.DictReader(io.StringIO(body)):
        if not row.get('Date'):
            continue
        output.append({'security_id': security_id, 'date': row['Date'], 'close': float(row['Close']),
            'volume': float(row['Volume']), 'currency': currency, 'source_url': url,
            'available_at': retrieved, 'price_basis': 'provider_unspecified', 'volume_basis': 'provider_unspecified',
            'mapping_source_url': mapping_source_url, 'status': 'quarantined_adjustment_basis_unverified'})
    return output, {'source_url': url, 'http_status': status, 'response_sha256': hashlib.sha256(raw).hexdigest(),
        'bytes': len(raw), 'retrieved_at': retrieved, 'observation_count': len(output),
        'browser_challenge': 'verify your browser' in body.lower(),
        'response_excerpt_if_empty': body[:200] if not output else None}


def fetch_stooq(symbol, security_id, currency, mapping_source_url):
    return fetch_stooq_response(symbol, security_id, currency, mapping_source_url)[0]


def acquire(universe, limit=5):
    """Checkpointed public transport, no source-data verification implied."""
    path = OUT/'market_provider_cache.json'
    cache = json.loads(path.read_text()) if path.exists() else {'observations': {}, 'attempts': {}, 'source_checks': []}
    # Inspect the issuer-universe provider itself rather than inventing market values.
    source_url = universe['source_url']
    try:
        import openpyxl
        with urllib.request.urlopen(urllib.request.Request(source_url, headers={'User-Agent': 'CapitalSignal Research hello@ainvestmentbank.ai'}), timeout=30) as response:
            raw = response.read()
            status = response.status
        rows = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True).active.values
        header = next(list(r) for r in rows if r[0] == 'Name' and r[1] == 'Ticker')
        cache['source_checks'] = [{'source_url': source_url, 'http_status': status,
            'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'sha256': hashlib.sha256(raw).hexdigest(),
            'columns': header, 'result': 'Provider supplies ETF shares held, not issuer shares outstanding, raw prices, volume or market values.'}]
    except Exception as exc:
        cache['source_checks'] = [{'source_url': source_url, 'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'error': type(exc).__name__ + ': ' + str(exc)}]
    # Respect source-wide challenges across all symbols and subsequent workers.
    blocked_until = cache.get('provider_blocked_until')
    if blocked_until and dt.datetime.fromisoformat(blocked_until) > dt.datetime.now(dt.timezone.utc):
        return {'attempted_this_run': 0, 'total_securities_attempted': len(cache['attempts']),
            'quarantined_observations': sum(len(x) for x in cache['observations'].values()),
            'cache': str(path.relative_to(ROOT)), 'status': 'provider_challenge_cooldown',
            'provider_blocked_until': blocked_until}
    attempted = 0
    for member in universe['securities']:
        if attempted >= limit:
            break
        if not member.get('cusip') or not member.get('ticker') or member.get('currency') != 'USD':
            continue
        security_id = 'cusip:' + member['cusip']
        previous = cache['attempts'].get(security_id, {})
        if previous.get('retrieved_at'):
            elapsed = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(previous['retrieved_at'])
            if elapsed.total_seconds() < 24*3600:
                continue
        symbol = member['ticker'].lower().replace('-', '.') + '.us'
        evidence = {'security_id': security_id, 'provider_symbol_candidate': symbol,
            'listing_mapping_basis': 'current ETF ticker/CUSIP only; historical listing correspondence unverified',
            'mapping_as_of': universe['as_of'], 'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            observations, response_evidence = fetch_stooq_response(symbol, security_id, 'USD', source_url)
            # A current ticker map establishes no correspondence before this snapshot.
            observations = [o for o in observations if o['date'] >= universe['as_of']]
            cache['observations'][security_id] = observations[-30:]
            evidence.update(response_evidence)
            evidence['retained_observation_count'] = len(cache['observations'][security_id])
            evidence['status'] = 'browser_challenge' if response_evidence.get('browser_challenge') else 'quarantined_adjustment_and_listing_basis' if observations else 'no_usable_observations_returned'
        except Exception as exc:
            evidence.update(status='source_failed', error=type(exc).__name__ + ': ' + str(exc))
            if hasattr(exc, 'code'):
                evidence['http_status'] = exc.code
        source_blocked = evidence.get('status') == 'browser_challenge' or evidence.get('http_status') in (403, 429)
        if source_blocked:
            cache['provider_blocked_until'] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=24)).isoformat()
            cache['provider_block_reason'] = evidence['status']
        cache['attempts'][security_id] = evidence
        attempted += 1
        OUT.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(cache, separators=(',', ':'), allow_nan=False))
        temporary.replace(path)
        if source_blocked:
            break
        time.sleep(.5)
    return {'attempted_this_run': attempted, 'total_securities_attempted': len(cache['attempts']),
        'quarantined_observations': sum(len(x) for x in cache['observations'].values()),
        'cache': str(path.relative_to(ROOT)), 'status': 'provider_blocked' if cache.get('provider_blocked_until') else 'transport_only_verified_input_coverage_unchanged',
        'provider_blocked_until': cache.get('provider_blocked_until')}


def audit_universe(universe, bundle, as_of, window=20):
    """Retain unidentified securities as explicit gaps, never join null IDs."""
    results = []
    for member in universe['securities']:
        if member.get('cusip'):
            result = calculate_security('cusip:' + member['cusip'], bundle, as_of, window=window)
        else:
            result = {'security_id': None, 'as_of': as_of, 'currency': member.get('currency'),
                'market_cap_usd': None, 'ownership_pct_outstanding': None,
                'ownership_pct_float': None, 'liquidity': None,
                'blockers': ['missing_provider_sourced_cusip'], 'sources': []}
        result['ticker'] = member.get('ticker')
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=pathlib.Path, help='Verified JSON market input bundle; see MARKET_INPUTS.md')
    parser.add_argument('--as-of', default=None)
    parser.add_argument('--window', type=int, default=20)
    parser.add_argument('--acquire', action='store_true', help='Attempt checkpointed public transport; unverified observations remain quarantined')
    parser.add_argument('--limit', type=int, default=5, help='Maximum provider symbols attempted per acquisition run')
    args = parser.parse_args()
    universe = json.loads((ROOT/'CapitalSignal/data/fundamentals/universe.json').read_text())
    if args.limit < 1:
        parser.error('limit must be positive')
    acquisition = acquire(universe, args.limit) if args.acquire else None
    as_of = args.as_of or universe['as_of']
    date(as_of)
    input_path = args.input or OUT/'market_inputs.json'
    bundle = json.loads(input_path.read_text()) if input_path.exists() else {}
    if args.input and not input_path.exists():
        parser.error('input bundle does not exist')
    results = audit_universe(universe, bundle, as_of, window=args.window)
    shares = 0
    for file in (ROOT/'CapitalSignal/data/fundamentals/companyfacts').glob('*.json.gz'):
        record = json.loads(gzip.decompress(file.read_bytes()))
        if any(p.get('filed', '9999') <= as_of and p.get('end', '9999') <= as_of for p in record.get('fields', {}).get('shares_outstanding', [])):
            shares += 1
    status = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'as_of': as_of,
        'universe_basis': universe['membership_basis'], 'security_count': len(results),
        'verified_price_count': sum('close_usd' in r and not any(b.startswith('stale_price') for b in r['blockers']) for r in results),
        'class_market_cap_count': sum(r['market_cap_usd'] is not None for r in results),
        'float_denominator_count': sum('float_shares' in r for r in results),
        'liquidity_count': sum(r['liquidity'] is not None for r in results),
        'cached_issuers_with_dated_share_facts': shares,
        'issuer_share_fact_limitation': 'Issuer XBRL share facts are not assigned to a security class without corroboration.',
        'status': 'ready' if results and all(r['market_cap_usd'] is not None and r['liquidity'] is not None and 'float_shares' in r for r in results) else 'blocked_missing_verified_market_inputs',
        'provider_adapter': 'Optional Stooq transport available; adjustment basis remains quarantined.',
        'acquisition': acquisition,
        'results': results}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT/'market_readiness.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(status, separators=(',', ':'), allow_nan=False))
    temporary.replace(path)
    print(json.dumps({k: v for k, v in status.items() if k != 'results'}))


if __name__ == '__main__':
    main()
