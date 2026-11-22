#!/usr/bin/env python3
"""Validate a deployed public site against its reviewed repository inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
from pathlib import PurePosixPath
import ssl
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_BASE_URL = "https://cstrohwork.github.io/aibank_public/"
DEFAULT_INVENTORY_URL = (
    "https://raw.githubusercontent.com/cstrohwork/aibank_public/main/"
    "public-site-inventory.json"
)
CRITICAL_PATHS = (
    "index.html",
    "CapitalSignal/index.html",
    "CapitalSignal/daily/index.html",
    "CapitalSignal/weekly/index.html",
    "CapitalSignal/spotlight/index.html",
    "CapitalSignal/ownership/index.html",
    "CapitalSignal/fundamentals/index.html",
    "CapitalSignal/model/index.html",
    "CapitalSignal/skunkworks/index.html",
    "CapitalSignal/skunkworks/workbench/index.html",
    "CapitalSignal/atlas/index.html",
    "CapitalSignal/workerdashboard/index.html",
    "CapitalSignal/data/atlas/manifest.json",
    "CapitalSignal/data/fundamentals/status.json",
)
FORBIDDEN_PATHS = (
    "CNAME",
    "CapitalSignal/WORKER_BACKLOG.md",
    "CapitalSignal/data/history/status.json",
    "scripts/sync_public_site.py",
)
USER_AGENT = "CapitalSignal-public-deployment-validator/1.0"


def validate_https_url(value: str, *, label: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{label} must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(f"{label} must not include credentials, query, or fragment")
    return value if value.endswith("/") else value + "/"


def _request(url: str, *, timeout: float) -> tuple[int, str, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=ssl.create_default_context()
        ) as response:
            return response.status, response.headers.get_content_type(), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get_content_type(), exc.read()


def expected_content_type(path: str) -> str | None:
    suffix = PurePosixPath(path).suffix.lower()
    return {
        ".html": "text/html",
        ".css": "text/css",
        ".js": "text/javascript",
        ".json": "application/json",
        ".svg": "image/svg+xml",
    }.get(suffix) or mimetypes.guess_type(path)[0]


def validate(
    base_url: str,
    inventory_url: str,
    *,
    timeout: float = 20.0,
    request_fn=_request,
) -> dict:
    base_url = validate_https_url(base_url, label="base URL")
    inventory_url = validate_https_url(inventory_url, label="inventory URL").rstrip("/")
    status, content_type, data = request_fn(inventory_url, timeout=timeout)
    if status != 200:
        raise RuntimeError(f"Inventory HTTP {status}: {inventory_url}")
    if content_type not in {"application/json", "text/plain"}:
        raise RuntimeError(f"Inventory has unexpected content type {content_type!r}")
    inventory = json.loads(data)
    if inventory.get("custom_domain_included") is not False:
        raise RuntimeError("Inventory does not prove CNAME exclusion")
    if inventory.get("raw_sec_archives_included") is not False:
        raise RuntimeError("Inventory does not prove raw SEC archive exclusion")
    entries = {item["path"]: item for item in inventory.get("files", [])}
    if inventory.get("file_count") != len(entries):
        raise RuntimeError("Inventory file count does not match unique entries")

    checked = []
    errors = []
    for path in CRITICAL_PATHS:
        entry = entries.get(path)
        if not entry:
            errors.append(f"critical path absent from inventory: {path}")
            continue
        url = urllib.parse.urljoin(base_url, path)
        actual_status, actual_type, body = request_fn(url, timeout=timeout)
        expected_type = expected_content_type(path)
        digest = hashlib.sha256(body).hexdigest()
        if actual_status != 200:
            errors.append(f"{path}: HTTP {actual_status}")
        if expected_type and actual_type != expected_type:
            errors.append(f"{path}: MIME {actual_type!r}, expected {expected_type!r}")
        if digest != entry.get("sha256"):
            errors.append(f"{path}: deployed bytes differ from reviewed inventory")
        checked.append(path)

    forbidden = []
    for path in FORBIDDEN_PATHS:
        url = urllib.parse.urljoin(base_url, path)
        actual_status, _, _ = request_fn(url, timeout=timeout)
        if actual_status != 404:
            errors.append(f"forbidden path is reachable ({actual_status}): {path}")
        forbidden.append({"path": path, "status": actual_status})

    report = {
        "schema_version": 1,
        "base_url": base_url,
        "inventory_url": inventory_url,
        "inventory_file_count": inventory.get("file_count"),
        "inventory_total_bytes": inventory.get("total_bytes"),
        "critical_paths_checked": checked,
        "forbidden_paths_checked": forbidden,
        "errors": errors,
        "status": "passed" if not errors else "failed",
    }
    if errors:
        raise RuntimeError(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--inventory-url", default=DEFAULT_INVENTORY_URL)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--report")
    args = parser.parse_args()
    report = validate(args.base_url, args.inventory_url, timeout=args.timeout)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            handle.write(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
