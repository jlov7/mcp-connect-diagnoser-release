"""Input mistakes should explain the workflow the user actually selected."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp_connect_diagnoser import __version__
from mcp_connect_diagnoser.__main__ import main


class CommandGuidanceTests(unittest.TestCase):
    def test_version_is_available_without_a_command_or_network_target(self):
        result = subprocess.run(
            [sys.executable, "-m", "mcp_connect_diagnoser", "--version"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "mcp-connect-diagnoser " + __version__)
        self.assertEqual(result.stderr, "")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFOs")
    def test_all_offline_cli_inputs_refuse_special_files_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regular = root / "report.json"
            regular.write_text(json.dumps({
                "schema_version": 3, "report_type": "mcp-session-probe",
                "verified": False, "protocol_version": None, "session_received": False,
                "tools_checked": 0, "tool_pages_checked": 0, "server_pings_answered": 0,
                "reconnect_attempts": 0, "catalogue_sha256": None,
                "stages": [{"stage": "initialize", "outcome": "failed", "http_status": None}],
                "failure": {"stage": "initialize", "code": "connection_failed"},
                "cleanup": {"outcome": "not_needed"},
            }))
            fifo = root / "PRIVATE-input.fifo"
            os.mkfifo(fifo)
            for special in [fifo, root]:
                for arguments, error_code in [
                    (["summarize", str(special)], "invalid_record"),
                    (["compare", str(special), str(regular)], "invalid_input"),
                    (["compare", str(regular), str(special)], "invalid_input"),
                    (["probe-many", str(special)], "invalid_input"),
                ]:
                    with self.subTest(special=special.name, arguments=arguments):
                        try:
                            result = subprocess.run(
                                [sys.executable, "-m", "mcp_connect_diagnoser", *arguments],
                                capture_output=True, text=True, timeout=2, check=False,
                            )
                        except subprocess.TimeoutExpired:
                            self.fail("offline command blocked opening a non-regular input")
                        self.assertEqual(result.returncode, 2)
                        self.assertEqual(result.stdout, "")
                        error = json.loads(result.stderr)
                        self.assertEqual(error["error"]["code"], error_code)
                        self.assertTrue(error["requestID"])
                        self.assertNotIn(str(special), result.stderr)
                        self.assertNotIn("PRIVATE", result.stderr)

    def test_invalid_input_advice_matches_the_selected_command(self):
        with tempfile.TemporaryDirectory() as name:
            wrong = Path(name) / 'wrong-format.json'
            wrong.write_text('{"schema_version":1,"targets":"not-an-array"}')
            for arguments, phrase in [
                    (['compare', str(wrong), str(wrong)], 'saved probe or endpoint-set reports'),
                    (['probe-many', str(wrong)], 'targets'),
                    (['summarize', str(wrong)], 'native'),
                    (['probe', 'not-a-local-url'], 'literal-loopback')]:
                with self.subTest(command=arguments[0]), patch('sys.stderr', new_callable=io.StringIO) as stderr:
                    self.assertEqual(main(arguments), 2)
                    error = json.loads(stderr.getvalue())
                    self.assertIn(phrase, error['error']['next_step'])
                    self.assertNotIn(str(wrong), stderr.getvalue())
                    self.assertIn('requestID', error)


if __name__ == '__main__':
    unittest.main()
