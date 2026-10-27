"""Synthetic local server using the pinned SDK's native guards and authentication."""
import logging
import socket
import sys

import uvicorn
from mcp.server import MCPServer
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request

TOKEN = 'synthetic-sdk-token'
RESOURCE = 'http://127.0.0.1/mcp'


class Verifier:
    async def verify_token(self, token):
        if token == TOKEN:
            return AccessToken(token=token, client_id='synthetic', scopes=['mcp'], resource=RESOURCE)
        return None


class Guard:
    def __init__(self, app):
        self.app = app
        self.guard = TransportSecurityMiddleware(TransportSecuritySettings(
            allowed_hosts=['127.0.0.1:*', 'localhost:*', '[::1]:*'],
            allowed_origins=['http://127.0.0.1:*', 'http://localhost:*', 'http://[::1]:*']))

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            response = await self.guard.validate_request(Request(scope), is_post=True)
            if response is not None:
                return await response(scope, receive, send)
        await self.app(scope, receive, send)


class HttpAuth:
    def __init__(self, app):
        self.app = app
        self.http = AuthenticationMiddleware(RequireAuthMiddleware(
            app, ['mcp'], AnyHttpUrl('http://127.0.0.1/.well-known/oauth-protected-resource/mcp')),
            backend=BearerAuthBackend(Verifier(), resource_server_url=AnyHttpUrl(RESOURCE)))

    async def __call__(self, scope, receive, send):
        target = self.http if scope['type'] == 'http' else self.app
        await target(scope, receive, send)


def make_app(mode):
    if mode == 'factory':
        server = MCPServer('sdk-repro', version='1.0.0', token_verifier=Verifier(), auth=AuthSettings(
            issuer_url='http://127.0.0.1', resource_server_url=RESOURCE,
            validate_token_resource=True, required_scopes=['mcp']))
        return server.streamable_http_app(json_response=True, stateless_http=True)
    server = MCPServer('sdk-repro', version='1.0.0')
    transport = server.streamable_http_app(json_response=True, stateless_http=True)

    # Both compositions retain native transport checks; neither is a claimed SDK default.
    return HttpAuth(Guard(transport)) if mode == 'auth-first' else Guard(HttpAuth(transport))


if __name__ == '__main__':
    if sys.argv[1] not in {'factory', 'auth-first', 'security-first'}:
        raise SystemExit('unknown composition')
    logging.disable(logging.CRITICAL)  # Native validation logs can echo request header values.
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    # The parent owns deadlines and tears down this process after its bounded matrix.
    print(sock.getsockname()[1], flush=True)
    uvicorn.Server(uvicorn.Config(make_app(sys.argv[1]), log_config=None, access_log=False,
                                  timeout_keep_alive=1)).run(sockets=[sock])
