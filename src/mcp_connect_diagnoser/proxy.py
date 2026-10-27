"""A bounded loopback reverse proxy for controlled diagnostic-loss experiments.

Not a public forward proxy, production gateway, or MCP SDK implementation.
"""
from __future__ import annotations

import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

from .core import ProbeError, _LoopbackHTTPServer


class LoopbackProxy:
    def __init__(self, target: str, *, strip_reason: bool = False):
        try:
            parsed = urlsplit(target)
            valid = (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
                     and parsed.port and parsed.path == '/mcp' and not parsed.query
                     and not parsed.fragment and not parsed.username and not parsed.password)
        except ValueError as exc:
            raise ProbeError('invalid loopback target') from exc
        if not valid or type(strip_reason) is not bool:
            raise ProbeError('only an explicit http://127.0.0.1:port/mcp target is allowed')
        self.target_port = parsed.port
        self.strip_reason = strip_reason
        self.forwarded = 0
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(2)

            def send_bounded(self, status, body, reason=None, *, native_headers=None):
                self.send_response(status)
                if native_headers is None:
                    self.send_header('Content-Type', 'application/json')
                else:
                    for name, value in native_headers.items():
                        self.send_header(name, value)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Connection', 'close')
                self.send_header('Content-Length', str(len(body)))
                if reason is not None:
                    self.send_header('X-Fixture-Rejection', reason)
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True

            def do_POST(self):
                # Refuse absolute URIs, framing ambiguity and credential ambiguity.
                invalid = self.path != '/mcp' or self.headers.get('Transfer-Encoding') is not None
                for name in ['Host', 'Origin', 'Authorization', 'Content-Length', 'Content-Type', 'Accept']:
                    invalid |= len(self.headers.get_all(name, [])) > 1
                for name in ['Content-Type', 'Accept']:
                    value = self.headers.get(name, '')
                    invalid |= len(value) > 1024 or any(ord(char) < 32 or ord(char) > 126 for char in value)
                length = self.headers.get('Content-Length', '0')
                invalid |= not length.isascii() or not length.isdigit()
                if invalid or len(length) > 5 or int(length) > 4096:
                    return self.send_bounded(400, b'{"status":"invalid_request"}')
                try:
                    body = self.rfile.read(int(length))
                    if len(body) != int(length):
                        return self.send_bounded(400, b'{"status":"truncated_request"}')
                except (TimeoutError, OSError):
                    return self.send_bounded(408, b'{"status":"request_timeout"}')
                incoming_host = self.headers.get('Host', '')
                forwarded_host = (f'127.0.0.1:{owner.target_port}'
                                  if incoming_host == f'127.0.0.1:{owner.port}'
                                  else incoming_host)
                headers = {'Host': forwarded_host}
                for name in ['Origin', 'Authorization', 'Content-Type', 'Accept']:
                    if self.headers.get(name) is not None:
                        headers[name] = self.headers[name]
                conn = http.client.HTTPConnection('127.0.0.1', owner.target_port, timeout=2)
                try:
                    with owner._lock:
                        owner.forwarded += 1
                    conn.request('POST', '/mcp', body=body, headers=headers)
                    response = conn.getresponse()
                    data = response.read(8193)
                    if len(data) > 8192:
                        return self.send_bounded(502, b'{"status":"upstream_too_large"}')
                    native_headers = {}
                    for name in ['Content-Type', 'WWW-Authenticate']:
                        values = response.headers.get_all(name, [])
                        if len(values) > 1 or any(len(value) > 1024 or any(
                                ord(char) < 32 or ord(char) > 126 for char in value) for value in values):
                            return self.send_bounded(502, b'{"status":"invalid_upstream_header"}')
                        if values:
                            native_headers[name] = values[0]
                    reasons = response.headers.get_all('X-Fixture-Rejection', [])
                    reason = reasons[0] if len(reasons) == 1 and not owner.strip_reason else None
                    # Never relay arbitrary upstream diagnostic text or internal details.
                    if reason not in {'host', 'origin', 'authorization'}:
                        reason = None
                    return self.send_bounded(response.status, data, reason, native_headers=native_headers)
                except (OSError, http.client.HTTPException):
                    return self.send_bounded(502, b'{"status":"upstream_unavailable"}')
                finally:
                    conn.close()

            def log_message(self, *_):
                pass  # Never record Authorization or caller-supplied header values.

        self.server = _LoopbackHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def port(self):
        return self.server.server_port

    @property
    def url(self):
        return f'http://127.0.0.1:{self.port}/mcp'

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def run_matrix() -> dict:
    from .core import LocalFixture, probe
    rows = []
    with (LocalFixture() as target, LoopbackProxy(target.url) as forward,
          LoopbackProxy(target.url, strip_reason=True) as strip):
        for route, endpoint in [('direct', target.url), ('forward', forward.url), ('stripped', strip.url)]:
            for mask in range(8):
                result = probe(endpoint, host_override='bad.invalid' if mask & 1 else None,
                               origin='wrong' if mask & 2 else 'http://localhost:7000',
                               bearer='wrong' if mask & 4 else 'synthetic-fixture-token',
                               trusted_fixture=True)
                rows.append({'route': route, 'host_invalid': bool(mask & 1),
                             'origin_invalid': bool(mask & 2), 'bearer_invalid': bool(mask & 4),
                             **result})
    return {'scope': 'Controlled HTTP fixtures and actual proxy; not MCP SDK conformance.', 'rows': rows}


if __name__ == '__main__':
    print(json.dumps(run_matrix(), indent=2))
