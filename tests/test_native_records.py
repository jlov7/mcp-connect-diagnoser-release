import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from mcp_connect_diagnoser.core import diagnose
from mcp_connect_diagnoser.native_records import RecordError, load_record, summarize
from mcp_connect_diagnoser.sdk_repro import frozen_definitions, run_matrix


def record_fixture():
    definitions = frozen_definitions()
    good = json.dumps({'result': {'serverInfo': {'name': 'sdk-repro'},
                                 'protocolVersion': '2025-11-25'}}).encode()
    rows = []
    for sdk in ['python', 'typescript']:
        for composition in definitions['compositions']:
            for route in definitions['routes']:
                for case in definitions['cases']:
                    positive = case['name'] in {'mask-0', 'absent-origin'}
                    body = good if positive else b'native rejection'
                    status = 200 if positive else 403
                    rows.append({'sdk': sdk, 'composition': composition, 'route': route,
                                 'case': case['name'], 'status': status,
                                 'headers': {'content-type': ['application/json'],
                                             'www-authenticate': []},
                                 'body_base64': base64.b64encode(body).decode(),
                                 'body_sha256': hashlib.sha256(body).hexdigest(),
                                 'diagnostic': diagnose(status, {})})
    return {'scope': 'Native loopback SDK middleware reproduction, not protocol conformance or deployment evidence.',
            'definitions': definitions, 'definition_sha256': hashlib.sha256(
                json.dumps(definitions, sort_keys=True).encode()).hexdigest(),
            'rows': rows, 'complete': True}


class NativeRecordTests(unittest.TestCase):
    def test_complete_record_summary_is_offline_and_conservative(self):
        summary = summarize(record_fixture())
        self.assertTrue(summary['verified'])
        self.assertEqual((summary['requests'], summary['pairs'], summary['unknown_diagnoses']),
                         (168, 84, 168))
        self.assertEqual(summary['positive_controls'], {'checked': 24, 'failures': []})
        self.assertEqual(len(summary['configurations']), 12)
        self.assertEqual(summary['differences'], [])

    def test_fidelity_differences_are_observations_and_failed_controls_remain_visible(self):
        record = record_fixture()
        proxy = record['rows'][14]
        proxy['status'] = 500
        proxy['body_base64'] = base64.b64encode(b'failed setup').decode()
        proxy['body_sha256'] = hashlib.sha256(b'failed setup').hexdigest()
        proxy['headers']['content-type'] = []
        summary = summarize(record)
        self.assertFalse(summary['verified'])
        self.assertEqual(summary['differences'][0]['fields'], ['status', 'body', 'headers'])
        self.assertEqual(len(summary['positive_controls']['failures']), 1)
        self.assertEqual(summary['unknown_diagnoses'], 168)

    def test_incomplete_duplicate_or_changed_matrix_rejected(self):
        for mutate in [lambda r: r.update(complete=False),
                       lambda r: r['rows'].pop(),
                       lambda r: r['rows'].__setitem__(0, deepcopy(r['rows'][1])),
                       lambda r: r['definitions']['versions'].update({'python-mcp': '0'}),
                       lambda r: r.update(definition_sha256='0' * 64)]:
            with self.subTest(mutate=mutate):
                record = record_fixture()
                mutate(record)
                with self.assertRaises(RecordError):
                    summarize(record)

    def test_malformed_wire_evidence_rejected(self):
        mutations = [lambda r: r.update(status=True),
                     lambda r: r.update(body_sha256='0' * 64),
                     lambda r: r.update(body_base64='%%%'),
                     lambda r: r.update(body_base64=r['body_base64'] + '\n'),
                     lambda r: r['headers'].update({'x-private': ['secret']}),
                     lambda r: r['headers'].update({'content-type': ['a', 'b']}),
                     lambda r: r['headers'].update({'content-type': ['unsafe\nvalue']}),
                     lambda r: r['diagnostic'].update(reason='authorization'),
                     lambda r: r.update(unexpected='private')]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                record = record_fixture()
                mutate(record['rows'][0])
                with self.assertRaises(RecordError):
                    summarize(record)

    def test_file_boundary_and_actionable_cli_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'record.json'
            for content in [b'{"complete":true,"complete":false}', b'[]', b'{',
                            b' ' * (2 * 1024 * 1024 + 1)]:
                path.write_bytes(content)
                with self.assertRaises(RecordError):
                    load_record(path)
            path.write_bytes(b'{"private":"must-not-echo"')
            result = subprocess.run([sys.executable, '-m', 'mcp_connect_diagnoser',
                                     'summarize', str(path)], capture_output=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 2)
            error = json.loads(result.stderr)
            self.assertEqual(error['error']['code'], 'invalid_record')
            self.assertIn('next_step', error['error'])
            self.assertTrue(error['requestID'])
            self.assertNotIn('must-not-echo', result.stderr.decode())
            path.write_text(json.dumps(record_fixture()))
            result = subprocess.run([sys.executable, '-m', 'mcp_connect_diagnoser',
                                     'summarize', str(path)], capture_output=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertTrue(json.loads(result.stdout)['verified'])
            failed = record_fixture()
            failed['rows'][0]['status'] = 500
            path.write_text(json.dumps(failed))
            result = subprocess.run([sys.executable, '-m', 'mcp_connect_diagnoser',
                                     'summarize', str(path)], capture_output=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads(result.stdout)['verified'])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFOs")
    def test_cli_rejects_nonregular_native_record_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PRIVATE-input.fifo"
            os.mkfifo(path)
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "mcp_connect_diagnoser", "summarize", str(path)],
                    capture_output=True, timeout=2, check=False,
                )
            except subprocess.TimeoutExpired:
                self.fail("summarize blocked opening a non-regular input")
            self.assertEqual(result.returncode, 2)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"]["code"], "invalid_record")
            self.assertTrue(error["requestID"])
            self.assertNotIn("PRIVATE", result.stderr.decode())

    def test_invalid_utf8_is_a_record_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'record.json'
            path.write_bytes(b'\xff')
            with self.assertRaises(RecordError):
                load_record(path)

    def test_existing_native_record_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'record.json'
            path.write_bytes(b'retained failed attempt')
            with self.assertRaises(FileExistsError):
                run_matrix(directory, 'unused', 'unused', path)
            self.assertEqual(path.read_bytes(), b'retained failed attempt')


if __name__ == '__main__':
    unittest.main()
