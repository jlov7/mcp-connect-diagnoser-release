# Limitations

The implemented job is controlled loopback native initialize/middleware response
reproduction and offline fidelity verification. It does not identify the
rejecting layer of arbitrary servers. All native diagnoses are `unknown`.
A verified record can be authored or altered consistently, so hashes prove
internal integrity, not producer identity, provenance authenticity or independent
replication. The verifier only accepts the exact frozen definition, not arbitrary
SDK versions, server addresses or experiment shapes.

The teaching HTTP fixture's explicit rejection header is fixture-only and not an
official MCP extension. Factory and hand-composed orders are separate conditions.
A passing response-pair comparison can preserve a native rejection or server bug;
it does not establish security or protocol correctness of the upstream SDK.

The native gate uses synthetic in-memory credentials and stateless initialize
requests. Separate bounded local JSON/SSE session checks are described below.
The following qualifications are **NOT RUN**: browser/CORS behavior,
OAuth discovery/authorization flows, real
credentials, external servers, deployed proxies, production hardening, user
studies, independent scientific validation and empirical superiority.

These small threaded servers bind only loopback and are not production services.
Read timeouts bound socket inactivity, not the total lifetime of a continuously
trickling client. The CLI reads at most 2 MiB and captures at most 8192 body bytes
per row; response headers outside the documented safe allowlist are not compared.
Only Python 3.11 through 3.13 are covered by the core CI configuration; SDK runtime
coverage is Python 3.13.15 and Node 24.15.0. A configured CI job is not evidence of
an observed exact-head remote run.

## Practical probe limits

The endpoint probe is for local Streamable HTTP development. HTTPS/remote endpoints, localhost names, credentials, OAuth, stdio and legacy transports are outside its input contract. It lists at most 256 tools over four pages, does not call tools, and checks only the object schema envelope. Raw server instructions/names/body text are omitted rather than interpreted. All failure causes remain unknown unless supported by separate trusted logs. Termination is best effort under the same absolute deadline and has a separate reported outcome. A passed initialize/ping/list check is useful connection evidence, not general MCP conformance or production certification.

Server-request support is limited to eight pings. SSE resumption is limited to two GET reconnects under the original deadline and requires a nonempty event ID of at most 1024 UTF-8 bytes. The tool refuses ASCII controls, DEL and leading/trailing ASCII spaces in resumable IDs. Session IDs retain a separate visible-ASCII restriction. Long retry delays can exhaust the deadline. Other server requests, missing/repeated IDs and wrong response IDs fail explicitly. Original operation POSTs are never repeated. These bounded cases are not general subscription or reconnect reliability qualification.

Endpoint sets accept at most 16 explicit local URLs, four concurrent checks and a 30-second total budget. Caller-supplied labels appear in reports, so use non-sensitive names. Offline comparison accepts only this tool's supported probe/set formats. Arbitrary logs, HARs, native frozen records and free text are unsupported by compare. Reports are unsigned and can be authored consistently; comparison does not establish authenticity or causation.

The 0.4.0 catalogue fingerprint detects advertised metadata differences after complete bounded discovery. It does not identify which private field changed, validate full JSON Schema, inspect tool bodies or infer compatibility. Arrays remain order-sensitive, including metadata arrays. Equivalent key/tool ordering and page partition normalize; different numeric JSON representations may not. Missing capability, old reports and partial discovery yield unavailable catalogue status. Unsalted hashes may be guessed and are not a confidentiality or authenticity mechanism. No remote schema references, instructions or tool bodies are fetched or executed.
