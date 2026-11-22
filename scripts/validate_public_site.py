#!/usr/bin/env python3
"""Validate the exact public-site tree before repository publication.

Checks local HTML/CSS dependencies, JSON syntax, and the principal generated
manifest references. External URLs are intentionally out of scope here and are
tested only after GitHub Pages is available.
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import unquote, urlsplit


EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel", "data", "javascript"}
CSS_URL = re.compile(r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)", re.IGNORECASE)
ROOT_CODE_REQUEST = re.compile(
    r"\b(?:fetch|importScripts|Worker|import|register)\s*\(\s*['\"]/(?!/)",
    re.IGNORECASE,
)
MAX_REPORTED_ERRORS = 100


class ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        for attribute in ("href", "src", "poster", "action", "formaction"):
            value = values.get(attribute)
            if value:
                self.references.append(value)
        srcset = values.get("srcset")
        if srcset:
            self.references.extend(item.strip().split()[0] for item in srcset.split(","))


def _resolve(site: Path, source: Path, reference: str) -> Path | None:
    reference = reference.strip()
    if not reference or reference.startswith("#") or reference.startswith("//"):
        return None
    parsed = urlsplit(reference)
    if parsed.scheme.lower() in EXTERNAL_SCHEMES or parsed.netloc:
        return None
    decoded = unquote(parsed.path)
    if not decoded:
        return None
    if decoded.startswith("/"):
        relative = PurePosixPath(decoded.lstrip("/"))
    else:
        relative = PurePosixPath(source.relative_to(site).parent.as_posix()) / decoded
    parts: list[str] = []
    for part in relative.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ValueError("reference escapes the public root")
            parts.pop()
        else:
            parts.append(part)
    candidate = site.joinpath(*parts)
    if decoded.endswith("/") or candidate.is_dir():
        candidate /= "index.html"
    return candidate


def _check_reference(site: Path, source: Path, reference: str, errors: list[str]) -> bool:
    try:
        target = _resolve(site, source, reference)
    except ValueError as exc:
        errors.append(f"{source.relative_to(site)} -> {reference}: {exc}")
        return True
    if target is not None and not target.is_file():
        errors.append(f"{source.relative_to(site)} -> missing {reference}")
    return target is not None


def _is_root_local(reference: str) -> bool:
    value = reference.strip()
    if not value.startswith("/") or value.startswith("//"):
        return False
    parsed = urlsplit(value)
    return not parsed.scheme and not parsed.netloc


def _json(site: Path, relative: str, errors: list[str]):
    path = site / relative
    if not path.is_file():
        errors.append("missing required JSON: " + relative)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON {relative}: {exc}")
        return None


def _check_manifest_references(site: Path, errors: list[str]) -> int:
    checked = 0
    atlas = _json(site, "CapitalSignal/data/atlas/manifest.json", errors)
    if isinstance(atlas, dict):
        for rows in atlas.get("lenses", {}).values():
            for row in rows if isinstance(rows, list) else []:
                name = row.get("file") if isinstance(row, dict) else None
                if not isinstance(name, str) or not (site / "CapitalSignal/data/atlas" / name).is_file():
                    errors.append("atlas manifest references missing/invalid file: " + repr(name))
                checked += 1
    holdings = _json(site, "CapitalSignal/data/13f/index.json", errors)
    if isinstance(holdings, dict):
        for row in holdings.get("managers", []):
            name = row.get("file") if isinstance(row, dict) else None
            if not isinstance(name, str) or not (site / "CapitalSignal/data/13f" / name).is_file():
                errors.append("13F index references missing/invalid file: " + repr(name))
            checked += 1
    model = _json(site, "CapitalSignal/data/fundamentals/model_data.json", errors)
    if isinstance(model, dict):
        for row in model.get("companies", {}).values():
            name = row.get("data_file") if isinstance(row, dict) else None
            if name is None:
                continue
            if not isinstance(name, str) or not (site / "CapitalSignal/data/fundamentals" / name).is_file():
                errors.append("model manifest references missing/invalid file: " + repr(name))
            checked += 1
    for required in (
        "CapitalSignal/data/fundamentals/status.json",
        "CapitalSignal/data/fundamentals/model_status.json",
        "CapitalSignal/skunkworks/catalog.json",
    ):
        _json(site, required, errors)
        checked += 1
    return checked


def validate(site: Path) -> dict:
    errors: list[str] = []
    html_files = list(site.rglob("*.html"))
    css_files = list(site.rglob("*.css"))
    json_files = list(site.rglob("*.json"))
    js_files = list(site.rglob("*.js"))
    reference_count = 0
    root_local_references = 0
    root_code_requests = 0
    for path in html_files:
        parser = ReferenceParser()
        try:
            text = path.read_text(encoding="utf-8")
            parser.feed(text)
        except (UnicodeDecodeError, ValueError) as exc:
            errors.append(f"invalid HTML text {path.relative_to(site)}: {exc}")
            continue
        for reference in parser.references:
            if _is_root_local(reference):
                errors.append(
                    f"{path.relative_to(site)} -> non-portable root-local reference {reference}"
                )
                root_local_references += 1
            reference_count += _check_reference(site, path, reference, errors)
        root_code_requests += len(ROOT_CODE_REQUEST.findall(text))
        if ROOT_CODE_REQUEST.search(text):
            errors.append(f"{path.relative_to(site)} contains non-portable root-local code request")
    for path in css_files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"invalid CSS text {path.relative_to(site)}: {exc}")
            continue
        for match in CSS_URL.finditer(text):
            reference = match.group(2)
            if _is_root_local(reference):
                errors.append(
                    f"{path.relative_to(site)} -> non-portable root-local CSS reference {reference}"
                )
                root_local_references += 1
            reference_count += _check_reference(site, path, reference, errors)
    for path in js_files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"invalid JavaScript text {path.relative_to(site)}: {exc}")
            continue
        matches = len(ROOT_CODE_REQUEST.findall(text))
        root_code_requests += matches
        if matches:
            errors.append(f"{path.relative_to(site)} contains {matches} non-portable root-local code requests")
    json_valid = 0
    for path in json_files:
        try:
            json.loads(path.read_text(encoding="utf-8"))
            json_valid += 1
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid JSON {path.relative_to(site)}: {exc}")
    manifest_references = _check_manifest_references(site, errors)
    return {
        "html_files": len(html_files),
        "css_files": len(css_files),
        "js_files": len(js_files),
        "json_files": len(json_files),
        "json_valid": json_valid,
        "local_references": reference_count,
        "root_local_references": root_local_references,
        "root_code_requests": root_code_requests,
        "manifest_references": manifest_references,
        "error_count": len(errors),
        "errors": errors[:MAX_REPORTED_ERRORS],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.site_dir.resolve())
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "errors"}, sort_keys=True))
    for error in report["errors"]:
        print("ERROR:", error)
    if report["error_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
