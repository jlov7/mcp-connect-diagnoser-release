"""Real HTTP user-session checks, independent of the frozen middleware matrix."""
import importlib
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


@contextmanager
def session_server(mode='json'):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def reply(self, status, body=b'', content_type='application/json', headers=()):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            truncated = mode == 'truncated-body' or (mode == 'truncated-notification' and status == 202)
            self.send_header('Content-Length', str(len(body) + (10 if truncated else 0)))
            if truncated:
                self.send_header('Connection', 'close')
                self.close_connection = True
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            method = request['method']
            calls.append((method, dict(self.headers), request))
            if mode in {'401', '403', '404', '406', '500'}:
                return self.reply(int(mode), b'PRIVATE-RESPONSE-TEXT')
            if mode == 'redirect':
                return self.reply(307, headers=[('Location', '/must-not-follow')])
            if mode == 'slow':
                time.sleep(1.3)
                return self.reply(200, b'{}')
            if mode == 'trickle':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', '50')
                self.end_headers()
                for _ in range(30):
                    try:
                        self.wfile.write(b' ')
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    time.sleep(0.1)
                return
            if method != 'initialize' and (
                    self.headers.get('MCP-Session-Id') != 'private-session-value' or
                    self.headers.get('MCP-Protocol-Version') != '2025-11-25'):
                return self.reply(400)
            if method == 'notifications/initialized':
                return self.reply(200 if mode == 'bad-notification' else 202)
            if method == 'initialize':
                result = {'protocolVersion': '2025-11-25',
                          'serverInfo': {'name': 'PRIVATE-SERVER-NAME', 'version': '1'},
                          'capabilities': {} if mode == 'no-tools' else {'tools': {}}}
                if mode == 'bad-version':
                    result['protocolVersion'] = 'unimplemented'
                if mode == 'bad-capability':
                    result['capabilities']['tools'] = True
                headers = [('MCP-Session-Id', 'private-session-value')]
                if mode == 'duplicate-session':
                    headers.append(('mcp-session-id', 'other-value'))
            elif method == 'ping':
                result, headers = {}, []
            elif method == 'tools/list':
                result = {'tools': [{'name': 'PRIVATE-TOOL-NAME',
                                    'inputSchema': {'type': 'object'}}]}
                if mode in {'pages', 'duplicate-tools'} and 'params' not in request:
                    result['nextCursor'] = 'PRIVATE-CURSOR'
                if mode == 'pages' and 'params' in request:
                    result['tools'][0]['name'] = 'PRIVATE-SECOND-TOOL'
                if mode == 'pages-loop':
                    result['tools'] = []
                    result['nextCursor'] = 'PRIVATE-CURSOR'
                if mode == 'endless-pages':
                    result['tools'] = []
                    result['nextCursor'] = str(request['id'])
                if mode == 'bad-tools':
                    result['tools'][0]['inputSchema'] = 'bad'
                headers = []
            else:
                return self.reply(400)
            message = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
            if mode == 'bad-id':
                message['id'] = True
            if mode == 'rpc-error' and method == 'ping':
                message.pop('result')
                message['error'] = {'code': -32603, 'message': 'PRIVATE-ERROR-TEXT'}
            body = json.dumps(message).encode()
            if mode == 'utf16-json':
                body = json.dumps(message).encode('utf-16')
            if mode == 'utf32-json':
                body = json.dumps(message).encode('utf-32')
            if mode == 'duplicate-json':
                body = b'{"jsonrpc":"2.0","id":1,"id":1,"result":{}}'
            if mode == 'nonfinite-json':
                body = body[:-1] + b',"extra":1e999}'
            if mode == 'surrogate-json':
                body = body[:-1] + b',"extra":"\\ud800"}'
            if mode == 'large':
                body = b' ' * (256 * 1024 + 1)
            if mode == 'html':
                return self.reply(200, b'<html>PRIVATE-RESPONSE-TEXT</html>', 'text/html')
            if mode in {'sse', 'sse-notification', 'sse-cr', 'sse-bom', 'sse-prime', 'sse-prime-space'}:
                body = (b': keepalive\r\n\r\nevent: message\r\ndata: ' + body + b'\r\n\r\n')
                if mode in {'sse-prime', 'sse-prime-space'}:
                    empty = b'data: \n\n' if mode == 'sse-prime-space' else b'data:\n\n'
                    body = b'id: initial-event-' + str(request['id']).encode() + b'\n' + empty + body
                if mode == 'sse-notification':
                    body = b'data: {"jsonrpc":"2.0","method":"notifications/message","params":{"text":"PRIVATE-NOTIFICATION"}}\n\n' + body
                if mode == 'sse-cr':
                    body = body.replace(b'\r\n', b'\r')
                if mode == 'sse-bom':
                    body = b'\xef\xbb\xbfdata: ' + json.dumps(message).encode() + b'\n\n'
                return self.reply(200, body, 'text/event-stream; charset=utf-8', headers)
            return self.reply(200, body, headers=headers)

        def do_DELETE(self):
            calls.append(('DELETE', dict(self.headers), None))
            self.reply(405 if mode == 'no-delete' else 204)

        def log_message(self, *args):
            pass

    class Server(ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            if not isinstance(sys.exc_info()[1], ConnectionError):
                super().handle_error(request, client_address)

    server = Server(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/custom-mcp', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class SessionProbeTests(unittest.TestCase):
    def run_probe(self, mode='json', **kwargs):
        from mcp_connect_diagnoser.session_probe import probe_session
        with session_server(mode) as (url, calls):
            result = probe_session(url, **kwargs)
        return result, calls

    def test_cli_runs_a_complete_user_endpoint_session(self):
        from mcp_connect_diagnoser.__main__ import main
        with session_server() as (url, calls), patch('sys.stdout', new_callable=io.StringIO) as out:
            status = main(['probe', url])
        self.assertEqual(status, 0)
        result = json.loads(out.getvalue())
        self.assertTrue(result['verified'])
        self.assertEqual([c[0] for c in calls],
                         ['initialize', 'notifications/initialized', 'ping', 'tools/list', 'DELETE'])
        self.assertEqual(result['tools_checked'], 1)
        self.assertNotIn('PRIVATE-', out.getvalue())
        self.assertNotIn('private-session-value', out.getvalue())

    def test_json_sse_and_capability_absence(self):
        for mode in ['json', 'sse', 'sse-notification', 'sse-cr', 'no-tools', 'no-delete']:
            with self.subTest(mode=mode):
                result, calls = self.run_probe(mode)
                self.assertTrue(result['verified'], result)
                self.assertEqual(result['protocol_version'], '2025-11-25')
                self.assertEqual(result['tools_checked'], 0 if mode == 'no-tools' else 1)
                self.assertNotIn('tools/call', [c[0] for c in calls])
                self.assertEqual(calls[-1][0], 'DELETE')

    def test_sse_empty_priming_event_does_not_hide_following_rpc_response(self):
        for mode in ['sse-prime', 'sse-prime-space']:
            with self.subTest(mode=mode):
                result, calls = self.run_probe(mode)
                self.assertTrue(result['verified'], result)
                self.assertEqual(result['tools_checked'], 1)
                self.assertEqual([c[0] for c in calls],
                                 ['initialize', 'notifications/initialized', 'ping', 'tools/list', 'DELETE'])

    def test_untrusted_responses_give_bounded_actionable_failures(self):
        modes = ['401', '403', '404', '406', '500', 'redirect', 'html', 'bad-id',
                 'bad-version', 'duplicate-json', 'duplicate-session', 'bad-notification',
                 'bad-capability', 'bad-tools', 'rpc-error', 'large', 'pages-loop',
                 'endless-pages', 'duplicate-tools', 'nonfinite-json', 'surrogate-json']
        for mode in modes:
            with self.subTest(mode=mode):
                result, calls = self.run_probe(mode)
                self.assertFalse(result['verified'], result)
                self.assertTrue(result['failure']['next_step'])
                self.assertEqual(result['failure']['cause'], 'unknown')
                self.assertNotIn('PRIVATE-', json.dumps(result))
                self.assertNotIn('private-session-value', json.dumps(result))
                if mode == 'redirect':
                    self.assertEqual(len(calls), 1)

    def test_pagination_counts_all_pages_and_propagates_session(self):
        result, calls = self.run_probe('pages')
        self.assertTrue(result['verified'])
        self.assertEqual((result['tools_checked'], result['tool_pages_checked']), (2, 2))
        self.assertEqual([c[0] for c in calls].count('tools/list'), 2)
        self.assertTrue(all(c[1].get('MCP-Session-Id') == 'private-session-value'
                            for c in calls[1:]))

    def test_absolute_deadline_stops_slow_and_trickling_responses(self):
        for mode in ['slow', 'trickle']:
            with self.subTest(mode=mode):
                started = time.monotonic()
                result, _ = self.run_probe(mode, timeout=1)
                self.assertFalse(result['verified'])
                self.assertEqual(result['failure']['code'], 'timeout')
                self.assertLess(time.monotonic() - started, 1.8)

    def test_invalid_targets_are_rejected_before_network_or_value_echo(self):
        from mcp_connect_diagnoser.session_probe import SessionInputError, probe_session
        for url in ['https://127.0.0.1:9/mcp', 'http://localhost:9/mcp',
                    'http://192.0.2.1:9/mcp', 'http://127.0.0.1/mcp',
                    'http://user:PRIVATE@127.0.0.1:9/mcp',
                    'http://127.0.0.1:9/mcp?PRIVATE=x', 'http://127.0.0.1:9/mcp#PRIVATE',
                    'http://127.0.0.1:9/\nPRIVATE']:
            with self.subTest(url=url), self.assertRaises(SessionInputError) as error:
                probe_session(url)
            self.assertNotIn('PRIVATE', str(error.exception))
        for timeout in [True, 0, 31, 1.5]:
            with self.assertRaises(SessionInputError):
                probe_session('http://127.0.0.1:9/mcp', timeout=timeout)

    def test_cli_output_is_exclusive_and_connection_failure_is_not_usage_error(self):
        with tempfile.TemporaryDirectory() as directory, session_server() as (url, calls):
            output = Path(directory) / 'private-report.json'
            output.write_text('retained')
            command = [sys.executable, '-m', 'mcp_connect_diagnoser', 'probe', url,
                       '--output', str(output)]
            result = subprocess.run(command, capture_output=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(), 'retained')
            self.assertEqual(calls, [])
            output.unlink()
            result = subprocess.run(command, capture_output=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(output.read_text())['verified'])
        result = subprocess.run([sys.executable, '-m', 'mcp_connect_diagnoser', 'probe', url],
                                capture_output=True, timeout=5, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['failure']['code'], 'connection_failed')

    def test_proxy_environment_is_ignored(self):
        with patch.dict('os.environ', {'http_proxy': 'http://192.0.2.1:9',
                                     'HTTP_PROXY': 'http://192.0.2.1:9'}):
            result, _ = self.run_probe()
        self.assertTrue(result['verified'])

    def test_sse_ignores_one_leading_utf8_bom(self):
        result, _ = self.run_probe('sse-bom')
        self.assertTrue(result['verified'], result)

    def test_json_must_be_utf8_even_if_parser_can_autodetect_other_encodings(self):
        for mode in ['utf16-json', 'utf32-json']:
            with self.subTest(mode=mode):
                result, _ = self.run_probe(mode)
                self.assertFalse(result['verified'], result)
                self.assertEqual(result['failure']['code'], 'invalid_json')

    def test_premature_eof_cannot_satisfy_declared_response_length(self):
        for mode in ['truncated-body', 'truncated-notification']:
            with self.subTest(mode=mode):
                result, _ = self.run_probe(mode)
                self.assertFalse(result['verified'], result)
                self.assertEqual(result['failure']['code'], 'truncated_body')

    def test_buffered_report_failure_is_a_private_structured_error(self):
        try:
            importlib.import_module('resource')
        except ImportError:
            self.skipTest('requires POSIX file-size resource limit')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'new-report.json'
            script = '''import resource, signal, sys
from unittest.mock import patch
from mcp_connect_diagnoser.__main__ import main
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (100, 100))
with patch('mcp_connect_diagnoser.__main__.probe_session', return_value={'verified': True, 'scope': 'local test' * 100}):
    code = main(['probe', 'http://127.0.0.1:9/mcp', '--output', sys.argv[1]])
raise SystemExit(code)
'''
            result = subprocess.run([sys.executable, '-c', script, str(output)],
                                    capture_output=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 2, result.stderr.decode())
            error = json.loads(result.stderr)
            self.assertEqual(error['error']['code'], 'output_failed')
            self.assertTrue(error['requestID'])
            self.assertNotIn(str(output), result.stderr.decode())
            self.assertLessEqual(output.stat().st_size, 100)


if __name__ == '__main__':
    unittest.main()
