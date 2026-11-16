import re
import unittest
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "capitalsignal-health.yml"
)


class HealthWorkflowBudgetTests(unittest.TestCase):
    def test_health_job_retains_bounded_execution_headroom(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        timeout = re.search(r"(?m)^\s*timeout-minutes:\s*(\d+)\s*$", text)
        self.assertIsNotNone(timeout)
        self.assertGreaterEqual(int(timeout.group(1)), 10)

    def test_health_report_and_serialization_safeguards_remain(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^\s*group:\s*capitalsignal-health\s*$")
        self.assertRegex(text, r"(?m)^\s*cancel-in-progress:\s*false\s*$")
        self.assertIn("python -m unittest discover -s tests -v", text)
        self.assertIn("node --test tests/atlas-core.test.cjs", text)
        self.assertIn("if-no-files-found: error", text)
        self.assertGreaterEqual(text.count("if: always()"), 3)


if __name__ == "__main__":
    unittest.main()
