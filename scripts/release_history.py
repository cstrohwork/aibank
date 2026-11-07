#!/usr/bin/env python3
"""Publish checksum-addressed raw SEC archive shards as GitHub release assets."""
import datetime
import hashlib
import io
import json
import os
import pathlib
import subprocess
import tarfile
import tempfile
from sec_history import ROOT, load, save

def package(root, records, output):
    manifest = []
    with tarfile.open(output, 'w') as archive:
        for accession, record in sorted(records.items()):
            file = root / record['raw_file']
            payload = file.read_bytes()
            info = tarfile.TarInfo(record['raw_file'])
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
            manifest.append({'accession': accession, 'member': record['raw_file'],
                'sha256': record['sha256'], 'source': record['source']})
        payload = json.dumps(manifest, sort_keys=True).encode()
        info = tarfile.TarInfo('MANIFEST.json')
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return hashlib.sha256(output.read_bytes()).hexdigest()

def publish(root=ROOT):
    repository = os.environ['GITHUB_REPOSITORY']
    if repository != 'cstrohwork/aibank':
        raise ValueError('Unexpected publication repository')
    state_path = root / 'history' / 'archive_state.json.gz'
    state = load(state_path, {})
    records = {a:r for a,r in state.items() if r.get('status') == 'archived'
        and not r.get('release_asset_url') and (root/r['raw_file']).exists()}
    if not records:
        print('No raw SEC submissions awaiting release publication')
        return
    # Daily releases remain well below GitHub's 1,000 assets/release limit.
    tag = 'sec-history-raw-' + datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    prefix = ['gh', 'release']
    with tempfile.TemporaryDirectory() as directory:
        file = pathlib.Path(directory) / 'archive.tar'
        digest = package(root, records, file)
        target = file.with_name('sec-' + digest[:24] + '.tar')
        file.rename(target)
        args = ['--repo', repository]
        found = subprocess.run(prefix + ['view', tag] + args, capture_output=True)
        if found.returncode:
            subprocess.run(prefix + ['create', tag, '--target', 'main', '--prerelease',
                '--title', 'Capital Signal SEC raw history ' + tag.removeprefix('sec-history-raw-'),
                '--notes', 'Public SEC complete-submission archive shards for the Capital Signal historical dataset. Each shard includes source URLs and SHA-256 checksums in MANIFEST.json. Backfill remains incomplete; consult CapitalSignal/data/history/status.json.'] + args, check=True)
        subprocess.run(prefix + ['upload', tag, str(target), '--clobber'] + args, check=True)
        # Check size and GitHub's digest before removing any local raw file.
        response = subprocess.run(prefix + ['view', tag, '--json', 'assets'] + args,
            check=True, capture_output=True, text=True)
        asset = next(a for a in json.loads(response.stdout)['assets'] if a['name'] == target.name)
        if asset['size'] != target.stat().st_size:
            raise ValueError('Uploaded archive size mismatch')
        expected = asset.get('digest')
        if expected and expected != 'sha256:' + digest:
            raise ValueError('Uploaded archive checksum mismatch')
        url = 'https://github.com/' + repository + '/releases/download/' + tag + '/' + target.name
        for accession, record in records.items():
            state[accession].update(release_asset_url=url, release_asset_sha256=digest)
        save(state_path, state)
        for record in records.values():
            (root/record['raw_file']).unlink()
    status_path = root/'history'/'status.json'
    status = load(status_path, {})
    status.update(raw_storage_backend='GitHub release assets; checksum-addressed archive shards',
        git_raw_bytes=0, storage_blocked=False)
    if status.get('status') == 'storage_blocked':
        status['status'] = 'in_progress'
    save(status_path, status)
    print('Published and verified', len(records), 'SEC submissions:', url)

if __name__ == '__main__':
    publish()
