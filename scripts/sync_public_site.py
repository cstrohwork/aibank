#!/usr/bin/env python3
"""Build an exact, reviewed public-site tree for ``aibank_public``.

The output contains website code and the normalized public data that those pages
load. It excludes source, workflows, raw SEC archives, worker checkpoints,
validation evidence, credentials, and the custom-domain ``CNAME``. Publication
uses a destination-only credential; this module never handles a token.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]
PAGE_ROOTS = (
    "CapitalSignal/daily", "CapitalSignal/weekly", "CapitalSignal/spotlight",
    "CapitalSignal/ownership", "CapitalSignal/fundamentals",
    "CapitalSignal/model", "CapitalSignal/skunkworks",
    "CapitalSignal/workerdashboard", "CapitalSignal/tools",
    "CapitalSignal/atlas", "CapitalSignal/subscribe",
)
STATIC_SUFFIXES = {
    ".html", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg",
    ".webp", ".ico", ".woff", ".woff2", ".txt",
}
REQUIRED_FILES = {
    "index.html", "CapitalSignal/index.html",
    "CapitalSignal/daily/index.html", "CapitalSignal/weekly/index.html",
    "CapitalSignal/spotlight/index.html", "CapitalSignal/ownership/index.html",
    "CapitalSignal/fundamentals/index.html", "CapitalSignal/model/index.html",
    "CapitalSignal/skunkworks/index.html",
    "CapitalSignal/workerdashboard/index.html", "CapitalSignal/tools/index.html",
    "CapitalSignal/atlas/index.html", "CapitalSignal/subscribe/index.html",
}
MAX_FILE_BYTES = 25_000_000
# Exact-head inventory measured 2,295,635,565 bytes. Keep bounded headroom for
# new public profiles without allowing the publisher to absorb arbitrary caches.
MAX_TOTAL_BYTES = 3_000_000_000
# The generated investor/fund profile library is a first-class public site
# dependency.  Exact-head inventory measured 162,229 reviewed files; retain
# bounded headroom without silently dropping profiles.
MAX_FILES = 200_000
SECRET_PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
}


def _is_public_json(relative: PurePosixPath) -> bool:
    """Return true only for reviewed, browser-consumed normalized outputs."""
    parts = relative.parts
    if relative == PurePosixPath("CapitalSignal/skunkworks/catalog.json"):
        return True
    if parts[:3] == ("CapitalSignal", "ownership", "data"):
        return len(parts) == 4 and relative.suffix == ".json"
    if parts[:3] in {
        ("CapitalSignal", "spotlight", "investors"),
        ("CapitalSignal", "spotlight", "funds"),
    }:
        return relative.suffix == ".json" and (
            relative.name == "profile.json" or "versions" in parts
        )
    if parts[:3] in {
        ("CapitalSignal", "data", "atlas"),
        ("CapitalSignal", "data", "13f"),
    }:
        return relative.suffix == ".json"
    if parts[:3] == ("CapitalSignal", "data", "fundamentals"):
        if len(parts) == 4 and relative.name in {
            "status.json", "model_status.json", "model_data.json",
        }:
            return True
        return (
            len(parts) == 5 and parts[3] == "model_companies"
            and relative.suffix == ".json"
        )
    return False


def _candidate_paths(root: Path):
    for name in ("index.html", "CapitalSignal/index.html"):
        yield root / name
    for directory in PAGE_ROOTS:
        folder = root / directory
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if path.suffix.lower() in STATIC_SUFFIXES or _is_public_json(relative):
                yield path
    for directory in (
        "CapitalSignal/data/atlas", "CapitalSignal/data/13f",
        "CapitalSignal/data/fundamentals",
    ):
        folder = root / directory
        if not folder.is_dir():
            continue
        for path in folder.rglob("*.json"):
            if path.is_file() and not path.is_symlink():
                relative = PurePosixPath(path.relative_to(root).as_posix())
                if _is_public_json(relative):
                    yield path


def collect(root: Path = ROOT) -> dict[str, Path]:
    files: dict[str, Path] = {}
    total_bytes = 0
    for path in _candidate_paths(root):
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise RuntimeError(f"Public asset exceeds {MAX_FILE_BYTES} bytes: {relative}")
        files[relative] = path
        total_bytes += size
    missing = sorted(REQUIRED_FILES - files.keys())
    if missing:
        raise RuntimeError("Required public site files are missing: " + ", ".join(missing))
    if len(files) > MAX_FILES:
        raise RuntimeError(f"Refusing {len(files)} public files; reviewed cap is {MAX_FILES}")
    if total_bytes > MAX_TOTAL_BYTES:
        raise RuntimeError(
            f"Refusing {total_bytes} public bytes; reviewed cap is {MAX_TOTAL_BYTES}"
        )
    return files


def audit(files: dict[str, Path]) -> None:
    forbidden_roots = ("scripts/", "tests/", ".github/", "CapitalSignal/validation/")
    forbidden_names = {"CNAME", "WORKER_BACKLOG.md", "archive_state.json.gz"}
    for relative, path in files.items():
        if relative.startswith(forbidden_roots) or Path(relative).name in forbidden_names:
            raise RuntimeError("Internal-only path entered public tree: " + relative)
        data = path.read_bytes()
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                raise RuntimeError(f"Possible {label} in public output: {relative}")


def stage(files: dict[str, Path], destination: Path) -> dict:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    entries = []
    total_bytes = 0
    for relative, source in sorted(files.items()):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        data = source.read_bytes()
        total_bytes += len(data)
        entries.append({
            "path": relative, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    manifest = {
        "schema_version": 1, "file_count": len(entries),
        "total_bytes": total_bytes, "custom_domain_included": False,
        "raw_sec_archives_included": False, "files": entries,
    }
    (destination / "public-site-inventory.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--stage-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = collect(args.root.resolve())
    audit(files)
    manifest = stage(files, args.stage_dir.resolve())
    print(
        f"Staged {manifest['file_count']} explicitly allowlisted files "
        f"({manifest['total_bytes']} bytes)."
    )
    print("Excluded: CNAME, raw SEC archives, worker state, source, workflows, tests, and secrets.")


if __name__ == "__main__":
    main()
