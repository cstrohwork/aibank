#!/usr/bin/env python3
"""Publish only ingestion-owned inputs, merging caches on the latest branch head.

No rebase of generated reports. The CLI resets a disposable Actions checkout;
it refuses to run in a developer checkout.
"""
import argparse
import collections
import datetime as dt
import gzip
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from ingest_sp1500_fundamentals import snapshot

DATA = pathlib.Path('CapitalSignal/data/fundamentals')

def read(path):
    blob = path.read_bytes()
    return json.loads(gzip.decompress(blob) if path.suffix == '.gz' else blob)

def stamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Unknown retrieval timezone')
    if parsed > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
        raise ValueError('Future retrieval timestamp')
    return parsed

def rank(path, relative):
    obj = read(path)
    if relative.parts[0] == 'companyfacts':
        if obj.get('cik') != path.name.split('.')[0] or not isinstance(obj.get('fields'), dict):
            raise ValueError('Invalid company cache identity/fields')
        return (stamp(obj['retrieved_at']),)
    if relative.name == 'universe.json' or relative.parts[0] == 'universes':
        if not obj.get('securities'):
            raise ValueError('Empty universe')
        return (dt.date.fromisoformat(obj['as_of']), stamp(obj['retrieved_at']))
    return (stamp(obj['at']),)

def input_files(folder):
    for name in ('universe.json', 'last_attempt.json'):
        p = folder/name
        if p.is_file(): yield p
    for pattern in ('companyfacts/[0-9]*.json.gz', 'universes/*.json'):
        yield from sorted(folder.glob(pattern))

def merge_inputs(source, target):
    """Union valid issuer caches; retain newer remote observations on collisions."""
    copied = 0
    for path in input_files(source):
        relative = path.relative_to(source)
        incoming = rank(path, relative)
        destination = target/relative
        current = None
        if destination.exists():
            try: current = rank(destination, relative)
            except (OSError, ValueError, KeyError, TypeError, EOFError): pass
        if current is not None and incoming <= current:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        copied += 1
    return copied

def summarize(folder, evidence):
    universe = read(folder/'universe.json')
    members = universe['securities']
    required = sorted({s['cik'] for s in members if s.get('cik')})
    pending, invalid, coverage = [], [], collections.Counter()
    count = fresh = 0
    for cik in required:
        path = folder/'companyfacts'/(cik+'.json.gz')
        if not path.exists():
            pending.append(cik); continue
        try:
            record = read(path)
            rank(path, pathlib.Path('companyfacts')/path.name)
            facts = snapshot(record, universe['as_of'])
            count += 1
            fresh += (dt.datetime.now(dt.timezone.utc)-stamp(record['retrieved_at'])).total_seconds() < 86400
            coverage.update(facts.keys())
        except (OSError, ValueError, KeyError, TypeError, EOFError) as exc:
            pending.append(cik); invalid.append({'cik':cik,'error':str(exc)})
    errors = {e['cik']: e for e in evidence.get('failed_attempts', []) if e.get('cik') in pending}
    status = dict(evidence)
    status.update(updated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        status='complete_with_gaps' if not pending else 'partial',
        universe_as_of=universe['as_of'], universe_basis=universe.get('membership_basis'),
        security_count=len(members), mapped_security_count=sum(bool(s.get('cik')) for s in members),
        unique_mapped_issuers=len(required), ingested_issuers=count, fresh_issuers=fresh,
        pending_issuers=pending, failed_attempts=list(errors.values()), invalid_records=invalid,
        unmapped_securities=[s for s in members if not s.get('cik')], field_issuer_coverage=dict(coverage),
        publication_basis='Validated union of checkpoint and current branch caches; generated analytics owned by intelligence workflow')
    (folder/'status.json').write_text(json.dumps(status,separators=(',',':')))
    return status

def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()

def publish(root, checkpoint):
    root, checkpoint = pathlib.Path(root).resolve(), pathlib.Path(checkpoint).resolve()
    # Check source integrity before the first reset, and preserve it outside checkout.
    with tempfile.TemporaryDirectory(prefix='fundamental-checkpoint-') as directory:
        saved = pathlib.Path(directory)
        rank(checkpoint/'universe.json', pathlib.Path('universe.json'))
        merge_inputs(checkpoint, saved)
        evidence = read(checkpoint/'status.json') if (checkpoint/'status.json').exists() else {}
        for attempt in range(5):
            git(root, 'fetch', 'origin', 'main')
            git(root, 'reset', '--hard', 'origin/main')
            folder = root/DATA
            merge_inputs(saved, folder)
            latest = read(folder/'status.json') if (folder/'status.json').exists() else {}
            combined = dict(latest, **evidence)
            combined['failed_attempts'] = latest.get('failed_attempts', []) + evidence.get('failed_attempts', [])
            report = summarize(folder, combined)
            paths = [str(DATA/p.relative_to(folder)) for p in input_files(folder)] + [str(DATA/'status.json')]
            git(root, 'add', '--', *paths)
            if not git(root, 'diff', '--cached', '--name-only'):
                return report
            git(root, 'commit', '-m', 'Publish validated fundamental cache checkpoint')
            result = subprocess.run(['git','push','origin','HEAD:main'],cwd=root,capture_output=True,text=True)
            if result.returncode == 0:
                return report
            if attempt == 4:
                raise RuntimeError('Publication rejected after five fresh-head merges: '+result.stderr[-1000:])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=pathlib.Path, required=True)
    args = parser.parse_args()
    if os.getenv('GITHUB_ACTIONS') != 'true':
        parser.error('Publisher requires a disposable GitHub Actions checkout')
    root = pathlib.Path(__file__).resolve().parents[1]
    report = publish(root, args.checkpoint)
    print(json.dumps({k:report[k] for k in ('status','ingested_issuers','unique_mapped_issuers','pending_issuers')}))

if __name__ == '__main__': main()
