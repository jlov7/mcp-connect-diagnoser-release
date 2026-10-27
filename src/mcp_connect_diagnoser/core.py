"""Synthetic MCP transport boundary: only loopback fixture probing is supported."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

REASONS = {'host','origin','authorization'}


class _LoopbackHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        # These owned fixtures bind a literal IPv4 address; reverse DNS adds no information.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address


class ProbeError(ValueError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProbeError('refuse redirects while probing a sensitive boundary')


def diagnose(status:int, headers:dict[str,str], trusted_fixture:bool=False) -> dict[str,str]:
    """Unknown unless an explicitly trusted local fixture supplied its diagnostic."""
    values = [v for k, v in headers.items() if k.lower() == 'x-fixture-rejection']
    raw = values[0] if len(values) == 1 else None
    expected_status = {'host': 403, 'origin': 403, 'authorization': 401}
    if trusted_fixture and raw in REASONS and status == expected_status[raw]:
        tips={'host':'Inspect the target hostname and configured Host validation.',
              'origin':'Inspect the allowed browser origin without removing origin checks.',
              'authorization':'Check credentials and configured authorization without logging tokens.'}
        return {'reason':raw,'confidence':'CONTROLLED_FIXTURE_ONLY','next_step':tips[raw]}
    return {'reason':'unknown','confidence':'UNKNOWN','next_step':'Inspect trusted server-side logs; HTTP status alone does not identify the rejecting layer.'}


def make_handler(allowed_origin:str, fixture_bearer:str, disclose_reason:bool=True):
    """Only for a local synthetic fixture; do not deploy as a real MCP server."""
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(2)

        def _respond(self,status:int,reason:str|None=None):
            body=json.dumps({'status':'ok' if status==200 else 'rejected'},sort_keys=True).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)))
            if reason and disclose_reason:
                self.send_header('X-Fixture-Rejection',reason)
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path!='/mcp':
                return self._respond(404)
            allowed_host=f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host')!=allowed_host:
                return self._respond(403,'host')
            if self.headers.get('Origin')!=allowed_origin:
                return self._respond(403,'origin')
            if self.headers.get('Authorization')!=f'Bearer {fixture_bearer}':
                return self._respond(401,'authorization')
            size=self.headers.get('Content-Length','0')
            if (self.headers.get('Transfer-Encoding') is not None or
                    len(self.headers.get_all('Content-Length', [])) > 1 or
                    not size.isascii() or not size.isdigit() or len(size)>5 or int(size)>4096):
                return self._respond(400)
            try:
                body=self.rfile.read(int(size))
            except (TimeoutError, OSError):
                return self._respond(408)
            if len(body)!=int(size):
                return self._respond(400)
            return self._respond(200)

        def log_message(self, format, *args):
            # No Authorization/Origin/Host values are emitted to a logfile.
            pass
    return Handler


class LocalFixture:
    def __init__(self, disclose_reason:bool=True):
        self.server=_LoopbackHTTPServer(('127.0.0.1',0),
                make_handler('http://localhost:7000','synthetic-fixture-token',disclose_reason))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)

    @property
    def url(self):return f'http://127.0.0.1:{self.server.server_port}/mcp'

    def __enter__(self):
        self.thread.start();return self

    def __exit__(self, *args):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)


def probe(url:str, *, origin:str='http://localhost:7000',
          bearer:str='synthetic-fixture-token', host_override:str|None=None,
          trusted_fixture:bool=False) -> dict[str,Any]:
    """Wire probe to an explicitly loopback-only target; no redirects or real tokens."""
    parsed=urlsplit(url)
    if (parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port or
            parsed.username or parsed.password or parsed.path!='/mcp' or parsed.query or parsed.fragment):
        raise ProbeError('only http://127.0.0.1:port/mcp permitted')
    headers={'Content-Type':'application/json','Origin':origin,'Authorization':f'Bearer {bearer}'}
    if host_override is not None:
        headers['Host']=host_override
    req=Request(url,data=b'{}',headers=headers,method='POST')
    opener=build_opener(ProxyHandler({}), HTTPHandler, _NoRedirect)
    try:
        with opener.open(req,timeout=3) as response:
            return {'status':response.status,'diagnostic':diagnose(response.status,dict(response.headers),trusted_fixture),
                    'wire_header_present':response.headers.get('X-Fixture-Rejection') is not None}
    except HTTPError as e:
        e.close()  # Retain headers/status, release the response socket.
        # Even a 403 may come from any layer. Only fixture-local metadata names it.
        return {'status':e.code,'diagnostic':diagnose(e.code,dict(e.headers),trusted_fixture),
                'wire_header_present':e.headers.get('X-Fixture-Rejection') is not None}
