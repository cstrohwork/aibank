import re
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "sec-history.yml"


def _integer_setting(text: str, name: str) -> int:
    match = re.search(rf"^\s*{re.escape(name)}:\s*['\"]?(\d+)['\"]?\s*$", text, re.MULTILINE)
    if not match:
        raise AssertionError(f"Missing integer workflow setting: {name}")
    return int(match.group(1))


class SecWorkflowBudgetTests(unittest.TestCase):
    def test_job_timeout_covers_acquisition_and_publication_headroom(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        timeout_minutes = _integer_setting(text, "timeout-minutes")
        acquisition_seconds = _integer_setting(text, "SEC_HISTORY_SECONDS")

        required_minutes = (acquisition_seconds + 59) // 60 + 15
        self.assertGreaterEqual(timeout_minutes, required_minutes)

    def test_serialized_recovery_safeguards_remain_enabled(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^\s*group:\s*sec-edgar-cache\s*$")
        self.assertRegex(text, r"(?m)^\s*cancel-in-progress:\s*false\s*$")
        self.assertIn("if: always()", text)
        self.assertIn("sec_worker_control.py continue", text)
        self.assertIn("sec-worker-recovery.yml/dispatches", text)


if __name__ == "__main__":
    unittest.main()
