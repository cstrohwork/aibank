#!/usr/bin/env python3
"""Resumable, all-form EDGAR catalogue and complete-submission archive.

Filing-date coverage starts 2025-09-30; holdings report dates are filtered
separately. Original accessions are immutable. Completion is measured, not assumed.
"""
import collections
import email.utils
import datetime as dt
import gzip
import hashlib
import io
import tarfile
import functools
import json
import os
import pathlib
import tempfile
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'CapitalSignal' / 'data'
START = os.getenv('SEC_HISTORY_START', '2025-09-30')
PRIORITY = {'13F-HR', '13F-HR/A', 'NPORT-P', 'NPORT-P/A', 'N-PX', 'N-PX/A',
            'SC 13D', 'SC 13D/A', 'SC 13G', 'SC 13G/A', 'SCHEDULE 13D', 'SCHEDULE 13G'}
INVESTOR_FORMS = PRIORITY | {'13F-NT', '13F-NT/A', 'SCHEDULE 13D/A', 'SCHEDULE 13G/A'}
POSITION_FORMS = {'13F-HR', '13F-HR/A', 'NPORT-P', 'NPORT-P/A'}
LAST_REQUEST = 0.0
REQUEST_LOCK = threading.Lock()
NORMALIZER_VERSION = 2
LIVE_FEED_STATUS = {'status': 'not_checked', 'new_accessions': 0}
RUN_ARCHIVE_BUDGET_BYTES = 100_000_000
BATCH_LIMIT_ERRORS = {
    'SEC submission exceeds remaining compressed archive budget',
    'SEC submission exceeded batch time budget',
}

class BatchBudgetExceeded(ValueError):
    """A resumable worker boundary, not a source failure."""


class ArchiveBudget:
    """Thread-safe compressed archive budget shared by download workers."""
    def __init__(self, limit):
        self.limit = limit
        self.used = 0
        self.lock = threading.Lock()

    def reserve(self, amount):
        with self.lock:
            if self.used + amount > self.limit:
                return False
            self.used += amount
            return True

    def release(self, amount):
        with self.lock:
            self.used = max(0, self.used - amount)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, separators=(',', ':'), allow_nan=False).encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == '.gz' else raw)

def load(path, default=None):
    if not path.exists():
        return default
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)

def open_sec(request, deadline=None):
    """Retry transient SEC 503s only; access blocks stop immediately.

    At most three requests, separated by 15/45 seconds or Retry-After.
    Longer requested pauses are left to the next scheduled worker.
    """
    global LAST_REQUEST
    for attempt in range(3):
        # Coordinate all worker request starts under one aggregate SEC rate limiter.
        with REQUEST_LOCK:
            time.sleep(max(0, 0.4 - (time.monotonic() - LAST_REQUEST)))
            LAST_REQUEST = time.monotonic()
        try:
            return urllib.request.urlopen(request, timeout=60)
        except urllib.error.HTTPError as exc:
            if exc.code != 503 or attempt == 2:
                raise
            delay = (15, 45)[attempt]
            value = (exc.headers or {}).get('Retry-After')
            if value:
                try:
                    delay = max(delay, float(value))
                except ValueError:
                    try:
                        when = email.utils.parsedate_to_datetime(value)
                        delay = max(delay, (when - dt.datetime.now(dt.timezone.utc)).total_seconds())
                    except (ValueError, TypeError, OverflowError):
                        raise exc
            if delay > 120 or (deadline is not None and time.monotonic() + delay + 60 >= deadline):
                raise
            print(json.dumps({'event': 'sec_503_retry', 'source': request.full_url,
                              'attempt': attempt + 2, 'pause_seconds': delay}), flush=True)
            exc.close()
            time.sleep(delay)

def fetch(url, limit=80_000_000):
    req = urllib.request.Request(url, headers={
        'User-Agent': os.getenv('SEC_USER_AGENT', 'CapitalSignal Research hello@ainvestmentbank.ai'),
        'Accept-Encoding': 'identity'})
    with open_sec(req) as resp:
        raw = resp.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Response exceeds configured byte limit; requires larger archive storage')
    return raw

def archive_submission(url, path, archive_limit, raw_limit=512_000_000, deadline=None, budget=None):
    """Stream an original into atomic gzip staging with bounded disk and memory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    reserved = 0
    committed = False
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': os.getenv('SEC_USER_AGENT', 'CapitalSignal Research hello@ainvestmentbank.ai'),
            'Accept-Encoding': 'identity'})
        digest, size, prefix = hashlib.sha256(), 0, b''
        with open_sec(req, deadline=deadline) as response:
            expected = response.headers.get('Content-Length')
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as staged:
                temporary = pathlib.Path(staged.name)
                with gzip.GzipFile(fileobj=staged, mode='wb', filename='', mtime=0) as packed:
                    while True:
                        if deadline is not None and time.monotonic() >= deadline:
                            raise BatchBudgetExceeded('SEC submission exceeded batch time budget')
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > raw_limit:
                            raise ValueError('SEC submission exceeds streaming raw byte limit')
                        prefix = (prefix + chunk)[:1000]
                        digest.update(chunk)
                        packed.write(chunk)
                        current = staged.tell()
                        if current > archive_limit:
                            raise BatchBudgetExceeded('SEC submission exceeds remaining compressed archive budget')
                        if budget is not None:
                            growth = current - reserved
                            if growth and not budget.reserve(growth):
                                raise BatchBudgetExceeded('SEC submission exceeds remaining compressed archive budget')
                            reserved = current
                if staged.tell() > archive_limit:
                    raise BatchBudgetExceeded('SEC submission exceeds remaining compressed archive budget')
        if expected is not None and size != int(expected):
            raise ValueError('Incomplete SEC submission: Content-Length mismatch')
        if b'<SEC-DOCUMENT>' not in prefix.upper():
            raise ValueError('Response is not a complete SEC submission')
        result = dict(sha256=digest.hexdigest(), raw_bytes=size,
                      archive_bytes=temporary.stat().st_size)
        temporary.replace(path)
        committed = True
        return result
    finally:
        if not committed and budget is not None and reserved:
            budget.release(reserved)
        if temporary is not None:
            temporary.unlink(missing_ok=True)

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

def parse_current_feed(raw):
    """Parse SEC's Latest Filings Atom feed into accession-addressed catalogue rows."""
    root = ET.fromstring(raw)
    rows = []
    for entry in root.iter():
        if entry.tag.rsplit('}', 1)[-1].lower() != 'entry':
            continue
        values = {}
        for child in entry.iter():
            name = child.tag.rsplit('}', 1)[-1].lower()
            if name in ('id', 'title', 'updated', 'summary') and child.text:
                values.setdefault(name, child.text.strip())
        href = next((node.attrib.get('href', '') for node in entry.iter()
                     if node.tag.rsplit('}', 1)[-1].lower() == 'link'
                     and node.attrib.get('href')), '')
        match = re.search(r'/edgar/data/(\d+)/(\d{18})(?:/|[-.]|$)', href)
        accession_match = re.search(r'(\d{10}-\d{2}-\d{6})',
                                    values.get('id', '') + ' ' + href + ' ' + values.get('summary', ''))
        if not match or not accession_match:
            continue
        cik = match.group(1).zfill(10)
        accession = accession_match.group(1)
        form = next((node.attrib.get('term', '').strip() for node in entry.iter()
                     if node.tag.rsplit('}', 1)[-1].lower() == 'category'
                     and node.attrib.get('term')), '')
        if not form:
            form = values.get('title', '').split(' - ', 1)[0].strip()
        filed = values.get('updated', '')[:10]
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', filed):
            found = re.search(r'Filed:\s*(\d{4}-\d{2}-\d{2})',
                              values.get('summary', ''), re.I)
            filed = found.group(1) if found else ''
        if not filed or not form:
            continue
        rows.append({'cik': cik, 'name': values.get('title', ''),
            'form': form, 'filing_date': filed, 'accession': accession,
            'source': f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}.txt',
            'discovery_source': 'sec_latest_filings_atom',
            'feed_observed_at': dt.datetime.now(dt.timezone.utc).isoformat()})
    return rows


def current_feed_rows(start, known_accessions):
    """Walk newest SEC feed pages until reaching an accession already catalogued."""
    discovered, seen = [], set()
    page_size = 100
    for offset in range(0, 1000, page_size):
        url = ('https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent'
               f'&owner=include&count={page_size}&start={offset}&output=atom')
        page = parse_current_feed(fetch(url, limit=2_000_000))
        if not page:
            break
        overlap = False
        for row in page:
            if row['accession'] in known_accessions or row['accession'] in seen:
                overlap = True
                continue
            seen.add(row['accession'])
            if row['filing_date'] >= start:
                discovered.append(row)
        if overlap or len(page) < page_size:
            break
    return discovered


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
    # The quarterly index is updated nightly. Poll SEC's current-filings feed on
    # every worker run so same-day accepted filings are not held until tomorrow.
    known_accessions = {row['accession'] for row in rows}
    global LIVE_FEED_STATUS
    LIVE_FEED_STATUS = {'status': 'checking', 'new_accessions': 0}
    try:
        live_rows = current_feed_rows(start, known_accessions)
        LIVE_FEED_STATUS = {'status': 'ok', 'new_accessions': len(live_rows)}
        current_key = f'{today.year}Q{(today.month - 1) // 3 + 1}'
        current_path = history / 'catalogue' / (current_key + '.json.gz')
        current_rows = load(current_path, [])
        merged = {row['accession']: row for row in current_rows}
        for row in live_rows:
            merged[row['accession']] = row
        if live_rows:
            save(current_path, sorted(merged.values(),
                key=lambda row: (row['filing_date'], row['accession'])))
            rows = [row for row in rows if row['accession'] not in {x['accession'] for x in live_rows}]
            rows.extend(live_rows)
        print(json.dumps({'event': 'sec_latest_filings_feed',
            'new_accessions': len(live_rows),
            'feed_observed_at': dt.datetime.now(dt.timezone.utc).isoformat()}), flush=True)
    except Exception as exc:
        LIVE_FEED_STATUS = {'status': 'error', 'new_accessions': 0,
            'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'error': str(exc)}
        failures.append({'source': 'sec_latest_filings_atom', 'error': str(exc)})
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
            # Filing-date discovery includes amendments for older report periods.
            # Exclude those before requiring supported holdings or a series ID;
            # zero-asset older filings are valid archived sources, not parse errors.
            document = ET.fromstring(xml)
            date = report_date(field(document, 'repPdDate') or
                               field(document, 'reportDate') or
                               field(document, 'reportingPeriod'))
            if date < start:
                continue
            fund = parse_fund(xml.encode(), row['source'])
            if not fund:
                raise ValueError('No supported N-PORT positions')
            # A standalone identity must match the catalogue registrant too.
            if fund.get('identity_registrant_cik', row['cik']) != row['cik']:
                raise ValueError('N-PORT identity does not match catalogue registrant')
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


def investor_filing_period(rows, state, start, end):
    """Summarize captured investor forms by SEC filing date, without conflating discovery and ingestion."""
    records = [row for row in rows
        if row.get('form') in INVESTOR_FORMS
        and start <= row.get('filing_date', '') <= end]
    by_form = {}
    for form in sorted({row['form'] for row in records}):
        subset = [row for row in records if row['form'] == form]
        archived = [row for row in subset
            if state.get(row['accession'], {}).get('status') == 'archived']
        failed = sum(state.get(row['accession'], {}).get('status') == 'failed'
            for row in subset)
        deferred = sum(state.get(row['accession'], {}).get('status') == 'deferred'
            for row in subset)
        by_form[form] = {
            'discovered': len(subset),
            'archived': len(archived),
            'pending': sum(state.get(row['accession'], {}).get('status')
                not in ('archived', 'failed', 'deferred') for row in subset),
            'failed': failed,
            'deferred': deferred,
            'positions_parsed': sum(
                row['form'] in POSITION_FORMS
                and not state.get(row['accession'], {}).get('normalization_error')
                for row in archived),
        }
    archived = [row for row in records
        if state.get(row['accession'], {}).get('status') == 'archived']
    return {
        'discovered': len(records),
        'archived': len(archived),
        'pending': sum(state.get(row['accession'], {}).get('status')
            not in ('archived', 'failed', 'deferred') for row in records),
        'failed': sum(state.get(row['accession'], {}).get('status') == 'failed'
            for row in records),
        'deferred': sum(state.get(row['accession'], {}).get('status') == 'deferred'
            for row in records),
        'positions_parsed': sum(
            row['form'] in POSITION_FORMS
            and not state.get(row['accession'], {}).get('normalization_error')
            for row in archived),
        'normalization_errors': sum(
            row['form'] in POSITION_FORMS
            and bool(state.get(row['accession'], {}).get('normalization_error'))
            for row in archived),
        'by_form': by_form,
    }


def run(root=ROOT):
    start = START
    dt.date.fromisoformat(start)
    history = root / 'history'
    today = dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo('America/New_York')).date()
    rows, index_errors = catalogue(root, start, today)
    state = load(history / 'archive_state.json.gz', {})
    # Older runs incorrectly treated worker capacity boundaries as source errors.
    # Retain their exact diagnostic history without enforcing an SEC cooldown.
    for record in state.values():
        if record.get('status') == 'failed' and record.get('error') in BATCH_LIMIT_ERRORS:
            record['prior_failure'] = {k: record[k] for k in ('error', 'retry_after') if k in record}
            record['deferred_reason'] = record.pop('error')
            record['status'] = 'deferred'
            record.pop('retry_after', None)
    reparsed=0
    for accession, record in state.items():
        if reparsed>=30:break
        if record.get('status')!='archived' or record.get('form') not in ('13F-HR','13F-HR/A','NPORT-P','NPORT-P/A'):continue
        if record.get('normalizer_version')==NORMALIZER_VERSION and not record.get('normalization_error'):continue
        try:
            if record.get('raw_bytes', 0) > 80_000_000:
                if record['form'] not in ('NPORT-P', 'NPORT-P/A'):
                    raise ValueError('Normalization deferred: original exceeds 80000000-byte parser memory limit')
                from stream_nport import normalize as normalize_stream
                record['normalized_files'] = normalize_stream(root, record, start)
            else:
                original=read_original(root,record)
                record['normalized_files']=normalize(record,original,root,start)
            record['normalizer_version']=NORMALIZER_VERSION
            record.pop('normalization_error',None)
        except Exception as exc:
            record['normalization_error']=str(exc)
        reparsed+=1
    def eligible(row):
        previous = state.get(row['accession'], {})
        if previous.get('status') == 'archived':
            return False
        # The old in-memory downloader rejected these before streaming existed.
        # Retry with the new capability; never override SEC access cooldowns.
        legacy_size = previous.get('error') == 'Response exceeds configured byte limit; requires larger archive storage'
        return legacy_size or previous.get('retry_after', '') <= today.isoformat()
    available = [r for r in rows if eligible(r)]
    # Newest SEC filings outrank legacy retries; within the same filing date, new
    # rows precede failed/deferred rows. This keeps current intake from stalling.
    available.sort(key=lambda r: (
        -int(r['filing_date'].replace('-', '')),
        state.get(r['accession'], {}).get('status') in ('failed', 'deferred'),
        r['accession']))
    priority = [r for r in available if r['form'] in PRIORITY]
    others = [r for r in available if r['form'] not in PRIORITY]
    limit = int(os.getenv('SEC_HISTORY_BATCH', '120'))
    reserved = max(1, limit // 5)
    queue = priority[:limit - reserved] + others[:reserved]
    used = {r['accession'] for r in queue}
    queue += [r for r in available if r['accession'] not in used][:limit - len(queue)]
    downloaded = 0
    download_interruption = None
    batch_deferral = None
    # Git is the current durable backend. Pause before outgrowing it; never
    # silently discard sources or pretend millions of pending filings are loaded.
    storage_limit=int(os.getenv("SEC_HISTORY_STORAGE_BYTES","750000000"))
    stored_bytes=sum(x.get("archive_bytes",0) for x in state.values() if x.get("status")=="archived" and not x.get("release_asset_url"))
    storage_blocked=stored_bytes>=storage_limit
    bytes_saved = 0
    budget_seconds = max(30, min(1200, int(os.getenv('SEC_HISTORY_SECONDS', '1200'))))
    began = time.monotonic()
    bytes_saved = 0
    budget_seconds = max(30, min(1200, int(os.getenv('SEC_HISTORY_SECONDS', '1200'))))
    worker_count = max(1, min(4, int(os.getenv('SEC_HISTORY_WORKERS', '3'))))
    began = time.monotonic()
    shared_budget = ArchiveBudget(min(storage_limit - stored_bytes, RUN_ARCHIVE_BUDGET_BYTES))
    queue_iter = iter(queue)
    inflight = {}
    stop_submitting = storage_blocked

    def submit_next(pool):
        if stop_submitting or time.monotonic() - began >= budget_seconds:
            return False
        try:
            next_row = next(queue_iter)
        except StopIteration:
            return False
        future = pool.submit(
            archive_submission,
            next_row['source'],
            history / 'raw' / next_row['filing_date'][:4] / next_row['cik'] / (next_row['accession'] + '.txt.gz'),
            min(storage_limit - stored_bytes, RUN_ARCHIVE_BUDGET_BYTES),
            deadline=began + budget_seconds,
            budget=shared_budget)
        inflight[future] = next_row
        return True

    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix='sec-archive') as pool:
        for _ in range(worker_count):
            if not submit_next(pool):
                break
        for future in as_completed(inflight):
            row = inflight.pop(future)
            accession = row['accession']
            path = history / 'raw' / row['filing_date'][:4] / row['cik'] / (accession + '.txt.gz')
            try:
                metadata = future.result()
                stored_bytes += metadata['archive_bytes']
                bytes_saved += metadata['archive_bytes']
                record = dict(row, status='archived', raw_file=str(path.relative_to(root)), **metadata)
                try:
                    if row['form'] in ('13F-HR', '13F-HR/A', 'NPORT-P', 'NPORT-P/A'):
                        if metadata['raw_bytes'] > 80_000_000:
                            if row['form'] not in ('NPORT-P', 'NPORT-P/A'):
                                raise ValueError('Normalization deferred: original exceeds 80000000-byte parser memory limit')
                            from stream_nport import normalize as normalize_stream
                            record['normalized_files'] = normalize_stream(root, record, start)
                        else:
                            raw = gzip.decompress(path.read_bytes())
                            record['normalized_files'] = normalize(row, raw, root, start)
                    else:
                        record['normalized_files'] = []
                    record['normalizer_version'] = NORMALIZER_VERSION
                except Exception as exc:
                    record['normalization_error'] = str(exc)
                state[accession] = record
                downloaded += 1
                if downloaded % 10 == 0:
                    print(json.dumps({'event': 'archive_progress', 'downloaded_this_run': downloaded,
                        'batch_budget_seconds': budget_seconds, 'compressed_bytes_this_run': bytes_saved,
                        'parallel_workers': worker_count, 'last_accession': accession}), flush=True)
            except BatchBudgetExceeded as exc:
                state[accession] = dict(state.get(accession, {}))
                state[accession].update(row, status='deferred', deferred_reason=str(exc))
                state[accession].pop('error', None)
                state[accession].pop('retry_after', None)
                if batch_deferral is None:
                    batch_deferral = {'accession': accession, 'source': row['source'], 'reason': str(exc)}
                stop_submitting = True
            except Exception as exc:
                state[accession] = dict(row, status='failed', error=str(exc),
                    retry_after=(today + dt.timedelta(days=1)).isoformat())
                if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 429, 503):
                    download_interruption = {'http_status': exc.code, 'accession': accession,
                        'source': row['source'], 'error': str(exc),
                        'retry_after': state[accession]['retry_after']}
                    stop_submitting = True
            save(history / 'archive_state.json.gz', state)
            if not stop_submitting:
                submit_next(pool)
    save(history / 'archive_state.json.gz', state)
    counts = collections.Counter(r['form'] for r in rows)
    archived = [state[r['accession']] for r in rows if state.get(r['accession'], {}).get('status') == 'archived']
    checked_at = dt.datetime.now(dt.timezone.utc).isoformat()
    quarter_start_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = dt.date(today.year, quarter_start_month, 1).isoformat()
    investor_monitor = {
        'filing_date_timezone': 'America/New_York',
        'as_of_date': today.isoformat(),
        'current_quarter_start': quarter_start,
        'current_day': investor_filing_period(rows, state, today.isoformat(), today.isoformat()),
        'current_quarter': investor_filing_period(rows, state, quarter_start, today.isoformat()),
    }
    failures = [s for s in state.values() if s.get('status') == 'failed']
    parse_errors = [s for s in archived if s.get('normalization_error')]
    previous_status = load(history / 'status.json', {})
    summary = {'start_filing_date': start, 'start_holdings_report_date': start,
        'checked_at': checked_at,
        'updated_at': checked_at,
        'investor_filings': investor_monitor,
        'live_feed': LIVE_FEED_STATUS,
        'catalogued_filings': len(rows), 'forms': dict(counts), 'archived_filings': len(archived),
        'pending_filings': len(rows) - len(archived), 'downloaded_this_run': downloaded, 'batch_budget_seconds': budget_seconds,
        'index_errors': index_errors, 'download_failures': len(failures),
        'download_interruption': download_interruption, 'batch_deferral': batch_deferral,
        'deferred_filings': sum(s.get('status') == 'deferred' for s in state.values()),
        'normalization_failures': len(parse_errors),
        'archive_bytes': sum(x.get('archive_bytes',0) for x in archived), 'git_raw_bytes': stored_bytes, 'storage_limit_bytes': storage_limit,
        'storage_blocked': storage_blocked,
        'status': 'storage_blocked' if storage_blocked else 'complete' if rows and len(archived) == len(rows) and not index_errors and not failures and not parse_errors else 'in_progress',
        'scope': 'All public EDGAR form types by filing date; complete submissions include exhibits. Holdings are filtered separately by report date. Live SEC latest-filings feed is polled during each worker run; quarterly indexes reconcile history. No confidential/unpublished filings.'}
    material_change = bool(downloaded or reparsed or index_errors or failures or download_interruption
        or LIVE_FEED_STATUS.get('status') == 'error'
        or LIVE_FEED_STATUS.get('new_accessions', 0)
        or summary['investor_filings'] != previous_status.get('investor_filings')
        or summary['catalogued_filings'] != previous_status.get('catalogued_filings')
        or summary['forms'] != previous_status.get('forms')
        or summary['normalization_failures'] != previous_status.get('normalization_failures')
        or summary['storage_blocked'] != previous_status.get('storage_blocked'))
    if not material_change and previous_status.get('updated_at'):
        summary['updated_at'] = previous_status['updated_at']
    save(history / 'status.json', summary)
    print(json.dumps(summary, indent=2))
    if index_errors or failures or parse_errors:
        print('WARNING: retained source and retry/error records require review')
    if download_interruption:
        raise SystemExit('SEC access interrupted: HTTP ' + str(download_interruption['http_status']) +
                         '; progress and retry evidence saved in history/status.json')
    if not rows or (not downloaded and failures and not batch_deferral):
        raise SystemExit('No forward progress; inspect SEC access and history status')

if __name__ == '__main__':
    run()
