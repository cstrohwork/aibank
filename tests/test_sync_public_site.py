import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "sync_public_site.py"
SPEC = importlib.util.spec_from_file_location("sync_public_site", MODULE_PATH)
sync = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(sync)


class PublicSiteSyncTests(unittest.TestCase):
    def make_site(self, root: Path) -> None:
        for name in sync.REQUIRED_FILES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("<!doctype html><title>public</title>", encoding="utf-8")

    def test_collects_reviewed_pages_and_browser_data_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_site(root)
            included = {
                "CapitalSignal/atlas/atlas.js": "console.log('public')",
                "CapitalSignal/ownership/data/NVDA.json": "{}",
                "CapitalSignal/spotlight/investors/1/profile.json": "{}",
                "CapitalSignal/spotlight/funds/1/S1/versions/a.json": "{}",
                "CapitalSignal/data/atlas/manifest.json": "{}",
                "CapitalSignal/data/13f/index.json": "{}",
                "CapitalSignal/data/fundamentals/status.json": "{}",
                "CapitalSignal/data/fundamentals/model_companies/0001.json": "{}",
            }
            for name, content in included.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            excluded = {
                "CNAME": "www.ainvestmentbank.ai",
                "scripts/ingest.py": "private worker",
                "CapitalSignal/WORKER_BACKLOG.md": "internal",
                "CapitalSignal/data/history/status.json": "worker state",
                "CapitalSignal/data/fundamentals/companyfacts/secret.json": "raw cache",
                "CapitalSignal/spotlight/investors/1/debug.json": "internal",
            }
            for name, content in excluded.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            files = sync.collect(root)
            self.assertTrue(set(included).issubset(files))
            self.assertTrue(set(excluded).isdisjoint(files))

    def test_audit_rejects_high_confidence_secret(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "index.html"
            path.write_text("ghp_" + "A" * 36, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "GitHub token"):
                sync.audit({"index.html": path})

    def test_stage_is_exact_and_hash_manifested(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            self.make_site(root)
            files = sync.collect(root)
            destination = Path(temp) / "stage"
            stale = destination / "stale.txt"
            stale.parent.mkdir(parents=True)
            stale.write_text("remove me", encoding="utf-8")
            manifest = sync.stage(files, destination)
            self.assertFalse(stale.exists())
            self.assertEqual(manifest["file_count"], len(sync.REQUIRED_FILES))
            self.assertFalse(manifest["custom_domain_included"])
            written = json.loads(
                (destination / "public-site-inventory.json").read_text(encoding="utf-8")
            )
            self.assertEqual(written["files"], manifest["files"])

    def test_stage_rewrites_root_local_html_links_for_project_pages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            self.make_site(root)
            page = root / "CapitalSignal" / "daily" / "2026-11-22" / "index.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                '<a href="/">Home</a><a href="/CapitalSignal/weekly/?x=1#top">Weekly</a>'
                '<script src="//cdn.example.test/a.js"></script>'
                '<link rel="canonical" href="https://www.ainvestmentbank.ai/CapitalSignal/">',
                encoding="utf-8",
            )
            files = sync.collect(root)
            destination = Path(temp) / "stage"
            manifest = sync.stage(files, destination)
            rendered = (destination / page.relative_to(root)).read_text(encoding="utf-8")
            self.assertIn('href="../../../"', rendered)
            self.assertIn('href="../../weekly/?x=1#top"', rendered)
            self.assertIn('src="//cdn.example.test/a.js"', rendered)
            self.assertIn('href="https://www.ainvestmentbank.ai/CapitalSignal/"', rendered)
            self.assertEqual(manifest["portable_root_references_rewritten"], 2)
            entry = next(x for x in manifest["files"] if x["path"] == page.relative_to(root).as_posix())
            self.assertEqual(entry["sha256"], hashlib.sha256(rendered.encode()).hexdigest())


if __name__ == "__main__":
    unittest.main()
