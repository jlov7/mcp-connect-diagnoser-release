# Pinned SDK compatibility

The optional native gate uses Python 3.13.15, `mcp==2.3.0`, Node 24.15.0, npm 12.0.0 and the committed Python and TypeScript dependency locks. These are reproduction inputs, not support for arbitrary SDK releases.

The TypeScript lock resolves the transitive `body-parser` dependency to 2.4.0, the maintainer-patched version for [GHSA-27r3-jxmh-p828 / CVE-2026-111181](https://github.com/expressjs/body-parser/security/advisories/GHSA-27r3-jxmh-p828). The advisory affects versions from 2.0.0 through releases before 2.4.0. This defensive dependency update preserves the direct SDK pins, native fixture source and frozen traffic expectations. The existing gates check ordinary compatibility; dedicated exploitation validation is **NOT RUN**. The product runtime has no dependencies.

Run the [README native commands](../README.md#verify-and-reproduce). The gate writes three separate reports. A passing invocation establishes the conditions below for that run. Workflow configuration alone does not establish a pass.

| Check | Native construction path | Required outcome |
| --- | --- | --- |
| Frozen middleware/proxy characterization | Locked Python and TypeScript SDK fixtures | All 168 frozen request expectations and native-response fidelity checks pass |
| Stateful session discovery | Python SDK JSON and SSE servers | Both sessions initialize, ping, discover tools and terminate without calling a tool |
| Metadata on ping results | Python SDK `Server(on_ping=...)`, `EmptyResult(_meta=...)`, JSON and SSE | Both sessions complete; private metadata is absent from reduced reports |
| Metadata on server pings | Python SDK typed `PingRequest`, string and integer progress tokens | Both sessions answer one server ping, discover one advertised tool and terminate |
| Fractional progress token | Python SDK typed `RequestParams` construction | SDK rejects `0.5` with `string_type` and `int_from_float`; no request is emitted |

The last row is an SDK limitation, not a successful wire exchange. The supported MCP schemas allow a string or number progress token. This pinned Python SDK's typed constructor accepts a string or integer. The diagnoser's separate [authored wire tests](../tests/test_ping_metadata.py) cover finite fractional tokens across all three supported protocol versions. Do not infer fractional-token native interoperability from those tests.

[`verify_ping_metadata.py`](../scripts/verify_ping_metadata.py) records four actual sessions and the constructor boundary. Its servers bind ephemeral literal loopback ports, use the SDK's public typed API and close after each case. It neither modifies SDK source nor rewrites native responses. The private marker is synthetic; the gate requires it to be absent from product reports.

These observations do not establish full MCP conformance, remote or authenticated interoperability, other transports, semantic tool compatibility or production security. No tool body is invoked. Unlisted SDK versions and native combinations are **NOT RUN**.

Primary protocol references: [2025-11-25 schema](https://modelcontextprotocol.io/specification/2025-11-25/schema), [2025-06-18 schema](https://modelcontextprotocol.io/specification/2025-06-18/schema), [2025-03-26 archived schema](https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/schema/2025-03-26/schema.ts).
