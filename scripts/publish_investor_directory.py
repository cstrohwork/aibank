#!/usr/bin/env python3
"""Publish cached investor research with explicit evidence limitations."""
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import argparse
import subprocess
from investor_profile_analytics import analyze, render

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / 'CapitalSignal/data'
OUT = ROOT / 'CapitalSignal/spotlight/investors'

def run(batch=2000):
    profiles = json.loads((DATA / 'investor_profiles.json').read_text())['profiles']
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'profiles': {}}
    template = (ROOT / 'CapitalSignal/spotlight/index.html').read_text()
    head = template.split('<header>')[0] + "<style>*{box-sizing:border-box}body{margin:0;background:#edf1f5;color:#1c3050;font:15px/1.55 Arial,sans-serif}.sheet{max-width:1080px;margin:auto;background:#fff;min-height:100vh}header{background:linear-gradient(110deg,#142747,#286895);padding:34px;color:#fff}.brand{letter-spacing:3px;font-size:12px;color:#bbd8eb}h1{font-size:clamp(29px,5vw,45px);margin:12px 0}header a{color:#cde5f5}.layout{display:grid;grid-template-columns:32% 68%}aside{background:#e5ebf0;padding:28px}main{padding:28px 35px}h2{font-size:20px;margin:0 0 14px}h3{margin:26px 0 10px;font-size:14px;text-transform:uppercase;letter-spacing:1px;color:#24658f;border-bottom:2px solid #dbe6ef;padding-bottom:6px}.number{font-size:30px;font-weight:bold;margin:2px 0}.label{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:#55708b}.metric{border-bottom:1px solid #bfcbd6;padding:13px 0}p{margin:0 0 15px}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:9px 6px;border-bottom:1px solid #d6dfe8;text-align:left}td:last-child,th:last-child{text-align:right}a{color:#236994;overflow-wrap:anywhere}.note{font-size:12px;color:#516477}.disclaimer{background:#f1f5f8;padding:15px;border-left:4px solid #527fa2;font-size:12px}@media(max-width:700px){.layout{display:block}aside,main{padding:22px}}</style>"
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    def esc(v):
        return html.escape(str(v if v is not None else 'Unknown'), quote=True)
    def rank(p):
        try:
            value = float(p.get('reported_13f_value_usd') or 0)
        except (ValueError, TypeError):
            value = 0
        verified = p.get('reported_13f_value_verified') is True and p.get('reported_13f_value_source')
        return (bool(verified), value if verified else 0, p.get('latest_report_date') or '')
    index_path = DATA / '13f/index.json'
    filing_dates = {}
    entries = []
    blobs = subprocess.run(['git', 'ls-files', '-s', 'CapitalSignal/data/13f/'], cwd=ROOT, capture_output=True, text=True).stdout
    blob_map = {line.split('\t',1)[1]:line.split()[1] for line in blobs.splitlines() if '\t' in line}
    if index_path.exists():
        entries = json.loads(index_path.read_text()).get('managers', [])
        for entry in entries:
            key = (str(entry.get('manager_cik', '')).zfill(10), entry.get('report_date'))
            filing_dates[key] = max(filing_dates.get(key, ''), entry.get('filing_date') or '')
    for profile in profiles:
        profile['filing_date'] = filing_dates.get((str(profile.get('manager_cik', '')).zfill(10), profile.get('latest_report_date')))
    for profile in profiles:
        cik_key = str(profile.get('manager_cik', '')).zfill(10)
        profile['render_version'] = 'distinct-prior-period-comparison-v3'
        profile['holdings_fingerprints'] = [blob_map.get('CapitalSignal/data/13f/' + str(e.get('file')), '') for e in entries if str(e.get('manager_cik', '')).zfill(10) == cik_key]
    profiles.sort(key=lambda p: (rank(p), p.get('filing_date') or ''), reverse=True)
    # Reserve a quarter of each bounded run for never-published managers.
    # The remaining slots refresh changed profiles; this prevents frequent
    # amendments to large managers from starving initial universe coverage.
    unpublished = []
    refreshes = []
    for p in profiles:
        cik = str(p.get('manager_cik') or '').zfill(10)
        prior = manifest['profiles'].get(cik, {})
        fingerprint = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
        if prior.get('fingerprint') == fingerprint and ((OUT / cik / 'index.html').exists() and (OUT / cik / 'profile.json').exists()):
            continue
        # Back off repeated failures without blocking other managers. A new source
        # fingerprint bypasses the cooldown so new filings can be processed promptly.
        failure = manifest.get('failures', {}).get(cik, {})
        if failure.get('fingerprint') == fingerprint and failure.get('last_attempt_at'):
            try:
                last_attempt = dt.datetime.fromisoformat(failure['last_attempt_at'])
                if last_attempt.tzinfo is None:
                    last_attempt = last_attempt.replace(tzinfo=dt.timezone.utc)
                cooldown = dt.timedelta(minutes=min(360, 5 * (2 ** min(int(failure.get('attempts', 1)) - 1, 7))))
                if dt.datetime.now(dt.timezone.utc) - last_attempt < cooldown:
                    continue
            except (ValueError, TypeError, OverflowError):
                pass
        (unpublished if cik not in manifest['profiles'] else refreshes).append(p)
    reserved = min(len(unpublished), max(1, batch // 4))
    selected = unpublished[:reserved] + refreshes[:max(0, batch - reserved)]
    selected += unpublished[reserved:reserved + max(0, batch - len(selected))]
    selected += refreshes[max(0, batch - reserved):max(0, batch - reserved) + max(0, batch - len(selected))]
    changed = 0
    errors = []
    manifest.setdefault('failures', {})
    for p in selected:
        cik = str(p.get('manager_cik') or '').zfill(10)
        if not re.fullmatch(r'\d{10}', cik):
            errors.append({'id': cik, 'error': 'Invalid CIK'})
            continue
        fingerprint = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
        prior = manifest['profiles'].get(cik, {})
        if prior.get('fingerprint') == fingerprint and ((OUT / cik / 'index.html').exists() and (OUT / cik / 'profile.json').exists()):
            continue
        if changed >= batch:
            continue
        try:
            sources = [s for s in p.get('source_filings', []) if isinstance(s, str) and s.startswith('https://www.sec.gov/')]
            if not sources:
                raise ValueError('No SEC source link')
            analytics = analyze(DATA, cik, p.get('latest_report_date') or '', entries)
            name = p.get('investor_name') or cik
            style = 'Value' if cik == '0001067983' else p.get('investor_style') or 'Pending fundamental coverage'
            orientation = 'Active (IR Resistant)' if cik == '0001067983' else p.get('orientation') or 'Pending fund classification'
            rows = [('CIK', cik), ('Latest cached reporting period', p.get('latest_report_date')),
                    ('Filing date', p.get('filing_date')), ('City', p.get('city')), ('State', p.get('state')), ('Country', p.get('country')),
                    ('Investment style', style), ('Orientation', orientation),
                    ('Style evidence', p.get('style_status')), ('Orientation evidence', p.get('orientation_status')),
                    ('Available reporting periods', ', '.join(p.get('periods_available', [])))]
            body = '<header><h1>' + esc(name) + '</h1><p>Institutional investor profile · SEC public disclosures</p></header><main><section class="panel"><h2>Investor overview</h2><table>'
            sidebar = '<aside><h2>Investor at a glance</h2>' + ''.join('<div class="metric"><div class="label">'+esc(k)+'</div><strong>'+esc(v)+'</strong></div>' for k,v in [('Investor',name),('Reporting period',p.get('latest_report_date')),('Filing date',p.get('filing_date')),('Investment style',style),('Orientation',orientation),('Distinct positions',analytics.get('distinct_positions'))]) + '</aside>'
            body = body.replace('<main>', '<div class="layout">' + sidebar + '<main>')
            body += ''.join('<tr><th style="text-align:left;padding:8px">' + esc(k) + '</th><td>' + esc(v) + '</td></tr>' for k,v in rows)
            body += '</table>' + render(p, analytics)
            body += '<h2>Coverage and verification</h2><p>Profile generated from the current normalized SEC cache. Monetary totals and turnover are withheld pending source-unit and amendment reconciliation. The latest cached reporting period may lag newer filings. Unknown fields indicate missing evidence.</p>'
            body += '<h2>SEC filing sources</h2><ul>' + ''.join('<li><a href="' + esc(s) + '">' + esc(s) + '</a></li>' for s in sources) + '</ul>'
            body += '<p><a href="../">All investor profiles</a> · <a href="profile.json">Profile data</a></p></section></main></div></html>'
            target = OUT / cik
            target.mkdir(exist_ok=True)
            versions = target / 'versions'
            versions.mkdir(exist_ok=True)
            doc = {'manager_cik': cik, 'investor_name': name, 'latest_report_date': p.get('latest_report_date'),
                   'filing_date': p.get('filing_date'), 'city': p.get('city'), 'state': p.get('state'), 'country': p.get('country'),
                   'investor_style': style, 'orientation': orientation, 'source_filings': sources,
                   'evidence_status': 'cached_source_profile_monetary_reconciliation_pending', 'source_fingerprint': fingerprint,
                   'generated_at': now, 'holdings_analytics': analytics, 'reported_13f_value_usd': None, 'annualized_turnover_proxy_pct': None}
            content = json.dumps(doc, indent=2) + '\n'
            (versions / (fingerprint + '.json')).write_text(content)
            (target / 'profile.json').write_text(content)
            (target / 'index.html').write_text(head + body)
            manifest['profiles'][cik] = {'name': name, 'fingerprint': fingerprint, 'report_date': p.get('latest_report_date'), 'generated_at': now}
            manifest['failures'].pop(cik, None)
            changed += 1
        except Exception as exc:
            # Keep a single unexpected analytics/rendering error from halting
            # publication of unrelated managers in this bounded batch.
            errors.append({'id': cik, 'error': f'{type(exc).__name__}: {exc}'})
            failure = manifest['failures'].get(cik, {})
            manifest['failures'][cik] = {'attempts': failure.get('attempts', 0) + 1,
                                         'last_error': str(exc), 'last_attempt_at': now,
                                         'fingerprint': fingerprint}
    remaining = sum(
        1 for p in profiles
        if (manifest['profiles'].get(str(p.get('manager_cik') or '').zfill(10), {}).get('fingerprint')
            != hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
            or not ((OUT / str(p.get('manager_cik') or '').zfill(10) / 'index.html').exists() and (OUT / str(p.get('manager_cik') or '').zfill(10) / 'profile.json').exists()))
    )
    # Separate never-published coverage from changed profiles awaiting refresh.
    # The combined pending count must not be mistaken for undiscovered investors.
    never_published_remaining = sum(1 for p in profiles if str(p.get('manager_cik') or '').zfill(10) not in manifest['profiles'])
    refresh_remaining = remaining - never_published_remaining
    # Persist the next eligible batch in priority order for operational visibility.
    # These are cached disclosure pages, not validated monetary research profiles.
    next_batch = []
    for p in profiles:
        cik = str(p.get('manager_cik') or '').zfill(10)
        fingerprint = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
        if (manifest['profiles'].get(cik, {}).get('fingerprint') != fingerprint
                or not ((OUT / cik / 'index.html').exists() and (OUT / cik / 'profile.json').exists())):
            next_batch.append({'manager_cik': cik, 'report_date': p.get('latest_report_date'),
                               'source_fingerprint': fingerprint,
                               'state': ('failed_retry' if cik in manifest['failures'] else
                                         'pending_initial' if cik not in manifest['profiles'] else 'pending_refresh'),
                               'retry_attempts': manifest['failures'].get(cik, {}).get('attempts', 0)})
        if len(next_batch) >= min(batch, 200):
            break
    # Reconcile the active discovery universe separately from historical pages.
    # A profile left in the manifest is not evidence that its manager remains
    # present in the latest ingested cache.
    active_ciks = {str(p.get('manager_cik') or '').zfill(10) for p in profiles}
    active_generated_count = sum(
        1 for cik in active_ciks
        if cik in manifest['profiles'] and ((OUT / cik / 'index.html').exists() and (OUT / cik / 'profile.json').exists())
    )
    orphaned_profile_count = sum(1 for cik in manifest['profiles'] if cik not in active_ciks)
    failed_pending_count = sum(1 for item in next_batch if item['manager_cik'] in manifest['failures'])
    manifest.update(active_generated_count=active_generated_count,
                    orphaned_profile_count=orphaned_profile_count,
                    failed_pending_next_batch=failed_pending_count)
    manifest.update(next_batch=next_batch, next_batch_count=len(next_batch),
                    profile_evidence_level='cached_sec_disclosure_monetary_reconciliation_pending',
                    never_published_remaining=never_published_remaining, refresh_remaining=refresh_remaining,
                    updated_at=now, cached_investor_count=len(profiles), generated_count=len(manifest['profiles']),
                    changed_this_run=changed, remaining_changed_or_unpublished=remaining,
                    selected_this_run=len(selected), errors=errors)
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    links = ''.join('<li><a href="' + esc(cik) + '/">' + esc(v['name']) + '</a> · ' + esc(v['report_date']) + '</li>' for cik,v in sorted(manifest['profiles'].items(), key=lambda x:x[1]['name']))
    (OUT / 'index.html').write_text(head + '<header><h1>Investor profiles</h1><p>' + str(len(manifest['profiles'])) + ' cached investor profiles. Updates follow ingestion. Monetary reconciliation pending.</p></header><main><section class="panel"><ul>' + links + '</ul></section></main></html>')
    print(json.dumps({k:v for k,v in manifest.items() if k != 'profiles'}))
    return manifest

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch-size', type=int, default=2000)
    run(ap.parse_args().batch_size)
