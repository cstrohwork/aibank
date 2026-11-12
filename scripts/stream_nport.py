"""Normalize large N-PORT originals with bounded reads and disk-backed XML.

Original/shard checksums are verified before publishing normalized data. The
512 MB original and 500,000-position limits remain explicit capacity boundaries.
"""
import contextlib
import gzip
import hashlib
import io
import pathlib
import re
import tarfile
import tempfile
import xml.etree.ElementTree as ET

from refresh_funds import fund_identity, local, parse_position, val


@contextlib.contextmanager
def original_stream(root, record):
    from sec_history import release_bytes
    path = root / record['raw_file']
    if path.exists():
        with gzip.open(path, 'rb') as stream:
            yield stream
    else:
        payload = release_bytes(record['release_asset_url'], record['release_asset_sha256'])
        with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
            member = archive.extractfile(record['raw_file'])
            if member is None:
                raise ValueError('SEC submission missing from release shard')
            with member, gzip.GzipFile(fileobj=member) as stream:
                yield stream


def extract_xml(stream, output, expected_sha256, raw_limit=512_000_000):
    """Locate primary N-PORT XML across chunk boundaries; hash the whole source."""
    mode, buffer = 'seek', b''
    digest, size = hashlib.sha256(), 0
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
        if size > raw_limit:
            raise ValueError('N-PORT original exceeds streaming raw byte limit')
        if mode == 'done':
            continue
        buffer += chunk
        while buffer:
            upper = buffer.upper()
            if mode == 'seek':
                at = upper.find(b'<DOCUMENT>')
                if at < 0:
                    buffer = buffer[-10:]
                    break
                buffer, mode = buffer[at + 10:], 'header'
            elif mode == 'header':
                at, end = upper.find(b'<XML>'), upper.find(b'</DOCUMENT>')
                if end >= 0 and (at < 0 or end < at):
                    buffer, mode = buffer[end + 11:], 'seek'
                elif at >= 0:
                    kind = re.search(br'<TYPE>\s*([^\r\n<]+)', buffer[:at], re.I)
                    wanted = kind and kind.group(1).strip().upper() in (b'NPORT-P', b'NPORT-P/A')
                    buffer, mode = buffer[at + 5:], 'copy' if wanted else 'skip'
                elif len(buffer) > 64 * 1024:
                    kind = re.search(br'<TYPE>\s*([^\r\n<]+)', buffer[:1000], re.I)
                    if kind and kind.group(1).strip().upper() in (b'NPORT-P', b'NPORT-P/A'):
                        raise ValueError('N-PORT XML header exceeds streaming limit')
                    buffer, mode = buffer[-11:], 'skip'
                else:
                    break
            elif mode == 'skip':
                at = upper.find(b'</DOCUMENT>')
                if at < 0:
                    buffer = buffer[-11:]
                    break
                buffer, mode = buffer[at + 11:], 'seek'
            elif mode == 'copy':
                at = upper.find(b'</XML>')
                if at >= 0:
                    output.write(buffer[:at].lstrip() if output.tell() == 0 else buffer[:at])
                    buffer, mode = b'', 'done'
                else:
                    output.write(buffer[:-6].lstrip() if output.tell() == 0 else buffer[:-6])
                    buffer = buffer[-6:]
                    break
    if digest.hexdigest() != expected_sha256:
        raise ValueError('Original SEC submission checksum mismatch')
    if mode != 'done':
        raise ValueError('N-PORT XML missing or incomplete')


def parse_xml(path, start, max_positions=500_000):
    from sec_history import report_date
    stack, rows, metadata = [], [], None
    total_assets = ''
    for event, node in ET.iterparse(path, events=('start', 'end')):
        if event == 'start':
            stack.append(node)
            continue
        name = local(node.tag)
        if name == 'geninfo':
            date = report_date(val(node, 'repPdDate', 'reportDate', 'reportingPeriod'))
            if date < start:
                return None
            identity = fund_identity(node)
            title = val(node, 'seriesName', 'seriesNm', 'seriesNameOfFund')
            if not title or title.upper() == 'N/A':
                title = val(node, 'regName') or identity['fund_id']
            metadata = dict(identity, fund_name=title, report_date=date)
            node.clear()
        elif name in ('totassets', 'totalassets'):
            total_assets = (node.text or '').strip()
        elif name in ('invstorsec', 'investmentorsecurity'):
            position = parse_position(node)
            if position is not None:
                rows.append(position)
                if len(rows) > max_positions:
                    raise ValueError('N-PORT exceeds streaming position limit')
            if len(stack) > 1:
                stack[-2].remove(node)
            node.clear()
        stack.pop()
    if metadata is None:
        raise ValueError('N-PORT general information missing')
    if not rows:
        raise ValueError('No supported N-PORT positions')
    return dict(metadata, total_assets_reported=total_assets, holdings=rows)


def normalize(root, record, start):
    from sec_history import save
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / 'primary.xml'
        with original_stream(root, record) as source, path.open('wb') as output:
            extract_xml(source, output, record['sha256'])
        fund = parse_xml(path, start)
    if fund is None:
        return []
    if fund.get('identity_registrant_cik', record['cik']) != record['cik']:
        raise ValueError('N-PORT identity does not match catalogue registrant')
    fund.update(registrant_cik=record['cik'], registrant_name=record['name'],
                accession=record['accession'], form=record['form'],
                filing_date=record['filing_date'], source=record['source'])
    # Re-normalizing an archived original is not a new public retrieval.
    for key in ('retrieved_at','ingested_at','public_available_at','public_observed_at','public_observation_basis','accepted_at'):
        if record.get(key) is not None:
            fund[key] = record[key]
    path = root / 'history/normalized/funds' / (record['accession'] + '.json.gz')
    save(path, fund)
    return [str(path.relative_to(root))]
