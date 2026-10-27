# References and provenance

The implementation is original project code under MIT. Optional SDK packages
and their transitive dependencies are installed from `tests/sdk/uv.lock` and
`tests/sdk/package-lock.json`; their own licenses remain applicable. No SDK
installation, third-party source tree, production trace or downloaded corpus is
vendored into the source archive or wheel. Tests use authored synthetic data.

- [MCP issue #3370](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3370):
  motivating failure report/discussion, not an adopted standard. Its deployment
  or SDK-population statements are not measurements by this project.
- [Python MCP SDK 2.3.0](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.3.0):
  pinned native implementation used in the reproduction.
- [Python transport security](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/transport_security.py)
  and [bearer middleware](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/auth/middleware/bearer_auth.py).
- [TypeScript MCP SDK 2.3.1](https://github.com/modelcontextprotocol/typescript-sdk/releases/tag/v2.3.1):
  native server and separately versioned adapters are fixed by the npm lock.
- [MCP transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
  and [authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization):
  references for the broader protocol. The reproduction's backward-compatible
  `2025-11-25` initialize flow does not qualify the full current-era flow.
- [Supported 2025-11-25 resumption](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#resumability-and-redelivery)
  and [SSE event-ID encoding](https://html.spec.whatwg.org/multipage/server-sent-events.html#the-last-event-id-header):
  sources for the bounded UTF-8 cursor correction. This probe does not claim a full EventSource implementation.
- [JSON-RPC error object](https://www.jsonrpc.org/specification#error_object):
  standard server-reported error categories. Their presence does not establish an underlying cause.

Pinned source links identify the implementation being exercised. They do not
turn native error text into a portable causal classifier or demonstrate an
upstream endorsement, certification or independent reproduction.
