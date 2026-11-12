"""Publish bounded CUSIP ownership shards instead of one unbounded Git blob."""
import pathlib
from sec_history import save


def write_ownership_index(directory, securities, note):
    directory = pathlib.Path(directory)
    groups = {}
    for cusip, positions in securities.items():
        groups.setdefault(cusip[:2], {})[cusip] = positions
    manifest = []
    for prefix, values in sorted(groups.items()):
        if not prefix.isalnum():
            raise ValueError('Invalid ownership CUSIP prefix')
        filename = 'ownership_by_cusip/' + prefix + '.json'
        save(directory / filename, {'securities': values, 'note': note})
        manifest.append({'prefix': prefix, 'file': filename, 'security_count': len(values)})
    save(directory / 'ownership_by_cusip.json', {
        'schema': 'cusip_ownership_shards_v1', 'shards': manifest,
        'security_count': len(securities), 'note': note,
        'lookup': 'Select the shard matching the first two CUSIP characters; read its securities map'})
