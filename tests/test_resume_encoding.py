"""Real HTTP/SSE behavior: UTF-8 cursor bytes, finite retries and safe RPC advice."""
import json
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mcp_connect_diagnoser.session_probe import PROTOCOLS, probe_session


@contextmanager
def service(*, cursor='café-📦', version=PROTOCOLS[0], rpc_error=None, get_status=200,
            complete=False):
    calls = []
    secret = 'PRIVATE-DO-NOT-ECHO'

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def send(self, status, body=b'', media='application/json', session=False):
            self.send_response(status)
            self.send_header('Content-Type', media)
            self.send_header('Content-Length', str(len(body)))
            if session:
                self.send_header('MCP-Session-Id', 'synthetic-session')
            self.end_headers()
            self.wfile.write(body)

        def record(self, message=None):
            calls.append({'verb': self.command, 'message': message,
                          'version': self.headers.get('MCP-Protocol-Version'),
                          'session': self.headers.get('MCP-Session-Id'),
                          # http.server preserves HTTP header bytes as Latin-1.
                          'cursor_bytes': self.headers.get('Last-Event-ID', '').encode('latin-1')})

        def do_POST(self):
            message = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.record(message)
            if message['method'] == 'notifications/initialized':
                self.send(202)
            elif message['method'] == 'initialize':
                response = {'jsonrpc': '2.0', 'id': 1, 'result': {
                    'protocolVersion': version, 'capabilities': {},
                    'serverInfo': {'name': secret, 'version': 'fixture'}}}
                self.send(200, json.dumps(response).encode(), session=True)
            elif rpc_error is not None:
                response = {'jsonrpc': '2.0', 'id': 2, 'error': {
                    'code': rpc_error, 'message': secret, 'data': {'detail': secret}}}
                self.send(200, json.dumps(response).encode())
            else:
                # End the stream after a resume cursor, without the RPC result.
                result = 'data: {"jsonrpc":"2.0","id":2,"result":{}}\n' if complete else ''
                body = ('retry: 0\nid: ' + cursor + '\n' + result + '\n').encode('utf-8')
                self.send(200, body, 'text/event-stream')

        def do_GET(self):
            self.record()
            body = b'data: {"jsonrpc":"2.0","id":2,"result":{}}\n\n'
            self.send(get_status, body, 'text/event-stream')

        def do_DELETE(self):
            self.record()
            self.send(204)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever,
                              kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/mcp', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


class ResumeEncodingTests(unittest.TestCase):
    def test_unicode_cursors_survive_exactly_across_all_supported_versions(self):
        for version in PROTOCOLS:
            for cursor in ('café-17', 'record-📦-東京'):
                with self.subTest(version=version, cursor=cursor), service(
                        cursor=cursor, version=version) as (url, calls):
                    report = probe_session(url, timeout=3)
                    self.assertTrue(report['verified'], report)
                    self.assertEqual(report['reconnect_attempts'], 1)
                    get, = [row for row in calls if row['verb'] == 'GET']
                    self.assertEqual(get['cursor_bytes'], cursor.encode('utf-8'))
                    self.assertEqual(get['session'], 'synthetic-session')
                    self.assertEqual(get['version'], version)
                    self.assertEqual(sum(row['message'] is not None and
                                         row['message'].get('method') == 'ping'
                                         for row in calls), 1)
                    self.assertEqual(report['cleanup']['outcome'], 'terminated')
                    self.assertNotIn(cursor, json.dumps(report, ensure_ascii=False))
                    self.assertNotIn('PRIVATE-DO-NOT-ECHO', json.dumps(report))

    def test_ascii_cursor_and_internal_space_are_lossless(self):
        for cursor in ('ascii-17', 'record 17'):
            with self.subTest(cursor=cursor), service(cursor=cursor) as (url, calls):
                report = probe_session(url, timeout=3)
                self.assertTrue(report['verified'], report)
                self.assertEqual([row['cursor_bytes'] for row in calls if row['verb'] == 'GET'],
                                 [cursor.encode('utf-8')])

    def test_byte_limit_is_applied_to_non_ascii_cursors(self):
        for cursor in ('📦' * 257, 'x' * 1025):
            with self.subTest(size=len(cursor.encode())), service(cursor=cursor) as (url, calls):
                report = probe_session(url, timeout=3)
                self.assertFalse(report['verified'])
                self.assertEqual(report['failure']['code'], 'invalid_sse_id')
                self.assertFalse(any(row['verb'] == 'GET' for row in calls))
                self.assertEqual(report['cleanup']['outcome'], 'terminated')

    def test_exact_utf8_byte_limit_is_accepted(self):
        for cursor in ('x' * 1024, '\U0001f4e6' * 256):
            with self.subTest(bytes=len(cursor.encode('utf-8'))), service(cursor=cursor) as (url, calls):
                report = probe_session(url, timeout=3)
                self.assertTrue(report['verified'], report)
                self.assertEqual([row['cursor_bytes'] for row in calls if row['verb'] == 'GET'],
                                 [cursor.encode('utf-8')])
                self.assertEqual(report['cleanup']['outcome'], 'terminated')

    def test_complete_stream_preserves_existing_character_bound(self):
        for cursor in ('\u00e9' * 1024, '\U0001f4e6' * 1024):
            with self.subTest(bytes=len(cursor.encode('utf-8'))), service(
                    cursor=cursor, complete=True) as (url, calls):
                report = probe_session(url, timeout=3)
                self.assertTrue(report['verified'], report)
                self.assertEqual(report['reconnect_attempts'], 0)
                self.assertFalse(any(row['verb'] == 'GET' for row in calls))
                self.assertEqual(report['cleanup']['outcome'], 'terminated')

    def test_header_controls_and_edge_whitespace_remain_refused(self):
        for cursor in ('bad\x01id', 'bad\x7fid', ' leading', 'trailing '):
            with self.subTest(cursor=repr(cursor)), service(cursor=cursor) as (url, calls):
                report = probe_session(url, timeout=3)
                self.assertFalse(report['verified'])
                self.assertFalse(any(row['verb'] == 'GET' for row in calls))
                self.assertEqual(report['failure']['code'], 'invalid_sse_id')

    def test_failed_resume_is_not_reposted_or_causally_overstated(self):
        with service(cursor='é-17', get_status=403) as (url, calls):
            report = probe_session(url, timeout=3)
            self.assertFalse(report['verified'])
            self.assertEqual(report['failure']['code'], 'http_rejected')
            self.assertEqual(report['failure']['cause'], 'unknown')
            self.assertEqual(report['reconnect_attempts'], 1)
            self.assertEqual(sum(row['message'] is not None and
                                 row['message'].get('method') == 'ping' for row in calls), 1)
            self.assertEqual(report['cleanup']['outcome'], 'terminated')

    def test_standard_rpc_errors_have_specific_bounded_next_actions(self):
        expected = {-32700: 'parse error', -32600: 'invalid request',
                    -32601: 'method not found', -32602: 'invalid params',
                    -32603: 'internal error'}
        for code, phrase in expected.items():
            with self.subTest(code=code), service(rpc_error=code) as (url, calls):
                report = probe_session(url, timeout=3)
                self.assertFalse(report['verified'])
                self.assertEqual(report['failure']['code'], 'rpc_error')
                self.assertIn(phrase, report['failure']['next_step'].lower())
                self.assertEqual(report['failure']['cause'], 'unknown')
                self.assertNotIn('PRIVATE-DO-NOT-ECHO', json.dumps(report))
                self.assertFalse(any(row['verb'] == 'GET' for row in calls))
                self.assertEqual(report['cleanup']['outcome'], 'terminated')

    def test_unrecognized_error_keeps_generic_advice(self):
        with service(rpc_error=-32087) as (url, _):
            report = probe_session(url, timeout=3)
            self.assertEqual(report['failure']['code'], 'rpc_error')
            self.assertIn('trusted logs', report['failure']['next_step'])
            self.assertNotIn('32087', json.dumps(report))

    def test_boolean_error_code_remains_malformed(self):
        with service(rpc_error=True) as (url, _):
            report = probe_session(url, timeout=3)
            self.assertEqual(report['failure']['code'], 'invalid_rpc_response')
            self.assertNotIn('PRIVATE-DO-NOT-ECHO', json.dumps(report))
