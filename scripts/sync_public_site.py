#!/usr/bin/env python3
"""Stage explicitly reviewed static website assets to a separate public repo.

No raw SEC caches, ingestion code, workflows, secrets, or generated datasets are copied.
This is a staging tool; custom-domain cutover is intentionally manual.
"""
import base64
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

DEST = os.environ.get("PUBLIC_SITE_REPO", "cstrohwork/aibank_public")
TOKEN = os.environ["PUBLIC_SITE_TOKEN"]
ROOT = Path(__file__).resolve().parents[1]
PAGES = (
    "CapitalSignal/daily", "CapitalSignal/weekly",
    "CapitalSignal/spotlight", "CapitalSignal/ownership",
    "CapitalSignal/fundamentals", "CapitalSignal/model",
    "CapitalSignal/skunkworks", "CapitalSignal/workerdashboard",
    "CapitalSignal/tools",
)
# Only static display assets. No JSON/CSV/databases; approve each dataset separately.
SUFFIXES = {".html", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg",
            ".webp", ".ico", ".woff", ".woff2", ".txt"}
MAX_BYTES = 2_000_000


def api(method, path, body=None):
    url = "https://api.github.com/repos/" + DEST + "/" + path
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": "Bearer " + TOKEN,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def collect():
    files = [ROOT / "index.html", ROOT / "CapitalSignal/index.html"]
    # Root-level shared assets must be separately reviewed before inclusion.
    for directory in PAGES:
        folder = ROOT / directory
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(ROOT)
            if any(part.startswith(".") for part in relative.parts):
                continue
            if any(part.lower() in {"data", "raw", "cache", "private", "internal",
                                   "scripts", "tests", "fixtures", "secrets"}
                   for part in relative.parts):
                continue
            if path.suffix.lower() in SUFFIXES:
                files.append(path)
    result = {}
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("Required site file missing: " + str(path))
        size = path.stat().st_size
        if size > MAX_BYTES:
            raise RuntimeError("Asset too large for unreviewed publication: " + str(path))
        result[path.relative_to(ROOT).as_posix()] = path
    return result


def main():
    files = collect()
    print("Staging static files:", len(files))
    for name in sorted(files):
        print("  ", name)
    branch = api("GET", "git/ref/heads/main")
    old_sha = branch["object"]["sha"]
    head = api("GET", "git/commits/" + old_sha)
    tree = []
    for name, path in sorted(files.items()):
        blob = api("POST", "git/blobs", {
            "content": base64.b64encode(path.read_bytes()).decode(),
            "encoding": "base64"})
        tree.append({"path": name, "mode": "100644",
                     "type": "blob", "sha": blob["sha"]})
    new_tree = api("POST", "git/trees", {
        "base_tree": head["tree"]["sha"], "tree": tree})
    commit = api("POST", "git/commits", {
        "message": "Publish reviewed static website files",
        "tree": new_tree["sha"], "parents": [old_sha]})
    api("PATCH", "git/refs/heads/main", {"sha": commit["sha"], "force": False})
    print("Published:", "https://github.com/" + DEST + "/commit/" + commit["sha"])
    print("Data feeds deliberately excluded pending explicit review.")
    print("Custom domain deliberately not transferred.")


if __name__ == "__main__":
    main()
