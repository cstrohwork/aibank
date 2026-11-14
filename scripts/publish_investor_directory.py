#!/usr/bin/env python3
"""Publish cached investor research with explicit evidence limitations."""
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import argparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / 'CapitalSignal/data'
OUT = ROOT / 'CapitalSignal/spotlight/investors'

def run(batch=2000):
    profiles = json.loads((DATA / 'investor_profiles.json').read_text())['profiles']
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'profiles': {}}
    template = (ROOT / 'CapitalSignal/spotlight/index.html').read_text()
    head = template.split('<header>')[0]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    def esc(v):
        return html.escape(str(v if v is not None else 'Unknown'), quote=True)
    def rank(p):
        try:
            value = float(p.get('reported_13f_value_usd') or 0)
        except (ValueError, TypeError):
            value = 0
        return (p.get('latest_report_date') or '', value)
    profiles.sort(key=rank, reverse=True)
    changed = 0
    errors = []
    for p in profiles:
        cik = str(p.get('manager_cik') or '').zfill(10)
        if not re.fullmatch(r'\d{10}', cik):
            errors.append({'id': cik, 'error': 'Invalid CIK'})
            continue
        fingerprint = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
        prior = manifest['profiles'].get(cik, {})
        if prior.get('fingerprint') == fingerprint and (OUT / cik / 'index.html').exists():
            continue
        if changed >= batch:
            continue
        try:
            sources = [s for s in p.get('source_filings', []) if isinstance(s, str) and s.startswith('https://www.sec.gov/')]
            if not sources:
                raise ValueError('No SEC source link')
            name = p.get('investor_name') or cik
            style = 'Value' if cik == '0001067983' else p.get('investor_style') or 'Pending fundamental coverage'
            orientation = 'Active (IR Resistant)' if cik == '0001067983' else p.get('orientation') or 'Pending fund classification'
            rows = [('CIK', cik), ('Latest cached reporting period', p.get('latest_report_date')),
                    ('City', p.get('city')), ('State', p.get('state')), ('Country', p.get('country')),
                    ('Investment style', style), ('Orientation', orientation),
                    ('Style evidence', p.get('style_status')), ('Orientation evidence', p.get('orientation_status')),
                    ('Available reporting periods', ', '.join(p.get('periods_available', [])))]
            body = '<header><h1>' + esc(name) + '</h1><p>Institutional investor profile · SEC public disclosures</p></header><main><section class="panel"><h2>Investor overview</h2><table>'
            body += ''.join('<tr><th style="text-align:left;padding:8px">' + esc(k) + '</th><td>' + esc(v) + '</td></tr>' for k,v in rows)
            body += '</table><h2>Coverage and verification</h2><p>Profile generated from the current normalized SEC cache. Monetary totals and turnover are withheld pending source-unit and amendment reconciliation. The latest cached reporting period may lag newer filings. Unknown fields indicate missing evidence.</p>'
            body += '<h2>SEC filing sources</h2><ul>' + ''.join('<li><a href="' + esc(s) + '">' + esc(s) + '</a></li>' for s in sources) + '</ul>'
            body += '<p><a href="../">All investor profiles</a> · <a href="profile.json">Profile data</a></p></section></main></html>'
            target = OUT / cik
            target.mkdir(exist_ok=True)
            versions = target / 'versions'
            versions.mkdir(exist_ok=True)
            doc = {'manager_cik': cik, 'investor_name': name, 'latest_report_date': p.get('latest_report_date'),
                   'city': p.get('city'), 'state': p.get('state'), 'country': p.get('country'),
                   'investor_style': style, 'orientation': orientation, 'source_filings': sources,
                   'evidence_status': 'cached_source_profile_monetary_reconciliation_pending', 'source_fingerprint': fingerprint,
                   'generated_at': now, 'reported_13f_value_usd': None, 'annualized_turnover_proxy_pct': None}
            content = json.dumps(doc, indent=2) + '\n'
            (versions / (fingerprint + '.json')).write_text(content)
            (target / 'profile.json').write_text(content)
            (target / 'index.html').write_text(head + body)
            manifest['profiles'][cik] = {'name': name, 'fingerprint': fingerprint, 'report_date': p.get('latest_report_date'), 'generated_at': now}
            changed += 1
        except (ValueError, TypeError, OSError) as exc:
            errors.append({'id': cik, 'error': str(exc)})
    manifest.update(updated_at=now, cached_investor_count=len(profiles), generated_count=len(manifest['profiles']), changed_this_run=changed, errors=errors)
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    links = ''.join('<li><a href="' + esc(cik) + '/">' + esc(v['name']) + '</a> · ' + esc(v['report_date']) + '</li>' for cik,v in sorted(manifest['profiles'].items(), key=lambda x:x[1]['name']))
    (OUT / 'index.html').write_text(head + '<header><h1>Investor profiles</h1><p>' + str(len(manifest['profiles'])) + ' cached investor profiles. Updates follow ingestion. Monetary reconciliation pending.</p></header><main><section class="panel"><ul>' + links + '</ul></section></main></html>')
    print(json.dumps({k:v for k,v in manifest.items() if k != 'profiles'}))
    return manifest

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch-size', type=int, default=2000)
    run(ap.parse_args().batch_size)
