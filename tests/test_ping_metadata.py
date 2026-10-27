"""Wire-level compatibility with common RequestParams / EmptyResult metadata."""
import json
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mcp_connect_diagnoser.session_probe import PROTOCOLS, probe_session


@contextmanager
def metadata_server(*, version=PROTOCOLS[0], params=None, result=None, send_ping=False):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def reply(self, status, body=b'', content_type='application/json'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            message = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((message, self.headers.get('MCP-Protocol-Version')))
            if 'method' not in message or message['method'] == 'notifications/initialized':
                self.reply(202)
                return
            method = message['method']
            answer = ({'protocolVersion': version, 'serverInfo': {'name': 'fixture', 'version': '1'},
                       'capabilities': {}} if method == 'initialize' else result)
            response = {'jsonrpc': '2.0', 'id': message['id'], 'result': answer}
            if method == 'ping' and send_ping:
                server_ping = {'jsonrpc': '2.0', 'id': 'server-17', 'method': 'ping', 'params': params}
                body = ''.join('data: ' + json.dumps(item) + '\n\n'
                               for item in (server_ping, response)).encode()
                self.reply(200, body, 'text/event-stream')
            else:
                self.reply(200, json.dumps(response).encode())

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/mcp', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


class PingMetadataTests(unittest.TestCase):
    def test_result_metadata_is_accepted_without_disclosure(self):
        for version in PROTOCOLS:
            with self.subTest(version=version), metadata_server(
                    version=version, result={'_meta': {'private': 'DO-NOT-ECHO'}}) as (url, calls):
                report = probe_session(url)
                self.assertTrue(report['verified'], report)
                self.assertEqual(report['protocol_version'], version)
                self.assertNotIn('DO-NOT-ECHO', json.dumps(report))
                self.assertTrue(all(version == v for m, v in calls if m.get('method') != 'initialize'))

    def test_server_ping_metadata_and_progress_tokens_are_accepted(self):
        for token in ('token', 7, 0.5):
            for version in PROTOCOLS:
                with self.subTest(token=token, version=version), metadata_server(
                        version=version, params={'_meta': {'progressToken': token,
                                                          'private': 'DO-NOT-ECHO'}},
                        result={}, send_ping=True) as (url, calls):
                    report = probe_session(url)
                    self.assertTrue(report['verified'], report)
                    self.assertEqual(report['server_pings_answered'], 1)
                    replies = [(m, v) for m, v in calls if m.get('id') == 'server-17']
                    self.assertEqual(replies, [({'jsonrpc': '2.0', 'id': 'server-17', 'result': {}}, version)])
                    self.assertNotIn('DO-NOT-ECHO', json.dumps(report))

    def test_empty_objects_remain_accepted(self):
        with metadata_server(params={}, result={}, send_ping=True) as (url, _):
            self.assertTrue(probe_session(url)['verified'])

    def test_common_result_extension_is_ignored_not_executed(self):
        with metadata_server(result={'_meta': {}, 'example.extension': {'instruction': 'DO-NOT-ECHO'}}) as (url, _):
            report = probe_session(url)
            self.assertTrue(report['verified'], report)
            self.assertNotIn('DO-NOT-ECHO', json.dumps(report))

    def test_nonobject_results_and_metadata_remain_invalid(self):
        for result in (None, [], True, 0, {'_meta': None}, {'_meta': []}, {'_meta': True}):
            with self.subTest(result=result), metadata_server(result=result) as (url, _):
                report = probe_session(url)
                self.assertFalse(report['verified'])
                self.assertEqual(report['failure']['code'], 'invalid_ping')

    def test_invalid_request_metadata_does_not_get_a_success_reply(self):
        for params in (None, [], True, {'_meta': None}, {'_meta': []},
                       {'_meta': {'progressToken': True}}, {'_meta': {'progressToken': {}}},
                       {'command': 'DO-NOT-ECHO'}):
            with self.subTest(params=params), metadata_server(params=params, result={}, send_ping=True) as (url, calls):
                report = probe_session(url)
                self.assertFalse(report['verified'])
                self.assertEqual(report['failure']['code'], 'invalid_server_request')
                self.assertFalse(any(m.get('id') == 'server-17' for m, _ in calls))
                self.assertNotIn('DO-NOT-ECHO', json.dumps(report))
