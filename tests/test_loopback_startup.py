"""Owned literal-loopback startup must not wait on reverse DNS."""
import io
import json
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mcp_connect_diagnoser.core import LocalFixture, probe
from mcp_connect_diagnoser.proxy import LoopbackProxy


class LoopbackStartupTests(unittest.TestCase):
    def test_fixture_starts_without_reverse_dns(self):
        with (patch('socket.getfqdn', side_effect=AssertionError('reverse DNS is forbidden')),
              LocalFixture() as target):
            self.assertEqual(target.server.server_name, '127.0.0.1')
            self.assertEqual(probe(target.url)['status'], 200)

    def test_proxy_starts_without_reverse_dns(self):
        with (patch('socket.getfqdn', side_effect=AssertionError('reverse DNS is forbidden')),
              LocalFixture() as target, LoopbackProxy(target.url) as proxy):
            self.assertEqual(proxy.server.server_name, '127.0.0.1')
            self.assertEqual(probe(proxy.url)['status'], 200)

    def test_quickstart_completes_without_reverse_dns(self):
        example = Path(__file__).resolve().parents[1] / 'examples/quickstart.py'
        namespace = runpy.run_path(str(example))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'reports'
            stdout = io.StringIO()
            with (patch('socket.getfqdn', side_effect=AssertionError('reverse DNS is forbidden')),
                  patch.object(sys, 'argv', [str(example), '--output-dir', str(output)]),
                  redirect_stdout(stdout)):
                self.assertEqual(namespace['main'](), 0)
            summary = json.loads(stdout.getvalue())
            self.assertTrue(summary['verified'])
            self.assertEqual(summary['reports_saved'], 6)
            self.assertEqual(len(list(output.glob('*.json'))), 6)


if __name__ == '__main__':
    unittest.main()
