"""Owned metadata fixture using the pinned SDK's public typed handler API."""
import json
import logging
import socket
import sys

import uvicorn
from mcp import types
from mcp.server import Server
from mcp.shared.message import ServerMessageMetadata
from pydantic import ValidationError

MARKER = 'NATIVE-METADATA-DO-NOT-ECHO'
MODES = ('response-json', 'response-sse', 'request-string', 'request-integer', 'fraction-construction')


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        raise SystemExit('expected one declared fixture mode')
    logging.disable(logging.CRITICAL)
    mode = sys.argv[1]
    if mode == 'fraction-construction':
        try:
            types.PingRequest(params=types.RequestParams(
                _meta=types.RequestParamsMeta(progressToken=0.5, private=MARKER)))
        except ValidationError as error:
            print(json.dumps({'outcome': 'unsupported_by_pinned_sdk',
                              'wire_request_emitted': False,
                              'error_types': [row['type'] for row in error.errors(include_input=False)]}))
            return
        raise AssertionError('the locked SDK constructor accepted a fractional progress token')

    async def ping(ctx, params):
        if mode.startswith('request-'):
            token = {'request-string': 'opaque-progress', 'request-integer': 7}[mode]
            request = types.PingRequest(params=types.RequestParams(
                _meta=types.RequestParamsMeta(progressToken=token, private=MARKER)))
            await ctx.session.send_request(
                request, types.EmptyResult, request_read_timeout_seconds=2,
                metadata=ServerMessageMetadata(related_request_id=ctx.request_id))
        return types.EmptyResult(_meta={'private': MARKER})

    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=[types.Tool(
            name='never-call', description='Advertised only.', inputSchema={'type': 'object'})])

    async def call_tool(ctx, params):
        raise AssertionError('a session probe must not call a tool')

    server = Server('native-ping-metadata', version='1', on_ping=ping,
                    on_list_tools=list_tools, on_call_tool=call_tool)
    app = server.streamable_http_app(json_response=mode == 'response-json',
                                     stateless_http=False, session_idle_timeout=10)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(16)
        print(listener.getsockname()[1], flush=True)
        uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False,
                                      timeout_keep_alive=1)).run(sockets=[listener])


if __name__ == '__main__':
    main()
