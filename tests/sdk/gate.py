"""Required SDK qualification is a separate explicit gate, with no skip path."""
import argparse
import base64
import json
import unittest
from pathlib import Path

from mcp_connect_diagnoser.sdk_repro import run_matrix


class SDKGate(unittest.TestCase):
    record = None

    def row(self, sdk, composition, route, case):
        return next(row for row in self.record['rows'] if (
            row['sdk'], row['composition'], row['route'], row['case']) == (
                sdk, composition, route, case))

    def test_complete_frozen_matrix(self):
        self.assertTrue(self.record['complete'])
        self.assertEqual(len(self.record['rows']), 168)
        self.assertEqual(self.record['definition_sha256'],
                         'e9e7811a19276af102b78197ee4ba3a69eec8d5569459690ccf93a487eb49d7f')

    def test_initialize_positive_controls(self):
        for row in self.record['rows']:
            if row['case'] in {'mask-0', 'absent-origin'}:
                with self.subTest(sdk=row['sdk'], composition=row['composition'], route=row['route']):
                    self.assertEqual(row['status'], 200)
                    result = json.loads(base64.b64decode(row['body_base64']))
                    self.assertEqual(result['result']['serverInfo']['name'], 'sdk-repro')
                    self.assertEqual(result['result']['protocolVersion'], '2025-11-25')

    def test_proxy_preserves_native_status(self):
        for row in self.record['rows']:
            if row['route'] == 'direct':
                with self.subTest(sdk=row['sdk'], composition=row['composition'], case=row['case']):
                    proxy = self.row(row['sdk'], row['composition'], 'proxy', row['case'])
                    self.assertEqual(proxy['status'], row['status'])

    def test_proxy_preserves_exact_native_bytes(self):
        for row in self.record['rows']:
            if row['route'] == 'direct':
                with self.subTest(sdk=row['sdk'], composition=row['composition'], case=row['case']):
                    proxy = self.row(row['sdk'], row['composition'], 'proxy', row['case'])
                    self.assertEqual(proxy['body_base64'], row['body_base64'])

    def test_proxy_preserves_safe_native_headers_including_absence(self):
        for row in self.record['rows']:
            if row['route'] == 'direct':
                with self.subTest(sdk=row['sdk'], composition=row['composition'], case=row['case']):
                    proxy = self.row(row['sdk'], row['composition'], 'proxy', row['case'])
                    self.assertEqual(proxy['headers'], row['headers'])

    def test_order_is_configuration_dependent(self):
        for sdk in ['python', 'typescript']:
            for route in ['direct', 'proxy']:
                with self.subTest(sdk=sdk, route=route):
                    auth = self.row(sdk, 'auth-first', route, 'mask-7')
                    security = self.row(sdk, 'security-first', route, 'mask-7')
                    factory = self.row(sdk, 'factory', route, 'mask-7')
                    self.assertEqual(auth['status'], 401)
                    self.assertEqual(security['status'], 421 if sdk == 'python' else 403)
                    self.assertEqual(factory['body_base64'],
                                     (auth if sdk == 'python' else security)['body_base64'])

    def test_no_sdk_response_becomes_fixture_diagnosis(self):
        for row in self.record['rows']:
            self.assertEqual(row['diagnostic']['reason'], 'unknown')
            self.assertEqual(row['diagnostic']['confidence'], 'UNKNOWN')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    SDKGate.record = run_matrix(Path(__file__).parent, args.python, args.node, args.output)
    unittest.main(argv=['sdk-gate'], verbosity=2)
