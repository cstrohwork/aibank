#!/usr/bin/env python3
"""Unattended SEC worker supervision and recovery of verified checkpoints."""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
from sec_history import ROOT, load, save, retry_due


def gh(*args, capture=True):
    for attempt in range(3):
        result = subprocess.run(['gh', *args], capture_output=capture, text=True)
        if result.returncode == 0:
            return result.stdout if capture else ''
        if attempt < 2:
            time.sleep((15, 45)[attempt])
    raise RuntimeError('GitHub command failed after three attempts: ' + ' '.join(args[:3]))


def api(path):
    return json.loads(gh('api', path))


def parse_time(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))


def decision(runs, status, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if any(run['status'] != 'completed' for run in runs):
        return 'wait', 'An SEC worker is running or queued'
    if status.get('storage_blocked'):
        return 'blocked', 'Archive storage needs attention; checkpoint retained'
    if not retry_due(status.get('next_retry_at'), now):
        return 'cooldown', 'SEC cooldown until ' + status['next_retry_at']
    completed = sorted(runs, key=lambda r: r['created_at'], reverse=True)
    streak = 0
    for run in completed:
        if run.get('conclusion') in ('failure', 'timed_out', 'startup_failure'):
            streak += 1
        elif run.get('conclusion') == 'cancelled':
            continue
        else:
            break
    if completed and streak:
        delay = min(1800, 60 * 2 ** min(streak - 1, 5))
        ready = parse_time(completed[0]['updated_at']) + dt.timedelta(seconds=delay)
        if now < ready:
            return 'cooldown', 'Failure backoff until ' + ready.isoformat()
    return 'dispatch', 'Resume from the latest verified checkpoint; poll live filings when caught up'


def supervise(root=ROOT):
    repo = os.environ['GITHUB_REPOSITORY']
    runs = api(f'repos/{repo}/actions/workflows/sec-history.yml/runs?per_page=30')['workflow_runs']
    action, reason = decision(runs, load(root / 'history/status.json', {}))
    print(json.dumps({'action': action, 'reason': reason}))
    if action == 'dispatch':
        gh('api', '--method', 'POST', f'repos/{repo}/actions/workflows/sec-history.yml/dispatches', '-f', 'ref=main')
    summary = os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as output:
            output.write(f'### SEC automatic recovery\n{action}: {reason}\n')


def recover_folder(root, folder):
    """Union valid immutable originals; never replace an already retained original."""
    state_path = root / 'history/archive_state.json.gz'
    current = load(state_path, {})
    recovered = load(folder / 'archive_state.json.gz', {})
    count = 0
    for accession, record in recovered.items():
        prior = current.get(accession, {})
        if record.get('status') != 'archived':
            continue
        if prior.get('status') == 'archived' and (prior.get('release_asset_url') or (root / prior['raw_file']).exists()):
            continue
        relative = pathlib.PurePosixPath(record.get('raw_file', ''))
        if not relative.parts or relative.parts[0] != 'history' or '..' in relative.parts:
            continue
        source = folder.joinpath(*relative.parts[1:])
        if not source.is_file() or source.is_symlink():
            continue
        digest = hashlib.sha256()
        raw_bytes = 0
        try:
            with gzip.open(source, 'rb') as stream:
                while chunk := stream.read(65536):
                    digest.update(chunk)
                    raw_bytes += len(chunk)
            if digest.hexdigest() != record.get('sha256') or raw_bytes != record.get('raw_bytes'):
                continue
        except (OSError, EOFError):
            continue
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        restored = dict(record)
        # The verified local copy remains available for release publication.
        restored.pop('release_asset_url', None)
        restored.pop('release_asset_sha256', None)
        for name in restored.get('normalized_files', []):
            rel = pathlib.PurePosixPath(name)
            if not rel.parts or rel.parts[:2] != ('history', 'normalized') or '..' in rel.parts:
                raise ValueError('Unsafe normalized checkpoint path')
            source_file = folder.joinpath(*rel.parts[1:])
            if not source_file.is_file():
                restored.pop('normalizer_version', None)
                continue
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_file, target)
        current[accession] = restored
        count += 1
    if count:
        save(state_path, current)
    return count


def restore(root=ROOT):
    repo = os.environ['GITHUB_REPOSITORY']
    runs = api(f'repos/{repo}/actions/workflows/sec-history.yml/runs?per_page=20')['workflow_runs']
    count = 0
    failed = [r for r in runs if r['status'] == 'completed' and r.get('conclusion') in ('failure', 'cancelled', 'timed_out')]
    for run in failed[:5]:
        assets = api(f"repos/{repo}/actions/runs/{run['id']}/artifacts")['artifacts']
        if not any(a['name'] == 'sec-history-checkpoint' and not a['expired'] for a in assets):
            continue
        with tempfile.TemporaryDirectory() as directory:
            gh('run', 'download', str(run['id']), '--repo', repo, '--name', 'sec-history-checkpoint', '--dir', directory)
            count += recover_folder(root, pathlib.Path(directory))
    print('Recovered verified SEC originals from failed-run checkpoints:', count)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('supervise', 'restore'))
    args = parser.parse_args()
    supervise() if args.operation == 'supervise' else restore()
