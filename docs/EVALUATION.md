# Evaluation and reproduction

The public job is reproducible native initialize/middleware transport fidelity,
not a diagnostic standard or full MCP conformance. The simplest comparison is
the same case sent directly to the native SDK and through the actual local proxy.
Check status, exact bytes and both safe headers, including their absence.

## Frozen experiment

Definition SHA-256:
`e9e7811a19276af102b78197ee4ba3a69eec8d5569459690ccf93a487eb49d7f`.
Two SDKs x three compositions x 14 cases x two routes = 168 POST requests,
84 direct/proxy pairs and 24 initialize controls. Cases cover all eight
Host/Origin/auth validity masks, absent Origin, null Origin, missing auth,
malformed JSON, unsupported Accept and invalid Content-Type. The controls use
backward-compatible protocol version `2025-11-25`.

Locks preserve Python `mcp==2.3.0`, TypeScript server 2.3.1, Express adapter 2.0.2,
Node adapter 2.0.0 and Express 5.1.0, including resolved dependencies. Use Python
3.13.15, Node 24.15.0, npm 12.0.0 and uv 0.13.1. SDK installation is optional to
the offline wheel but mandatory for the native release gate. Never substitute a
green core suite for a native run.

## Observations and retained negative results

The native reproduction exposed a Python custom-composition
lifespan setup failure (500 positive controls), then 114 failing native proxy
subtests. Native initialize responses became 406 when the proxy dropped Accept;
it also changed media types, fabricated absent Content-Type and lost challenges.
The proxy regressions cover these cases against the unchanged matrix;
no case or guard policy is omitted from the native gate.

Observed all-invalid responses from that pinned reproduction:

| Configuration | Python status | TypeScript status |
| --- | --- | --- |
| Native localhost factory | 401 | 403 |
| Hand-composed auth first | 401 | 401 |
| Hand-composed security first | 421 | 403 |

These are observations of configurations, not causal diagnoses inferred from
arbitrary 401/403 bodies. All native classifier outputs remain `unknown`.
One rejection does not establish that the other guards would accept.

The release repair separately reproduced the fixture's missing body-read timeout,
truncated bodies returning 200 and ambiguous body framing. The focused regressions
failed before the repair. They now exercise timeout, truncation, framing limits
and unchanged guard order. Offline verifier regressions cover incomplete/duplicate
rows, changed definitions, corrupt base64/hash/headers, invented diagnoses,
malformed/oversized JSON, preserved failures and structured CLI errors.

## Reproduce

Run `sh scripts/verify-release.sh` for source, sdist and installed-wheel checks.
It retains `.release-scratch/verify.*/package-receipt.json`, including package file
names and SHA-256s. The wheel is rebuilt from extracted sdist and imported from
its isolated environment outside the checkout. Its authored synthetic record
only tests the offline CLI; it is not native runtime evidence.

Run `scripts/verify-native.sh` as in README for the separately pinned native gate.
Seven assertion groups exercise all 168 responses with no skip path. The offline
summary adds structural/hash checks and reports exact counts. For installed-wheel
native reproduction, invoke the extracted source's `tests/sdk/gate.py` with the
wheel interpreter, pass the locked SDK interpreter and Node executable as server
arguments, and omit source PYTHONPATH. The gate's server scripts come from that
matching extracted source, not the installed package.

CI runs core/package checks on Python 3.11, 3.12 and 3.13 and a separate pinned
native job on Python 3.13.15/Node 24.15.0. Record the exact revision and execution
environment for every reported result. Raw SDK errors can contain local paths
or server text; inspect them before sharing. A configured workflow is not a
passing hosted result, and authored records do not replace native execution.

## Practical local-session qualification

The 0.2.0 addition checks an explicitly supplied local endpoint, including operations after initialize. The independent HTTP fixtures exercise valid JSON and SSE, stateful header propagation, readiness, ping, paginated tools, unsupported capabilities and termination. Negative controls include a successful HTTP status with an invalid RPC envelope, operation failure after successful initialize, repeated discovery cursors, wrong versions, malformed tool schemas, redirects, private-text omission and slow/trickling response deadlines.

The 0.3.0 tests add owned HTTP services that wait for server-ping replies before continuing the original request, close primed SSE streams and require Last-Event-ID GET resumption, and mix healthy, broken and stalled endpoints. Negative controls reject unsupported server requests, duplicate IDs, ping floods, reconnect floods, wrong response IDs, missing resumption IDs and retry delays beyond the deadline. Counts and observed HTTP calls verify that original operation POSTs are not repeated. Offline comparison tests altered report text/IDs, old report compatibility, typed-field changes and malformed inputs. These are authored service scenarios and software checks, not independent protocol certification or unfamiliar-human evidence.

`scripts/verify_session.py --python SDK_PYTHON --output NEW.json` separately starts two owned native Python MCP 2.3.0 stateful servers and checks JSON/SSE sessions. It terminates every child. It requires the existing locked optional SDK environment; it fetches nothing itself. The optional native gate runs both this check and the unchanged 168-request middleware/proxy matrix. These are software qualification cases, not an unfamiliar-human study, remote-service result or evidence of causal diagnostic superiority. A one-request status check is a useful simpler baseline but does not exercise the session or subsequent operation; a hand-written client implementing the same checks can be equally informative.

The 0.4.0 authored catalogue regressions check same-count name/input/output/metadata drift, stable object-key/tool order and page partition, empty catalogues, missing capability, duplicate names, partial discovery, legacy reports and malformed fingerprints. These are software regressions. The previously retained same-count comparison blind spot remains historical negative evidence; it is not rewritten by the new report format. A competent native SDK client can independently compare complete private catalogues and inspect actual differences. A content-omitting saved comparison is the bounded product benefit, not superiority over that client or evidence of human time savings.
