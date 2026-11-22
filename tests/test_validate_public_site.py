import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "validate_public_site.py"
SPEC = importlib.util.spec_from_file_location("validate_public_site", MODULE_PATH)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(validator)


class PublicSiteValidatorTests(unittest.TestCase):
    def write(self, root: Path, name: str, content: str) -> None:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def make_required_json(self, root: Path) -> None:
        self.write(root, "CapitalSignal/data/atlas/manifest.json", '{"lenses":{}}')
        self.write(root, "CapitalSignal/data/13f/index.json", '{"managers":[]}')
        self.write(root, "CapitalSignal/data/fundamentals/model_data.json", '{"companies":{}}')
        self.write(root, "CapitalSignal/data/fundamentals/status.json", '{}')
        self.write(root, "CapitalSignal/data/fundamentals/model_status.json", '{}')
        self.write(root, "CapitalSignal/skunkworks/catalog.json", '[]')

    def test_validates_absolute_relative_css_and_external_references(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_required_json(root)
            self.write(root, "index.html", '<a href="/CapitalSignal/"></a><a href="https://sec.gov/"></a>')
            self.write(root, "CapitalSignal/index.html", '<link href="site.css"><img src="asset.svg">')
            self.write(root, "CapitalSignal/site.css", 'body{background:url("asset.svg")}')
            self.write(root, "CapitalSignal/asset.svg", '<svg/>')
            report = validator.validate(root)
            self.assertEqual(report["error_count"], 0)
            self.assertEqual(report["local_references"], 4)

    def test_reports_missing_local_link_and_invalid_json(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_required_json(root)
            self.write(root, "index.html", '<a href="missing/"></a>')
            self.write(root, "bad.json", '{')
            report = validator.validate(root)
            self.assertEqual(report["error_count"], 2)
            self.assertTrue(any("missing/" in item for item in report["errors"]))
            self.assertTrue(any("bad.json" in item for item in report["errors"]))

    def test_checks_generated_manifest_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_required_json(root)
            self.write(root, "index.html", '<title>ok</title>')
            self.write(
                root, "CapitalSignal/data/atlas/manifest.json",
                json.dumps({"lenses": {"managers": [{"file": "missing.json"}]}}),
            )
            report = validator.validate(root)
            self.assertEqual(report["error_count"], 1)
            self.assertIn("atlas manifest", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
