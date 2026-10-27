"""The supplied quickstart runs from source and installed sdists without an existing service."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class QuickstartTests(unittest.TestCase):
    def test_supplied_quickstart_retains_failures_and_refuses_to_overwrite_an_attempt(self):
        example = Path(__file__).resolve().parents[1] / "examples/quickstart.py"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "first"
            command = [sys.executable, str(example), "--output-dir", str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertTrue(summary["verified"])
            self.assertEqual(summary["catalogue_status"], "changed")
            self.assertEqual(summary["failure_stage"], "ping")
            self.assertTrue(summary["recovered"])
            reports = {name: json.loads((output / (name + ".json")).read_text())
                       for name in ["before", "after", "failed", "recovered", "drift", "recovery"]}
            self.assertEqual(reports["before"]["tools_checked"], 2)
            self.assertEqual(reports["after"]["tools_checked"], 2)
            self.assertFalse(reports["failed"]["verified"])
            self.assertEqual(reports["failed"]["failure"]["code"], "rpc_error")
            self.assertTrue(reports["recovery"]["same_observations"])
            hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
            repeated = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
            self.assertEqual(repeated.returncode, 2)
            self.assertTrue(json.loads(repeated.stderr)["requestID"])
            self.assertEqual(hashes, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in output.iterdir()})
            recovered = subprocess.run([sys.executable, str(example), "--output-dir",
                                        str(Path(directory) / "second")],
                                       capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertTrue(json.loads(recovered.stdout)["verified"])


if __name__ == "__main__":
    unittest.main()
