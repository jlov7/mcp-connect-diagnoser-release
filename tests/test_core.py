import socket
import unittest

from mcp_connect_diagnoser.core import LocalFixture, ProbeError, _NoRedirect, diagnose, probe


class WireTests(unittest.TestCase):
    def fixture_request(self, srv, framing, body=b'', *, truncate=False, host=None):
        conn = socket.create_connection(('127.0.0.1', srv.server.server_port), timeout=3)
        try:
            headers = (f'POST /mcp HTTP/1.1\r\nHost: {host or "127.0.0.1:" + str(srv.server.server_port)}\r\n'
                       'Origin: http://localhost:7000\r\n'
                       'Authorization: Bearer synthetic-fixture-token\r\n')
            conn.sendall(headers.encode() + framing + b'\r\n' + body)
            if truncate:
                conn.shutdown(socket.SHUT_WR)
            return conn.recv(4096).split(b'\r\n', 1)[0]
        finally:
            conn.close()

    def test_partial_body_has_read_timeout(self):
        with LocalFixture() as srv:
            self.assertIn(b'408', self.fixture_request(srv, b'Content-Length: 2\r\n', b'{'))

    def test_truncated_body_is_not_success(self):
        with LocalFixture() as srv:
            self.assertIn(b'400', self.fixture_request(
                srv, b'Content-Length: 2\r\n', b'{', truncate=True))

    def test_ambiguous_or_excessive_body_framing_rejected(self):
        framings = [b'Content-Length: 0\r\nContent-Length: 1\r\n',
                    b'Transfer-Encoding: chunked\r\n', b'Content-Length: 4097\r\n',
                    b'Content-Length: ' + b'9' * 5000 + b'\r\n']
        with LocalFixture() as srv:
            for framing in framings:
                with self.subTest(framing=framing[:50]):
                    self.assertIn(b'400', self.fixture_request(srv, framing))

    def test_guard_order_precedes_body_read(self):
        with LocalFixture() as srv:
            self.assertIn(b'403', self.fixture_request(
                srv, b'Content-Length: 2\r\n', host='bad.invalid'))

    def test_allowed_wire(self):
        with LocalFixture() as srv:
            self.assertEqual(probe(srv.url)['status'],200)

    def test_bad_host_rejected_first(self):
        with LocalFixture() as srv:
            r=probe(srv.url,host_override='bad.invalid',trusted_fixture=True)
            self.assertEqual((r['status'],r['diagnostic']['reason']),(403,'host'))

    def test_bad_origin_distinguished(self):
        with LocalFixture() as srv:
            r=probe(srv.url,origin='https://bad.invalid',trusted_fixture=True)
            self.assertEqual(r['diagnostic']['reason'],'origin')

    def test_auth_distinguished(self):
        with LocalFixture() as srv:
            r=probe(srv.url,bearer='wrong-synthetic',trusted_fixture=True)
            self.assertEqual((r['status'],r['diagnostic']['reason']),(401,'authorization'))

    def test_multiple_failures_only_first_rejected_layer_reported(self):
        with LocalFixture() as srv:
            r=probe(srv.url,bearer='wrong-synthetic',origin='https://bad.invalid',trusted_fixture=True)
            self.assertEqual(r['diagnostic']['reason'],'origin')

    def test_generic_response_remains_unknown(self):
        with LocalFixture(disclose_reason=False) as srv:
            r=probe(srv.url,origin='https://bad.invalid',trusted_fixture=True)
            self.assertEqual(r['status'],403)
            self.assertEqual(r['diagnostic']['reason'],'unknown')

    def test_untrusted_default_will_not_accept_wire_reason(self):
        with LocalFixture() as srv:
            r=probe(srv.url,origin='https://bad.invalid')
            self.assertTrue(r['wire_header_present'])
            self.assertEqual(r['diagnostic']['reason'],'unknown')

    def test_header_not_trusted_on_external_response(self):
        r=diagnose(401,{'X-Fixture-Rejection':'authorization'},trusted_fixture=False)
        self.assertEqual(r['reason'],'unknown')

    def test_bad_reason_not_sanitized_into_known(self):
        r=diagnose(403,{'X-Fixture-Rejection':'internal-secret-hostname'},trusted_fixture=True)
        self.assertEqual(r['reason'],'unknown')

    def test_no_origin_header_leak(self):
        with LocalFixture() as srv:
            r=probe(srv.url,origin='secret-sensitive-origin')
            self.assertNotIn('secret-sensitive-origin',repr(r))

    def test_no_auth_token_echoed(self):
        with LocalFixture() as srv:
            r=probe(srv.url,bearer='synthetic-secret')
            self.assertNotIn('synthetic-secret',repr(r))

    def test_redirects_refused_by_implementation(self):
        with self.assertRaises(ProbeError):
            _NoRedirect().redirect_request(None,None,302,'Found',{},'http://example.com')

    def test_nonloopback_target_forbidden(self):
        for url in ('https://github.com/mcp','http://example.com/mcp','http://localhost:123/mcp',
                    'http://127.0.0.1:80/admin','http://user:pass@127.0.0.1:80/mcp'):
            with self.assertRaises(ProbeError):probe(url)

    def test_probe_uses_real_http_wire(self):
        with LocalFixture() as srv:
            r=probe(srv.url,host_override='not-expected',trusted_fixture=True)
            self.assertTrue(r['wire_header_present'])

    def test_unknown_not_equivalent_to_auth_failure(self):
        result=diagnose(403,{})
        self.assertEqual(result['reason'],'unknown')

    def test_normal_401_no_header_cannot_identify_auth(self):
        self.assertEqual(diagnose(401,{},trusted_fixture=True)['reason'],'unknown')

    def test_wrong_status_cannot_claim_fixture_reason(self):
        self.assertEqual(diagnose(200,{'X-Fixture-Rejection':'host'},True)['reason'],'unknown')


if __name__=='__main__':unittest.main()
