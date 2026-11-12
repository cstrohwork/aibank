import importlib.util
import pathlib
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("pipeline", pathlib.Path(__file__).resolve().parents[1] / "scripts/run_intelligence_pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)

class PipelineTests(unittest.TestCase):
    def test_failure_preserved_and_remaining_stages_run(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args[-1])
            if len(calls) == 2:
                raise subprocess.TimeoutExpired(args, 480)
            return subprocess.CompletedProcess(args, 0, "ok", "")
        with tempfile.TemporaryDirectory() as temp:
            report = pipeline.rebuild(pathlib.Path(temp), run)
        self.assertEqual(len(calls), len(pipeline.STAGES))
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["stages"][1]["status"], "failed")
        self.assertEqual(report["stages"][-1]["status"], "passed")

    def test_success_is_execution_only(self):
        def run(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, "", "")
        with tempfile.TemporaryDirectory() as temp:
            report = pipeline.rebuild(pathlib.Path(temp), run)
        self.assertEqual(report["status"], "completed")
        self.assertIn("does not certify source coverage", report["scope"])
