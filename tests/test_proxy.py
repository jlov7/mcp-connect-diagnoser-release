import importlib.util
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from mcp_connect_diagnoser.core import LocalFixture, ProbeError, diagnose, probe


@contextmanager
def native_response(headers):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = b'\x00native rejection\xff'
            self.send_response(401)
            for name, value in headers:
                self.send_header(name, value)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/mcp'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


class HardenedProbeTests(unittest.TestCase):
    def test_loopback_requests_ignore_ambient_proxy(self):
        # A controlled local proxy target; no real credential or external network.
        with (LocalFixture() as target, LocalFixture() as unwanted,
              patch('urllib.request.getproxies', return_value={'http': unwanted.url}),
              patch('urllib.request.proxy_bypass', return_value=False)):
            self.assertEqual(probe(target.url)['status'], 200)

    def test_reason_header_names_are_case_insensitive(self):
        self.assertEqual(diagnose(403, {'X-FIXTURE-REJECTION': 'origin'}, True)['reason'], 'origin')

    def test_conflicting_case_variants_are_unknown(self):
        self.assertEqual(diagnose(403, {'X-Fixture-Rejection': 'origin',
                                      'x-fixture-rejection': 'host'}, True)['reason'], 'unknown')

    def test_status_reason_inconsistency_is_unknown(self):
        for code, reason in [(401, 'origin'), (403, 'authorization'), (401, 'host')]:
            self.assertEqual(diagnose(code, {'X-Fixture-Rejection': reason}, True)['reason'],
                             'unknown')


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('mcp_connect_diagnoser.proxy'),
                             'Missing actual loopback forwarding proxy')
        from mcp_connect_diagnoser.proxy import LoopbackProxy
        self.Proxy = LoopbackProxy

    def test_success_through_actual_proxy(self):
        with LocalFixture() as target, self.Proxy(target.url) as middle:
            self.assertEqual(probe(middle.url)['status'], 200)
            self.assertEqual(middle.forwarded, 1)

    def test_layer_preserved_then_unknown_when_metadata_removed(self):
        with LocalFixture() as target:
            for strip in [False, True]:
                with self.Proxy(target.url, strip_reason=strip) as middle:
                    r = probe(middle.url, origin='https://bad.invalid', trusted_fixture=True)
                    self.assertEqual(r['status'], 403)
                    self.assertEqual(r['diagnostic']['reason'], 'unknown' if strip else 'origin')
                    self.assertEqual(r['wire_header_present'], not strip)

    def test_bad_host_is_not_repaired_into_success(self):
        with LocalFixture() as target, self.Proxy(target.url) as middle:
            r = probe(middle.url, host_override='bad.invalid', trusted_fixture=True)
            self.assertEqual(r['diagnostic']['reason'], 'host')

    def test_multiple_failures_report_one_layer_not_all_conditions(self):
        with LocalFixture() as target, self.Proxy(target.url) as middle:
            r = probe(middle.url, origin='wrong', bearer='wrong', trusted_fixture=True)
            self.assertEqual(r['diagnostic']['reason'], 'origin')
            r = probe(middle.url, bearer='wrong', trusted_fixture=True)
            self.assertEqual(r['diagnostic']['reason'], 'authorization')

    def test_duplicate_auth_and_oversized_bodies_refused_before_forwarding(self):
        import http.client
        with LocalFixture() as target, self.Proxy(target.url) as middle:
            for duplicate in [True, False]:
                c = http.client.HTTPConnection('127.0.0.1', middle.port, timeout=2)
                c.putrequest('POST', '/mcp')
                c.putheader('Authorization', 'Bearer synthetic')
                if duplicate:
                    c.putheader('Authorization', 'Bearer other')
                c.putheader('Content-Length', '0' if duplicate else '4097')
                c.endheaders()
                response = c.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
                c.close()
            self.assertEqual(middle.forwarded, 0)

    def test_remote_target_is_not_a_proxy_option(self):
        for url in ['http://example.com:80/mcp', 'http://127.0.0.1:8/else',
                    'http://127.0.0.1:8/mcp?url=http://example.com']:
            with self.assertRaises(ProbeError):
                self.Proxy(url)

    def test_dead_upstream_is_unknown_not_an_auth_diagnosis(self):
        import socket
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        # The bound but non-listening socket prevents port reuse without offering HTTP.
        try:
            with self.Proxy(f'http://127.0.0.1:{port}/mcp') as middle:
                r = probe(middle.url, trusted_fixture=True)
                self.assertEqual(r['status'], 502)
                self.assertEqual(r['diagnostic']['reason'], 'unknown')
        finally:
            sock.close()

    def test_native_headers_and_exact_bytes_preserved_without_arbitrary_relay(self):
        import http.client
        headers = [('Content-Type', 'text/plain; charset=utf-8'),
                   ('WWW-Authenticate', 'Bearer error="invalid_token"'),
                   ('X-Private-Upstream', 'must-not-be-relayed')]
        with native_response(headers) as target, self.Proxy(target) as middle:
            conn = http.client.HTTPConnection('127.0.0.1', middle.port, timeout=2)
            try:
                conn.request('POST', '/mcp', body=b'{}')
                response = conn.getresponse()
                self.assertEqual(response.status, 401)
                self.assertEqual(response.read(), b'\x00native rejection\xff')
                self.assertEqual(response.headers['Content-Type'], 'text/plain; charset=utf-8')
                self.assertEqual(response.headers['WWW-Authenticate'], 'Bearer error="invalid_token"')
                self.assertIsNone(response.headers['X-Private-Upstream'])
            finally:
                conn.close()

    def test_duplicate_or_oversized_safe_response_headers_refused(self):
        for name in ['Content-Type', 'WWW-Authenticate']:
            for headers in [[(name, 'one'), (name, 'two')], [(name, 'x' * 1025)]]:
                with (self.subTest(name=name, count=len(headers)),
                      native_response(headers) as target, self.Proxy(target) as middle):
                    self.assertEqual(probe(middle.url)['status'], 502)

    def test_duplicate_negotiation_request_headers_refused_before_forwarding(self):
        import http.client
        with LocalFixture() as target, self.Proxy(target.url) as middle:
            for name in ['Content-Type', 'Accept']:
                conn = http.client.HTTPConnection('127.0.0.1', middle.port, timeout=2)
                try:
                    conn.putrequest('POST', '/mcp')
                    conn.putheader(name, 'application/json')
                    conn.putheader(name, 'text/plain')
                    conn.putheader('Content-Length', '0')
                    conn.endheaders()
                    response = conn.getresponse()
                    self.assertEqual(response.status, 400)
                    response.read()
                finally:
                    conn.close()
            self.assertEqual(middle.forwarded, 0)

class MatrixTests(unittest.TestCase):
    def test_full_three_route_eight_condition_census(self):
        from mcp_connect_diagnoser.proxy import run_matrix
        rows = run_matrix()['rows']
        self.assertEqual(len(rows), 24)
        for row in rows:
            first = ('host' if row['host_invalid'] else 'origin' if row['origin_invalid']
                     else 'authorization' if row['bearer_invalid'] else None)
            expected_code = 403 if first in ('host', 'origin') else 401 if first else 200
            self.assertEqual(row['status'], expected_code)
            self.assertEqual(row['diagnostic']['reason'],
                             first if first and row['route'] != 'stripped' else 'unknown')
