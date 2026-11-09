#!/usr/bin/env python3
"""Resumable, all-form EDGAR catalogue and complete-submission archive.

Filing-date coverage starts 2025-09-30; holdings report dates are filtered
separately. Original accessions are immutable. Completion is measured, not assumed.
"""
import collections
import datetime as dt
import gzip
import hashlib
import io
import tarfile
import functools
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'CapitalSignal' / 'data'
START = os.getenv('SEC_HISTORY_START', '2025-09-30')
PRIORITY = {'13F-HR', '13F-HR/A', 'NPORT-P', 'NPORT-P/A', 'N-PX', 'N-PX/A',
            'SC 13D', 'SC 13D/A', 'SC 13G', 'SC 13G/A', 'SCHEDULE 13D', 'SCHEDULE 13G'}
LAST_REQUEST = 0.0
NORMALIZER_VERSION = 2

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, separators=(',', ':'), allow_nan=False).encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == '.gz' else raw)

def load(path, default=None):
    if not path.exists():
        return default
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)

def fetch(url, limit=80_000_000):
    global LAST_REQUEST
    time.sleep(max(0, 0.4 - (time.monotonic() - LAST_REQUEST)))
    LAST_REQUEST = time.monotonic()
    req = urllib.request.Request(url, headers={
        'User-Agent': os.getenv('SEC_USER_AGENT', 'CapitalSignal Research hello@ainvestmentbank.ai'),
        'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Response exceeds configured byte limit; requires larger archive storage')
    return raw

def quarters(start, end):
    day = dt.date.fromisoformat(start)
    year, quarter = day.year, (day.month - 1) // 3 + 1
    while (year, quarter) <= (end.year, (end.month - 1) // 3 + 1):
        yield year, quarter
        year, quarter = (year + 1, 1) if quarter == 4 else (year, quarter + 1)

def parse_master(raw, start):
    result = {}
    for line in raw.decode('latin-1').splitlines():
        parts = line.split('|')
        if len(parts) != 5 or not parts[0].isdigit():
            continue
        cik, name, form, filed, filename = parts
        if filed < start:
            continue
        match = re.fullmatch(r'edgar/data/\d+/(\d{10}-\d{2}-\d{6})\.txt', filename)
        if not match:
            continue
        accession = match.group(1)
        result[accession] = {'cik': cik.zfill(10), 'name': name, 'form': form,
            'filing_date': filed, 'accession': accession,
            'source': 'https://www.sec.gov/Archives/' + filename}
    return sorted(result.values(), key=lambda x: (x['filing_date'], x['accession']))

def catalogue(root, start, today):
    history = root / 'history'
    rows, failures = [], []
    for year, quarter in quarters(start, today):
        key = f'{year}Q{quarter}'
        path = history / 'catalogue' / (key + '.json.gz')
        meta_path = history / 'catalogue' / (key + '.meta.json')
        meta = load(meta_path, {})
        # Recheck historical indexes weekly for SEC post-acceptance corrections.
        fetched = meta.get('fetched_date', '1900-01-01')
        stale = (today - dt.date.fromisoformat(fetched)).days >= 7
        current = (year, quarter) == (today.year, (today.month - 1) // 3 + 1)
        if not path.exists() or stale or (current and fetched != today.isoformat()):
            url = f'https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx'
            try:
                entries = parse_master(fetch(url), start)
                if not entries:
                    raise ValueError('Empty filing catalogue')
                save(path, entries)
                save(meta_path, {'source': url, 'fetched_date': today.isoformat(), 'filings': len(entries)})
            except Exception as exc:
                failures.append({'quarter': key, 'error': str(exc)})
        rows.extend(load(path, []))
    return rows, failures

def documents(raw):
    text = raw.decode('utf-8', errors='replace')
    for block in re.findall(r'<DOCUMENT>(.*?)</DOCUMENT>', text, flags=re.I | re.S):
        kind = re.search(r'<TYPE>\s*([^\r\n<]+)', block, re.I)
        xml = re.search(r'<XML>\s*(.*?)\s*</XML>', block, flags=re.I | re.S)
        if xml:
            yield kind.group(1).strip().upper() if kind else '', xml.group(1)

def field(node, name):
    for child in node.iter():
        if child.tag.rsplit('}', 1)[-1].lower() == name.lower():
            return (child.text or '').strip()
    return ''

def report_date(value):
    for fmt in ('%Y-%m-%d', '%m-%d-%Y', '%m/%d/%Y', '%Y%m%d'):
        try:
            return dt.datetime.strptime(value[:10], fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError('Invalid/missing report date: ' + value)

def normalize(row, raw, root, start):
    from refresh_13f import parse as parse_13f
    from refresh_funds import parse as parse_fund
    parsed = list(documents(raw))
    base = dict(row)
    paths = []
    if row['form'] in ('13F-HR', '13F-HR/A'):
        cover = next((ET.fromstring(xml) for kind, xml in parsed if kind in ('13F-HR', '13F-HR/A')), None)
        if cover is None:
            raise ValueError('13F cover XML missing')
        date = report_date(field(cover, 'reportCalendarOrQuarter') or field(cover, 'periodOfReport'))
        if date < start:
            return []
        holdings = []
        for kind, xml in parsed:
            holdings.extend(parse_13f(xml.encode()))
        if not holdings:
            raise ValueError('13F holdings XML missing')
        for h in holdings:
            # All requested filings are after the SEC dollar-unit change in 2023.
            h['value_usd'] = h['value_thousands']
        manager = next((n for n in cover.iter() if n.tag.rsplit('}', 1)[-1].lower() == 'filingmanager'), cover)
        base.update(manager_cik=row['cik'], manager_name=field(manager, 'name') or row['name'],
            report_date=date, holdings=holdings, value_unit='USD',
            legacy_value_thousands_field_contains='USD',
            amendment_type=field(cover, 'amendmentType').upper(),
            city=field(manager, 'city') or None, state_or_country=field(manager, 'stateOrCountry') or None)
        path = root / 'history' / 'normalized' / '13f' / (row['accession'] + '.json.gz')
        save(path, base)
        paths.append(str(path.relative_to(root)))
    elif row['form'] in ('NPORT-P', 'NPORT-P/A'):
        for kind, xml in parsed:
            if kind not in ('NPORT-P', 'NPORT-P/A'):
                continue
            fund = parse_fund(xml.encode(), row['source'])
            if not fund:
                raise ValueError('No supported N-PORT positions')
            date = report_date(fund['report_date'])
            if date < start:
                continue
            if not re.fullmatch(r'S\d+', fund['series_id']):
                raise ValueError('Missing/invalid N-PORT series identifier')
            fund.update(registrant_cik=row['cik'], registrant_name=row['name'],
                accession=row['accession'], form=row['form'], filing_date=row['filing_date'], report_date=date)
            path = root / 'history' / 'normalized' / 'funds' / (row['accession'] + '.json.gz')
            save(path, fund)
            paths.append(str(path.relative_to(root)))
        if not paths:
            # A reporting period before the cutoff is an intentional exclusion.
            if not any(kind in ('NPORT-P', 'NPORT-P/A') for kind, xml in parsed):
                raise ValueError('N-PORT XML missing')
    return paths

def submission_rows(submission, reader, start):
    chunks=[submission.get("filings",{}).get("recent",{})]
    for item in submission.get("filings",{}).get("files",[]):
        if item.get("filingTo", "9999-12-31") >= start:
            chunks.append(json.loads(reader("https://data.sec.gov/submissions/"+item["name"])))
    rows={}
    for chunk in chunks:
        for i, accession in enumerate(chunk.get("accessionNumber", [])):
            rows[accession]={k: values[i] if i<len(values) else "" for k,values in chunk.items() if isinstance(values,list)}
    return list(rows.values())


@functools.lru_cache(maxsize=2)
def release_bytes(url, digest):
    raw=fetch(url,limit=100_000_000)
    if hashlib.sha256(raw).hexdigest()!=digest:
        raise ValueError("Release shard checksum mismatch")
    return raw

def read_original(root, record):
    path=root/record["raw_file"]
    if path.exists():
        raw=gzip.decompress(path.read_bytes())
    else:
        payload=release_bytes(record["release_asset_url"],record["release_asset_sha256"])
        with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
            member=archive.extractfile(record["raw_file"])
            if member is None:raise ValueError("SEC submission missing from release shard")
            raw=gzip.decompress(member.read())
    if hashlib.sha256(raw).hexdigest()!=record["sha256"]:
        raise ValueError("Original SEC submission checksum mismatch")
    return raw


def run(root=ROOT):
    start = START
    dt.date.fromisoformat(start)
    history = root / 'history'
    today = dt.datetime.now(dt.timezone.utc).date()
    rows, index_errors = catalogue(root, start, today)
    state = load(history / 'archive_state.json.gz', {})
    reparsed=0
    for accession, record in state.items():
        if reparsed>=30:break
        if record.get('status')!='archived' or record.get('form') not in ('13F-HR','13F-HR/A','NPORT-P','NPORT-P/A'):continue
        if record.get('normalizer_version')==NORMALIZER_VERSION and not record.get('normalization_error'):continue
        try:
            original=read_original(root,record)
            record['normalized_files']=normalize(record,original,root,start)
            record['normalizer_version']=NORMALIZER_VERSION
            record.pop('normalization_error',None)
        except Exception as exc:
            record['normalization_error']=str(exc)
        reparsed+=1
    available = [r for r in rows if state.get(r['accession'], {}).get('status') != 'archived'
                 and state.get(r['accession'], {}).get('retry_after', '') <= today.isoformat()]
    priority = [r for r in available if r['form'] in PRIORITY]
    others = [r for r in available if r['form'] not in PRIORITY]
    limit = int(os.getenv('SEC_HISTORY_BATCH', '120'))
    reserved = max(1, limit // 5)
    queue = priority[:limit - reserved] + others[:reserved]
    used = {r['accession'] for r in queue}
    queue += [r for r in available if r['accession'] not in used][:limit - len(queue)]
    downloaded = 0
    download_interruption = None
    # Git is the current durable backend. Pause before outgrowing it; never
    # silently discard sources or pretend millions of pending filings are loaded.
    storage_limit=int(os.getenv("SEC_HISTORY_STORAGE_BYTES","750000000"))
    stored_bytes=sum(x.get("archive_bytes",0) for x in state.values() if x.get("status")=="archived" and not x.get("release_asset_url"))
    storage_blocked=stored_bytes>=storage_limit
    bytes_saved = 0
    began = time.monotonic()
    for row in queue:
        if storage_blocked or time.monotonic() - began > 1200 or bytes_saved >= 60_000_000:
            break
        accession = row['accession']
        path = history / 'raw' / row['filing_date'][:4] / row['cik'] / (accession + '.txt.gz')
        try:
            raw = gzip.decompress(path.read_bytes()) if path.exists() else fetch(row['source'])
            if b'<SEC-DOCUMENT>' not in raw[:1000].upper():
                raise ValueError('Response is not a complete SEC submission')
            packed = gzip.compress(raw, mtime=0)
            if stored_bytes+len(packed)>storage_limit:
                storage_blocked=True
                break
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(packed)
            stored_bytes+=len(packed)
            bytes_saved += len(packed)
            record = dict(row, status='archived', raw_file=str(path.relative_to(root)),
                sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw), archive_bytes=len(packed))
            try:
                record['normalized_files'] = normalize(row, raw, root, start)
                record['normalizer_version'] = NORMALIZER_VERSION
            except Exception as exc:
                record['normalization_error'] = str(exc)
            state[accession] = record
            downloaded += 1
        except Exception as exc:
            state[accession] = dict(row, status='failed', error=str(exc),
                retry_after=(today + dt.timedelta(days=1)).isoformat())
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 429, 503):
                # A service outage is not an accession-specific parse failure.
                # Stop requests, persist prior progress, and expose the interruption.
                download_interruption = {'http_status': exc.code, 'accession': accession,
                    'source': row['source'], 'error': str(exc),
                    'retry_after': state[accession]['retry_after']}
                break
        save(history / 'archive_state.json.gz', state)
    save(history / 'archive_state.json.gz', state)
    counts = collections.Counter(r['form'] for r in rows)
    archived = [state[r['accession']] for r in rows if state.get(r['accession'], {}).get('status') == 'archived']
    failures = [s for s in state.values() if s.get('status') == 'failed']
    parse_errors = [s for s in archived if s.get('normalization_error')]
    summary = {'start_filing_date': start, 'start_holdings_report_date': start,
        'updated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'catalogued_filings': len(rows), 'forms': dict(counts), 'archived_filings': len(archived),
        'pending_filings': len(rows) - len(archived), 'downloaded_this_run': downloaded,
        'index_errors': index_errors, 'download_failures': len(failures),
        'download_interruption': download_interruption,
        'normalization_failures': len(parse_errors),
        'archive_bytes': sum(x.get('archive_bytes',0) for x in archived), 'git_raw_bytes': stored_bytes, 'storage_limit_bytes': storage_limit,
        'storage_blocked': storage_blocked,
        'status': 'storage_blocked' if storage_blocked else 'complete' if rows and len(archived) == len(rows) and not index_errors else 'in_progress',
        'scope': 'All public EDGAR form types by filing date; complete submissions include exhibits. Holdings are filtered separately by report date. Catalogue current through SEC index publication, not intraday. No confidential/unpublished filings.'}
    save(history / 'status.json', summary)
    print(json.dumps(summary, indent=2))
    if index_errors or failures or parse_errors:
        print('WARNING: retained source and retry/error records require review')
    if download_interruption:
        raise SystemExit('SEC access interrupted: HTTP ' + str(download_interruption['http_status']) +
                         '; progress and retry evidence saved in history/status.json')
    if not rows or (not downloaded and failures):
        raise SystemExit('No forward progress; inspect SEC access and history status')

if __name__ == '__main__':
    run()

