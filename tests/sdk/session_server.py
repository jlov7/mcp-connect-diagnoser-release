"""Owned local stateful SDK fixture, separate from the frozen guard matrix."""
import logging
import socket
import sys

import uvicorn
from mcp.server import MCPServer


def main():
    if sys.argv[1:] not in [['json'], ['sse']]:
        raise SystemExit('expected json or sse')
    logging.disable(logging.CRITICAL)
    server = MCPServer('local-session-check', version='1.0.0')

    @server.tool()
    def echo(value: str) -> str:
        """An advertised tool. The connection check must never invoke it."""
        raise AssertionError('the probe must not call tools')

    app = server.streamable_http_app(json_response=sys.argv[1] == 'json',
                                      stateless_http=False, session_idle_timeout=10)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(16)
        print(listener.getsockname()[1], flush=True)
        uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False,
                                      timeout_keep_alive=1)).run(sockets=[listener])


if __name__ == '__main__':
    main()
