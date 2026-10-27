# Validation

Core source/package checks and the separately pinned native SDK gate answer
different questions. Run both as described in [README](../README.md) and
[the release procedure](RELEASING.md). [Evaluation](EVALUATION.md) preserves the
frozen native definition and its negative controls.

| Contract | Discriminating checks | Limit |
| --- | --- | --- |
| Saved catalogue comparisons detect same-count metadata changes | [Catalogue cases](../tests/test_catalogue.py) | Reduced hashes do not reveal differences or authenticate a producer |
| Complete Unicode streams retain the receive bound; resume headers use the UTF-8 byte bound | [Resume encoding](../tests/test_resume_encoding.py) | The bounded probe is not a full EventSource implementation |
| Supported ping metadata is accepted without disclosure | [Metadata cases](../tests/test_ping_metadata.py), [native metadata gate](../scripts/verify_ping_metadata.py) | Only the documented versions and metadata shape are covered |
| Original operation POSTs are not replayed during SSE resumption | [Session cases](../tests/test_session_probe.py) | Limited reconnects share the original deadline |
| Native direct/proxy fidelity is checked against frozen traffic | [SDK gate](../tests/sdk/gate.py) | SDK observations do not establish general MCP conformance |

The native gate exercises the unchanged 168-request matrix, two stateful sessions
and four metadata sessions using committed locks. The
[compatibility table](COMPATIBILITY.md) records supported combinations and the
Python SDK's fractional-progress-token boundary. Core tests do not substitute
for native execution. Remote services, authentication, tool execution, causal
middleware diagnosis and production qualification remain outside scope.
