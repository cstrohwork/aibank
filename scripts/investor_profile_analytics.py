"""Holdings-based profile sections with explicit unit and amendment gates."""
import collections
import json
import math
from html import escape

def holdings(snapshot):
    rows = collections.defaultdict(lambda: {'shares': 0, 'value': 0, 'issuer': ''})
    skipped = 0
    missing_usd_rows = 0
    for h in snapshot.get('holdings', []):
        if h.get('put_call') or h.get('share_type', 'SH') != 'SH':
            continue
        try:
            # Never interpret legacy thousands as dollars, even if the
            # snapshot header declares USD. Missing dollar units invalidate
            # monetary analytics instead of silently understating exposure.
            if h.get('value_usd') is None:
                missing_usd_rows += 1
                raise ValueError('Missing normalized USD holding value')
            value = float(h['value_usd'])
            shares = float(str(h.get('shares', '')).replace(',', ''))
            if not math.isfinite(value) or not math.isfinite(shares) or value < 0 or shares < 0:
                raise ValueError('Invalid holding')
            key = (h['cusip'], h.get('class', ''))
            row = rows[key]
            row['issuer'] = h.get('issuer') or h['cusip']
            row['shares'] += shares
            row['value'] += value
        except (ValueError, TypeError, KeyError):
            skipped += 1
    return rows, skipped

def analyze(data, cik, period, entries):
    matching = sorted([e for e in entries if str(e.get('manager_cik', '')).zfill(10) == cik and e.get('report_date', '') <= period], key=lambda e:e['report_date'])
    snaps = []
    for entry in matching:
        filename = str(entry.get('file', ''))
        if '/' in filename or not filename.endswith('.json'):
            continue
        path = data / '13f' / filename
        if path.exists():
            snap = json.loads(path.read_text())
            if str(snap.get('manager_cik', '')).zfill(10) == cik:
                snaps.append(snap)
    if not snaps or snaps[-1].get('report_date') != period:
        return {'available': False}
    # Multiple accessions for one report period can represent amendments or
    # separate filings. Do not silently use whichever appears last in the index.
    # A source-validated amendment precedence resolver must choose the winner.
    same_period = [s for s in snaps if s.get('report_date') == period]
    if len(same_period) != 1 or same_period[0].get('amendment_review_required'):
        return {'available': False, 'reason': 'Unresolved same-period filing or amendment precedence',
                'report_date': period, 'filing_count': len(same_period)}
    latest = same_period[0]
    rows, skipped = holdings(latest)
    total = sum(x['value'] for x in rows.values())
    ordered = sorted(rows.items(), key=lambda kv:kv[1]['value'], reverse=True)
    # Dollar amounts require an explicit unit declaration and no unresolved amendment.
    usd = latest.get('value_unit') == 'USD' and not latest.get('amendment_review_required') and not skipped and total > 0
    top = [{'cusip': k[0], 'security_class': k[1], 'issuer': v['issuer'], 'shares': v['shares'],
            'value_usd': v['value'] if usd else None, 'weight_pct': round(v['value']/total*100, 2) if usd else None} for k,v in ordered[:10]]
    result = {'available': True, 'report_date': period, 'filing_date': latest.get('filing_date'),
              'accession': latest.get('accession'), 'source': latest.get('source'),
              'distinct_positions': len(rows), 'excluded_invalid_rows': skipped,
              'reported_long_equity_value_usd': total if usd else None,
              'value_basis': 'Normalized cached long common-share rows; not independently reconciled to SEC cover-page totals',
              'weights_basis': 'Weights and concentration require validated USD units, all rows valid, and resolved amendments; excludes options and non-share positions',
              'top_holdings': top, 'top_five_pct': round(sum(v['value'] for _,v in ordered[:5])/total*100,2) if usd else None,
              'top_ten_pct': round(sum(v['value'] for _,v in ordered[:10])/total*100,2) if usd else None,
              'hhi': round(sum((v['value']/total*100)**2 for v in rows.values()),2) if usd else None,
              'changes': None, 'timeline': [{'report_date':s.get('report_date'), 'filing_date':s.get('filing_date'), 'accession':s.get('accession')} for s in snaps]}
    # Compare only the immediately preceding *distinct reporting period*.
    # A second filing for the current period is not a prior-quarter position,
    # and an unresolved amendment in either period invalidates the comparison.
    prior_periods = sorted({x.get('report_date') for x in snaps if x.get('report_date') and x.get('report_date') < period})
    if prior_periods:
        previous_date = prior_periods[-1]
        previous_candidates = [x for x in snaps if x.get('report_date') == previous_date]
        if len(previous_candidates) == 1 and not previous_candidates[0].get('amendment_review_required'):
            before, bad = holdings(previous_candidates[0])
            if usd and previous_candidates[0].get('value_unit') == 'USD' and not bad and not skipped:
                result['changes'] = {'previous_period': previous_date,
                                     'new_positions': len(rows.keys()-before.keys()),
                                     'exited_positions': len(before.keys()-rows.keys()),
                                     'increased_positions': sum(rows[k]['shares']>before[k]['shares'] for k in rows.keys()&before.keys()),
                                     'reduced_positions': sum(rows[k]['shares']<before[k]['shares'] for k in rows.keys()&before.keys())}
    return result

def render(p, a):
    def e(v): return escape(str(v if v is not None else 'Unavailable'), quote=True)
    def pct(v): return e(v)+'%' if v is not None else 'Unavailable'
    def money(v): return '${:,.0f}'.format(v) if v is not None else 'Awaiting unit validation'
    if not a.get('available'):
        return '<h3>Underlying holdings</h3><p>'+e(a.get('reason') or 'No matching holdings snapshot is available for this report period.')+'</p>'
    body = '<h3>Profile summary</h3><p>'+e(p['investor_name'])+' disclosed '+e(a['distinct_positions'])+' distinct long share positions in the '+e(a['report_date'])+' cached reporting period. Top five positions represent '+pct(a['top_five_pct'])+' of available long-share value.</p>'
    body += '<h3>Reported positioning and concentration</h3><p>Normalized long-share value: <b>'+money(a['reported_long_equity_value_usd'])+'</b>. This is not total institutional AUM. Top ten concentration: <b>'+pct(a['top_ten_pct'])+'</b>. HHI (0–10,000): '+e(a['hhi'])+'.</p>'
    body += '<h3>Largest disclosed security positions</h3><div style="overflow:auto"><table><tr><th>Security / CUSIP</th><th>Shares</th><th>Value</th><th>Weight</th></tr>'
    for h in a['top_holdings']:
        body += '<tr><td>'+e(h['issuer'])+'<br>'+e(h['cusip'])+'</td><td>'+e('{:,.0f}'.format(h['shares']))+'</td><td>'+money(h['value_usd'])+'</td><td>'+pct(h['weight_pct'])+'</td></tr>'
    body += '</table></div><h3>Position changes</h3>'
    c = a.get('changes')
    body += ('<p>Versus '+e(c['previous_period'])+': '+e(c['new_positions'])+' new, '+e(c['exited_positions'])+' exited, '+e(c['increased_positions'])+' increased and '+e(c['reduced_positions'])+' reduced positions. Share changes may reflect corporate actions and are not executed trade records.</p>') if c else '<p>Comparable validated snapshots are not yet available.</p>'
    turnover = p.get('annualized_turnover_proxy_pct')
    body += '<h3>Turnover and investment approach</h3><p>Annualized turnover proxy: '+(pct(turnover) if p.get('turnover_verified') is True else 'Awaiting historical unit and corporate-action validation')+'. Style and orientation require holdings fundamentals and verified underlying fund coverage.</p>'
    body += '<h3>Disclosure timeline</h3><table><tr><th>Reporting period</th><th>Filing date</th><th>Accession</th></tr>'+''.join('<tr><td>'+e(x['report_date'])+'</td><td>'+e(x['filing_date'])+'</td><td>'+e(x['accession'])+'</td></tr>' for x in a['timeline'])+'</table>'
    body += '<h3>What this means for issuers</h3><p>Use disclosed position size, concentration and share changes to assess portfolio fit alongside issuer fundamentals and liquidity. Disclosures lag holdings and do not establish current buying intentions.</p><p class="note">'+e(a['value_basis'])+'. '+e(a['weights_basis'])+'. Excluded invalid rows: '+e(a['excluded_invalid_rows'])+'.</p>'
    return body
