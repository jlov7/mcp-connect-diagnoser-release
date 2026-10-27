# Design

`core.py` provides a synthetic HTTP fixture and conservative classifier.
`proxy.py` implements a bounded reverse proxy whose target must be literal
`http://127.0.0.1:port/mcp`. `sdk_repro.py` runs the frozen native SDK matrix.
`native_records.py` validates complete records and compares direct/proxy pairs
without sockets or subprocesses. `reports.py` compares allowlisted probe observations
offline and schedules explicit endpoint sets. `__main__.py` exposes these commands
and the local session probe.

The teaching fixture evaluates Host, then Origin, then bearer authentication.
Those guards precede body processing. Connections have a two-second socket
inactivity timeout; an incomplete body returns 408, EOF before Content-Length
returns 400, and duplicate Content-Length, Transfer-Encoding or bodies above
4096 bytes return 400. This is a bounded local teaching server, not a hardened
public listener or slow-client total-wall-clock admission service. Threaded
request handlers are daemon threads; this change does not claim a server-close
hang. Fixture diagnostics do not become native SDK claims.

The proxy forwards only relevant Host, Origin, Authorization, Accept and
Content-Type fields. A valid proxy Host maps to the target loopback port; an
invalid Host remains invalid. It relays exact bounded body bytes and only native
Content-Type and WWW-Authenticate response fields, preserving absence. The
fixture's separate recognized rejection field can be retained or stripped.
Duplicate/invalid permitted response headers yield 502; invalid framing or
negotiation request fields yield 400 before forwarding. Arbitrary upstream
headers are excluded. No Host/Origin/auth guard is disabled for a passing result.

Each native SDK has a localhost factory configuration, a hand-composed auth-first
configuration and a hand-composed security-first configuration. The latter two
are explicitly selected experiments, not claimed SDK defaults. Native transport
checks remain enabled. Token verification is synthetic, in memory, including
resource/audience validation. No authorization server is contacted.

SDK readiness has a ten-second announcement wait and five-second connection
wait; each request has a three-second timeout and an 8192-byte response bound.
The harness terminates and reaps server subprocesses in `finally`, with a kill
fallback. Loopback HTTP probes disable ambient proxy routing and redirects.
This bounded trusted harness is not an arbitrary-command or arbitrary-server
probe. Input records never select executable paths.

## User-endpoint session boundary

The session client uses http.client directly with validated 127.0.0.1/[::1] literals. It never delegates proxy selection, DNS, redirects or credential lookup. One absolute monotonic deadline includes connection, response reads and best-effort cleanup; a socket shutdown timer bounds trickling responses as well as idle reads. Requests are limited to initialize, notifications/initialized, ping, at most four tools/list pages, eight empty replies to server pings, two SSE-resumption GETs and DELETE. No tools/call, sampling, elicitation or arbitrary received instruction is executed. An unsupported server request fails the check.

Strict bounded JSON/SSE decoding yields protocol envelopes; response text and server-supplied strings are not copied to reports. Only a supported negotiated version is sent subsequently. A validated session ID remains in memory and is omitted from stdout/files. A successful stage set is distinct from cleanup outcome. Hashes in the older record verifier establish consistency, not authenticity. Frozen matrix definitions and unknown native causal labels are unchanged.

Resumption retains the original integer request ID, bounded event count, last complete event ID, session and retry delay. It changes only the physical request to GET. Duplicate event IDs and server-request IDs are refused. The session and requested protocol are available while awaiting initialize, permitting bounded server pings and resumption there too. Every reconnect and reply inherits the same deadline.

Endpoint sets are fully prevalidated before a four-worker executor starts. There is no persistent queue, discovery or background worker. Offline comparison projects validated reports onto known typed fields before comparing them, so supplied text, byte counts and timing cannot become comparison output. Report consistency does not establish authenticity.
