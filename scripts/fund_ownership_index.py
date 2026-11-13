"""Publish ownership pages with a hard serialized size limit."""
import json
import pathlib
from sec_history import save


def write_ownership_index(directory, securities, note, max_bytes=8_000_000):
    directory = pathlib.Path(directory)
    groups = {}
    for cusip, positions in securities.items():
        groups.setdefault(cusip[:2], {})[cusip] = positions
    manifest, retained = [], set()
    base_size = len(json.dumps({'securities': {}, 'note': note}, separators=(',', ':'), allow_nan=False).encode())
    for prefix, values in sorted(groups.items()):
        if not prefix.isalnum():
            raise ValueError('Invalid ownership CUSIP prefix')
        page, size, number = {}, base_size, 0
        def flush():
            nonlocal page, size, number
            if not page:
                return
            filename = f'ownership_by_cusip/{prefix}-{number:05d}.json'
            path = directory / filename
            save(path, {'securities': page, 'note': note})
            if path.stat().st_size > max_bytes:
                raise ValueError('Ownership page exceeded configured byte limit')
            retained.add(path.name)
            manifest.append({'prefix': prefix, 'file': filename, 'security_count': len(page)})
            number += 1
            page, size = {}, base_size
        for cusip, positions in sorted(values.items()):
            for position in positions:
                # Conservative overhead includes the key, array, and separators.
                growth = len(json.dumps(position, separators=(',', ':'), allow_nan=False).encode()) + len(json.dumps(cusip).encode()) + 16
                if base_size + growth > max_bytes:
                    raise ValueError('One ownership position exceeds configured page limit')
                if page and size + growth > max_bytes:
                    flush()
                page.setdefault(cusip, []).append(position)
                size += growth
        flush()
    save(directory / 'ownership_by_cusip.json', {
        'schema': 'cusip_ownership_shards_v1', 'shards': manifest,
        'security_count': len(securities), 'note': note,
        'max_shard_bytes': max_bytes,
        'lookup': 'Select all shards matching the first two CUSIP characters; concatenate positions per CUSIP'})
    # Remove obsolete oversized or previous-generation pages before Git publication.
    for path in (directory / 'ownership_by_cusip').glob('*.json'):
        if path.name not in retained:
            path.unlink()
