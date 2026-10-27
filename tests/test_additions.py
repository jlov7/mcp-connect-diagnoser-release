"""Owned services exercise the four approved local developer workflows."""
import io
import json
import os
import tempfile
import threading
import time
import unittest
import uuid
from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


@contextmanager
def development_service():
    calls, pending, replies = [], {}, {}
    stop = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def reply(self, status, body=b'', media='application/json', headers=()):
            self.send_response(status)
            self.send_header('Content-Type', media)
            self.send_header('Content-Length', str(len(body)))
            for key, value in headers:
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(body)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append({'verb': 'POST', 'path': self.path, 'request': request,
                          'headers': dict(self.headers), 'time': time.monotonic()})
            if 'method' not in request:
                if (self.headers.get('MCP-Session-Id') != 'owned-session' or
                        self.headers.get('MCP-Protocol-Version') != '2025-11-25'):
                    return self.reply(400)
                self.reply(202)
                if request.get('result') == {} and request.get('id') in replies:
                    replies[request['id']].set()
                return
            method = request['method']
            if self.path == '/missing':
                return self.reply(404)
            if self.path == '/stall':
                stop.wait(2)
                return
            if self.path == '/silent-sse':
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.flush()
                stop.wait(2)
                return
            if method == 'notifications/initialized':
                return self.reply(202)
            if method == 'initialize':
                result = {'protocolVersion': '2025-11-25',
                          'serverInfo': {'name': 'UNTRUSTED-NAME', 'version': '1'},
                          'capabilities': {'tools': {}}}
                headers = [('MCP-Session-Id', 'owned-session')]
            elif method == 'ping':
                result, headers = {}, []
            elif method == 'tools/list':
                result = {'tools': [{'name': 'UNTRUSTED-TOOL', 'inputSchema': {'type': 'object'}}]}
                headers = []
            else:
                return self.reply(400)
            message = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
            if self.path in {'/pings', '/unsupported', '/ping-loop', '/duplicate-ping', '/combo'}:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Connection', 'close')
                for key, value in headers:
                    self.send_header(key, value)
                self.end_headers()
                self.close_connection = True
                count = 9 if self.path == '/ping-loop' else 2 if self.path == '/duplicate-ping' else 1
                for i in range(count):
                    server_id = 'server-' + str(request['id']) + '-' + str(0 if self.path == '/duplicate-ping' else i)
                    event = threading.Event()
                    replies[server_id] = event
                    incoming = {'jsonrpc': '2.0', 'id': server_id,
                                'method': 'sampling/createMessage' if self.path == '/unsupported' else 'ping'}
                    try:
                        self.wfile.write(b'data: ' + json.dumps(incoming).encode() + b'\n\n')
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    if not event.wait(0.7):
                        return
                if self.path == '/combo' and method == 'tools/list':
                    cursor = 'combo-' + str(request['id'])
                    pending[cursor] = message
                    self.wfile.write(b'id: ' + cursor.encode() + b'\nretry: 1\ndata:\n\n')
                    self.wfile.flush()
                    return
                try:
                    self.wfile.write(b'data: ' + json.dumps(message).encode() + b'\n\n')
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            resume = self.path in {'/resume', '/wrong-id', '/repeat-id', '/endless', '/long-retry', '/no-id'} and method == 'tools/list'
            resume = resume or self.path == '/init-resume' and method == 'initialize'
            if resume:
                cursor = 'event-' + str(request['id'])
                pending[cursor] = message
                prefix = b'' if self.path == '/no-id' else b'id: ' + cursor.encode() + b'\n'
                retry = b'5000' if self.path == '/long-retry' else b'5'
                return self.reply(200, prefix + b'retry: ' + retry + b'\ndata:\n\n', 'text/event-stream', headers)
            self.reply(200, json.dumps(message).encode(), headers=headers)

        def do_GET(self):
            calls.append({'verb': 'GET', 'path': self.path, 'headers': dict(self.headers), 'time': time.monotonic()})
            cursor = self.headers.get('Last-Event-ID')
            if (cursor not in pending or self.headers.get('MCP-Session-Id') != 'owned-session' or
                    self.headers.get('MCP-Protocol-Version') != '2025-11-25'):
                return self.reply(400)
            message = deepcopy(pending[cursor])
            if self.path == '/wrong-id':
                message['id'] = 999
            if self.path == '/endless':
                next_cursor = cursor + '-next'
                pending[next_cursor] = message
                return self.reply(200, b'id: ' + next_cursor.encode() + b'\nretry: 0\ndata:\n\n', 'text/event-stream')
            event_id = cursor if self.path == '/repeat-id' else cursor + '-done'
            self.reply(200, b'id: ' + event_id.encode() + b'\ndata: ' + json.dumps(message).encode() + b'\n\n', 'text/event-stream')

        def do_DELETE(self):
            calls.append({'verb': 'DELETE', 'path': self.path, 'headers': dict(self.headers)})
            self.reply(204)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port), calls
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class AdditionsTests(unittest.TestCase):
    def test_ping_and_resume_share_the_original_discovery_request(self):
        from mcp_connect_diagnoser.session_probe import probe_session
        with development_service() as (base, calls):
            result = probe_session(base + '/combo', timeout=2)
        self.assertTrue(result['verified'], result)
        self.assertEqual(result['server_pings_answered'], 3)
        self.assertEqual(result['reconnect_attempts'], 1)
        self.assertEqual(sum(c.get('request', {}).get('method') == 'tools/list' for c in calls), 1)

    def test_endpoint_set_bounds_labels_and_options_precede_every_connection(self):
        from mcp_connect_diagnoser.reports import probe_many
        from mcp_connect_diagnoser.session_probe import SessionInputError
        with development_service() as (base, calls):
            valid = {'schema_version': 1, 'targets': [{'label': 'local', 'url': base + '/ok'}]}
            invalid = [dict(valid, schema_version=True), dict(valid, targets=[]),
                       dict(valid, extra=True), dict(valid, targets=valid['targets'] * 2),
                       dict(valid, targets=[{'label': 'unsafe/value', 'url': base + '/ok'}]),
                       dict(valid, targets=[{'label': 'é', 'url': base + '/ok'}]),
                       dict(valid, targets=[{'label': str(i), 'url': base + '/ok'} for i in range(17)])]
            for inputs in invalid:
                with self.subTest(inputs=inputs), self.assertRaises(SessionInputError):
                    probe_many(inputs)
            for options in [{'timeout': True}, {'timeout': 0}, {'max_seconds': 31}, {'max_seconds': 0}]:
                with self.subTest(options=options), self.assertRaises(SessionInputError):
                    probe_many(valid, **options)
            self.assertEqual(calls, [])

    def test_report_comparison_rejects_malformed_typed_fields_without_echo(self):
        from mcp_connect_diagnoser.reports import compare_reports
        from mcp_connect_diagnoser.session_probe import SessionInputError, probe_session
        with development_service() as (base, _):
            valid = probe_session(base + '/ok')
        for field, value in [('schema_version', True), ('tools_checked', True),
                             ('reconnect_attempts', 3), ('server_pings_answered', -1),
                             ('stages', []), ('protocol_version', ['UNTRUSTED'])]:
            invalid = deepcopy(valid)
            invalid[field] = value
            with self.subTest(field=field), self.assertRaises(SessionInputError) as caught:
                compare_reports(valid, invalid)
            self.assertNotIn('UNTRUSTED', str(caught.exception))

    def test_json_inputs_reject_fifos_duplicates_and_non_utf8(self):
        from mcp_connect_diagnoser.reports import load_json
        from mcp_connect_diagnoser.session_probe import SessionInputError
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            for content in [b'{"targets":[],"targets":[]}', '{}'.encode('utf-16'), b' ' * (2 * 1024 * 1024 + 1)]:
                source.write_bytes(content)
                with self.assertRaises(SessionInputError):
                    load_json(source)
            fifo = Path(directory) / 'input.fifo'
            os.mkfifo(fifo)
            started = time.monotonic()
            with self.assertRaises(SessionInputError):
                load_json(fifo)
            self.assertLess(time.monotonic() - started, 0.5)

    def test_silent_sse_deadline_is_a_timeout_without_reconnect(self):
        from mcp_connect_diagnoser.session_probe import probe_session
        with development_service() as (base, calls):
            result = probe_session(base + '/silent-sse', timeout=1)
        self.assertEqual(result['failure']['code'], 'timeout')
        self.assertFalse(any(c['verb'] == 'GET' for c in calls))

    def test_server_ping_before_initialize_and_later_results(self):
        from mcp_connect_diagnoser.session_probe import probe_session
        with development_service() as (base, calls):
            result = probe_session(base + '/pings', timeout=3)
        self.assertTrue(result['verified'], result)
        self.assertEqual(result['server_pings_answered'], 3)
        answers = [c for c in calls if c['verb'] == 'POST' and 'method' not in c['request']]
        self.assertEqual(len(answers), 3)
        self.assertTrue(all(c['request']['result'] == {} for c in answers))
        self.assertNotIn('UNTRUSTED', json.dumps(result))

    def test_server_requests_are_allowlisted_bounded_and_not_executed(self):
        from mcp_connect_diagnoser.session_probe import probe_session
        for mode, expected, answered in [('unsupported', 'unsupported_server_request', 0),
                                         ('ping-loop', 'ping_limit', 8),
                                         ('duplicate-ping', 'invalid_server_request', 1)]:
            with self.subTest(mode=mode), development_service() as (base, calls):
                result = probe_session(base + '/' + mode, timeout=3)
                self.assertFalse(result['verified'])
                self.assertEqual(result['failure']['code'], expected)
                self.assertEqual(result['server_pings_answered'], answered)
                self.assertFalse(any(c.get('request', {}).get('method') == 'tools/call' for c in calls))

    def test_resume_uses_same_endpoint_get_cursor_and_retry_without_repost(self):
        from mcp_connect_diagnoser.session_probe import probe_session
        for mode in ['resume', 'init-resume']:
            with self.subTest(mode=mode), development_service() as (base, calls):
                result = probe_session(base + '/' + mode, timeout=3)
                self.assertTrue(result['verified'], result)
                self.assertEqual(result['reconnect_attempts'], 1)
                gets = [c for c in calls if c['verb'] == 'GET']
                self.assertEqual(len(gets), 1)
                prior = max(c['time'] for c in calls if c['verb'] == 'POST' and c['time'] < gets[0]['time'])
                self.assertGreaterEqual(gets[0]['time'] - prior, 0.004)
                self.assertEqual(gets[0]['headers']['Accept'], 'text/event-stream')
                self.assertEqual([c.get('request', {}).get('method') for c in calls].count('initialize'), 1)
                self.assertEqual([c.get('request', {}).get('method') for c in calls].count('tools/list'), 1)

    def test_replay_wrong_ids_and_unbounded_resumption_fail(self):
        from mcp_connect_diagnoser.session_probe import probe_session
        for mode, expected in [('wrong-id', 'invalid_rpc_response'), ('repeat-id', 'invalid_sse_id'),
                               ('endless', 'resume_limit'), ('long-retry', 'timeout'), ('no-id', 'unresumable_stream')]:
            with self.subTest(mode=mode), development_service() as (base, calls):
                result = probe_session(base + '/' + mode, timeout=1)
                self.assertFalse(result['verified'])
                self.assertEqual(result['failure']['code'], expected)
                self.assertLessEqual(sum(c['verb'] == 'GET' for c in calls), 2)
                self.assertNotIn('event-', json.dumps(result))

    def test_endpoint_set_keeps_healthy_broken_and_deadline_results(self):
        from mcp_connect_diagnoser.reports import probe_many
        with development_service() as (base, _):
            inputs = {'schema_version': 1, 'targets': [{'label': label, 'url': base + '/' + route}
                      for label, route in [('catalog', 'ok'), ('old-route', 'missing'), ('stalled', 'stall')]]}
            started = time.monotonic()
            result = probe_many(inputs, timeout=1, max_seconds=2)
        self.assertLess(time.monotonic() - started, 2.8)
        self.assertFalse(result['verified'])
        rows = {r['label']: r for r in result['targets']}
        self.assertTrue(rows['catalog']['report']['verified'])
        self.assertFalse(rows['old-route']['report']['verified'])
        self.assertFalse(rows['stalled']['report']['verified'])
        self.assertNotIn(base, json.dumps(result))

    def test_endpoint_set_prevalidates_every_target_before_network(self):
        from mcp_connect_diagnoser.reports import probe_many
        from mcp_connect_diagnoser.session_probe import SessionInputError
        with development_service() as (base, calls):
            bad = {'schema_version': 1, 'targets': [{'label': 'valid', 'url': base + '/ok'},
                   {'label': 'remote', 'url': 'http://192.0.2.1:9/mcp'}]}
            with self.assertRaises(SessionInputError):
                probe_many(bad)
            self.assertEqual(calls, [])

    def test_comparison_ignores_ids_text_and_timing_but_detects_observations(self):
        from mcp_connect_diagnoser.reports import compare_reports
        from mcp_connect_diagnoser.session_probe import SessionInputError, probe_session
        with development_service() as (base, _):
            before = probe_session(base + '/ok')
            failed = probe_session(base + '/missing')
        same = deepcopy(before)
        same['requestID'] = str(uuid.uuid4())
        same['summary'] = 'UNTRUSTED-REPORT-TEXT'
        result = compare_reports(before, same)
        self.assertTrue(result['same_observations'])
        self.assertNotIn('UNTRUSTED', json.dumps(result))
        self.assertFalse(compare_reports(before, failed)['same_observations'])
        malformed = deepcopy(before)
        malformed['tools_checked'] = 'UNTRUSTED'
        with self.assertRaises(SessionInputError):
            compare_reports(before, malformed)
        old = deepcopy(before)
        old['schema_version'] = 1
        for field in ['report_type', 'server_pings_answered', 'reconnect_attempts']:
            old.pop(field, None)
        self.assertTrue(compare_reports(before, old)['same_observations'])

    def test_new_cli_commands_use_private_exclusive_reports(self):
        from mcp_connect_diagnoser.__main__ import main
        with tempfile.TemporaryDirectory() as directory, development_service() as (base, calls):
            directory = Path(directory)
            source, output, compared = [directory / name for name in ['targets.json', 'set.json', 'diff.json']]
            source.write_text(json.dumps({'schema_version': 1, 'targets': [{'label': 'catalog', 'url': base + '/ok'}]}))
            with patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(main(['probe-many', str(source), '--output', str(output)]), 0)
                count = len(calls)
                with patch('sys.stderr', new_callable=io.StringIO):
                    self.assertEqual(main(['probe-many', str(source), '--output', str(output)]), 2)
                self.assertEqual(len(calls), count)
                self.assertEqual(main(['compare', str(output), str(output), '--output', str(compared)]), 0)
            self.assertTrue(json.loads(compared.read_text())['same_observations'])
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
