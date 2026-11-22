import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "validate_public_deployment.py"
SPEC = importlib.util.spec_from_file_location("validate_public_deployment", MODULE_PATH)
deploy = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(deploy)


class PublicDeploymentValidationTests(unittest.TestCase):
    def make_fetcher(self, *, corrupt=None, exposed=None):
        base = deploy.DEFAULT_BASE_URL
        bodies = {path: ("payload:" + path).encode() for path in deploy.CRITICAL_PATHS}
        entries = [
            {"path": path, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
            for path, body in bodies.items()
        ]
        inventory = {
            "file_count": len(entries), "total_bytes": sum(x["bytes"] for x in entries),
            "custom_domain_included": False, "raw_sec_archives_included": False,
            "files": entries,
        }

        def fetch(url, *, timeout):
            del timeout
            if url == deploy.DEFAULT_INVENTORY_URL:
                return 200, "text/plain", json.dumps(inventory).encode()
            path = url.removeprefix(base)
            if path in deploy.FORBIDDEN_PATHS:
                return (200 if path == exposed else 404), "text/plain", b""
            body = bodies[path]
            if path == corrupt:
                body += b"changed"
            return 200, deploy.expected_content_type(path), body

        return fetch

    def test_passes_hash_mime_and_forbidden_path_checks(self):
        report = deploy.validate(
            deploy.DEFAULT_BASE_URL, deploy.DEFAULT_INVENTORY_URL,
            request_fn=self.make_fetcher(),
        )
        self.assertEqual(report["status"], "passed")
        self.assertEqual(len(report["critical_paths_checked"]), len(deploy.CRITICAL_PATHS))

    def test_fails_on_changed_deployed_bytes(self):
        with self.assertRaisesRegex(RuntimeError, "deployed bytes differ"):
            deploy.validate(
                deploy.DEFAULT_BASE_URL, deploy.DEFAULT_INVENTORY_URL,
                request_fn=self.make_fetcher(corrupt="CapitalSignal/index.html"),
            )

    def test_fails_when_internal_path_is_exposed(self):
        with self.assertRaisesRegex(RuntimeError, "forbidden path is reachable"):
            deploy.validate(
                deploy.DEFAULT_BASE_URL, deploy.DEFAULT_INVENTORY_URL,
                request_fn=self.make_fetcher(exposed="CapitalSignal/WORKER_BACKLOG.md"),
            )

    def test_rejects_unsafe_base_url(self):
        for url in ("http://example.test", "https://user:pw@example.test", "https://example.test/?x=1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                deploy.validate_https_url(url, label="base URL")


if __name__ == "__main__":
    unittest.main()
