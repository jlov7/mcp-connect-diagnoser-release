# Usage

Version 1.0's supported interfaces and compatibility policy are defined in
[stability](STABILITY.md). Run `.venv/bin/mcp-connect-diagnoser --version` without
a target to identify the installed version. The supplied [quickstart](../examples/quickstart.py)
checks an owned loopback fixture without an existing service.

Use the README commands to generate a fresh native record from the source
archive after its `.venv` installation, without activating the environment.
The SDK harness requires its matching `tests/sdk` scripts and locks.
The offline native-record command is:

```sh
.venv/bin/mcp-connect-diagnoser summarize native.json
.venv/bin/python -m mcp_connect_diagnoser summarize native.json
```

Exit 0 means the supplied record is structurally complete and all frozen positive
controls and direct/proxy fidelity checks passed. Exit 1 retains a valid complete
record's observed differences or failed controls. Exit 2 means invalid input or
usage, with JSON on stderr: `requestID`, `error.code`, `error.message` and
`error.next_step`. No raw body, path contents or supplied header value is echoed
in errors. Success summaries contain a request ID too; it is intentionally
nondeterministic and not part of the frozen experiment hash.

Records must be regular UTF-8 JSON files, at most 2 MiB, with unique object keys.
FIFOs, directories and device files are refused without waiting for a writer. Exactly 168 unique
rows must match the frozen SDK/composition/route/case census. Bodies are canonical
base64, at most 8192 bytes, with matching SHA-256. Only `content-type` and
`www-authenticate` response headers are allowed, each absent or one printable
ASCII value of at most 1024 characters. Every stored native diagnosis must equal
the conservative unknown result. Headers are compared with absence preserved.

The verifier checks integrity and consistency, not authenticity. It can validate
an authored synthetic record, so successful verification alone is not runtime or
independent evidence. The package check labels its authored CLI smoke as such.
Treat records from other people as untrusted data. The tool never starts a server
while summarizing them and never executes a command or code from them.

The native runner writes a record exclusively, then preserves partial rows with
`complete: false` on failure. Do not reuse the output filename. Partial records
are retained evidence but intentionally rejected by the strict summary. Source
native gate logs may include synthetic SDK error text and local stack paths;
review before sharing them.

## Inspect a rejection

`verified: true` means the controls and proxy comparisons passed. The matrix
deliberately includes rejected requests, so a matching 401, 403 or 406 can appear
in a verified record. `unknown` is the native classifier's limit, not a failed
comparison. Use trusted server logs to investigate a real server's rejecting
layer.

After summarizing your record, inspect one frozen case offline from the source
directory. This example prints both routes' status, safe headers and decoded
body for the Python factory's unsupported Accept case. JSON escaping keeps body
text separate from terminal control characters:

```sh
.venv/bin/python - .release-scratch/native.json <<'PY'
import base64
import json
import sys

with open(sys.argv[1], encoding='utf-8') as stream:
    record = json.load(stream)
for row in record['rows']:
    if (row['sdk'], row['composition'], row['case']) == (
            'python', 'factory', 'unsupported-accept'):
        print(json.dumps({
            'route': row['route'], 'status': row['status'],
            'headers': row['headers'], 'diagnostic': row['diagnostic'],
            'body': base64.b64decode(row['body_base64']).decode('utf-8', errors='replace'),
        }))
PY
```

The pinned experiment sends `Accept: text/plain` in this case and observes 406
on both routes. Its positive controls use `Accept: application/json,
text/event-stream` and observe 200. This gives a concrete negotiation check for
this fixture; the classifier still cannot infer an arbitrary server's cause.

## Recover a rejected record

For exit 1, inspect `differences` and `positive_controls.failures` in stdout.
They identify the configuration and case to inspect above. Preserve the record
and investigate the native/proxy observations before changing anything.

For exit 2, read `error.message` on stderr. A body hash mismatch identifies its
zero-based row. Malformed JSON or `complete: false` means the strict summary
cannot verify the record. Preserve the rejected file and its SDK logs, then
rerun the README native command with a fresh output name, for example
`NATIVE_OUTPUT="$PWD/.release-scratch/native-retry-1.json"`. Summarize that new
path. Reusing a path is refused; do not edit hashes, remove rows or mark a
partial record complete to obtain a pass.

For the teaching fixture only:

```sh
.venv/bin/python -m mcp_connect_diagnoser.demo
.venv/bin/python -m mcp_connect_diagnoser.proxy
```

Fixture reasons are trusted only with explicit fixture trust and a matching
status/header pair. The three-route teaching matrix has 24 requests and is
separate from the 168-request native SDK matrix.

## Local connection check

Use the installed command `.venv/bin/mcp-connect-diagnoser probe http://127.0.0.1:PORT/path`, optionally with `--timeout 1..30` and `--output NEW.json`. IPv6 uses `http://[::1]:PORT/path`. There is no default listener. The URL must name a service you deliberately want to check. The probe accepts no credentials, follows no redirects, bypasses environment proxies and performs no DNS lookup. It accepts only plain HTTP literal loopback targets, with no query, user information or fragment.

The Python API is `from mcp_connect_diagnoser.session_probe import probe_session, SessionInputError`. Call `probe_session(url, timeout=10)`. Invalid inputs raise SessionInputError; network/protocol observations return a report with verified, stages and failure/next_step when applicable. It never executes a tool. Initialize, initialized notification, ping and advertised tools/list are checked in sequence; bounded pagination carries the session and negotiated protocol headers. A returned session gets best-effort DELETE within the same absolute deadline. Cleanup has its own outcome and does not change which connection stages passed. Reports contain counts and constant advice, never raw server text, names, session values or cursor values.

JSON and SSE responses are supported. Duplicate JSON keys, non-finite numbers, mismatched IDs, invalid initialization envelopes, repeated cursors and malformed object tool-schema envelopes fail. The 256-tool/four-page/64-message/256-KiB bounds deliberately reject larger catalogs. Default deadline is 10 seconds; explicit values are integer 1..30 seconds. The session check is not a full JSON Schema or protocol-conformance validator. `summarize` remains exclusively for the frozen native experiment record.

### Server ping and SSE resumption (0.3.0)

A server ping before the original response gets an empty JSON-RPC result by a separate POST. The original request continues waiting. At most eight pings are answered across the probe. IDs must be bounded strings or safe integers, unique within the server-request direction. No sampling, elicitation or tool operation is dispatched. A response POST requires HTTP 202 with an empty body. Before initialize returns, the requested protocol version is used for these transport requests; afterward the negotiated version is used. The session header is captured before reading initialize's body.

A closed SSE stream can resume by GET to the identical endpoint, carrying Accept: text/event-stream, session/protocol headers and Last-Event-ID. Operation POSTs are never repeated. Retry delays are honored inside the absolute deadline. At most two GET reconnects are attempted across the probe. Explicit event IDs must be unique within the session and at most 1024 characters. Resumption additionally requires a nonempty ID of at most 1024 UTF-8 bytes, without ASCII controls, DEL or leading/trailing ASCII spaces. A completed response does not need to fit a resume header. UTF-8 bytes are preserved in that header; session IDs remain separately restricted to visible ASCII. Missing IDs, replayed IDs, wrong response IDs and exhausted limits fail explicitly. A logical request retains its 64-event limit across reconnects; each physical response has a 256 KiB bound. Invalid UTF-8 or Content-Length framing fails rather than being repaired by reconnecting.

Reports use schema_version: 3 and report_type: mcp-session-probe, with server_pings_answered and reconnect_attempts counts. IDs, cursor values and response bodies remain in memory only.

For standard JSON-RPC error codes -32700, -32600, -32601, -32602 and -32603, `failure.next_step` names the server-reported category and suggests a corresponding check. `failure.code` remains `rpc_error` and `failure.cause` remains `unknown`. Custom codes receive generic advice. Server messages, error data and cursor values are omitted. Advice wording is not a stable comparison field.

### Complete catalogue fingerprint (0.4.0)

catalogue_sha256 is a lowercase 64-character SHA-256 digest, or null when unavailable. It covers the complete advertised tools array only after all pages pass validation and a terminal page is received. Duplicate names fail across pages. No tools capability, failed or partial discovery leaves null; an advertised empty catalogue has a digest. The existing four-page/256-tool/256-KiB-per-response/deadline bounds still apply. Retained catalogue memory is bounded by those page/body limits. Names, schemas, metadata and instructions are never copied into reports or dereferenced.

The canonical bytes are UTF-8 JSON of tools sorted by unique name, with object keys recursively sorted, no whitespace, ensure_ascii=False and allow_nan=False. All advertised tool fields participate, including inputSchema, outputSchema and metadata. Page envelopes, pagination cursors and initialize instructions do not. Tool order, object-key order and page partition have no effect; arrays retain their order. This is observed metadata equality, not a semantic JSON Schema equivalence test. Numeric representations such as 1 and 1.0 can differ. Hashes are unsigned and guessable, with no confidentiality, authenticity, conformance or tool-body correctness guarantee.

### Explicit local endpoint sets

`.venv/bin/mcp-connect-diagnoser probe-many TARGETS.json --timeout 5 --max-seconds 10 --output NEW.json` accepts a schema-version-1 object with exactly schema_version and targets. Each of 1..16 target objects has exactly label and url. Labels are unique, start with an ASCII letter/digit, and contain at most 48 ASCII letters, digits, periods, underscores or hyphens. Use non-sensitive labels. URL rules match probe. All targets and bounds are validated before network activity or output reservation.

At most four probes run concurrently. Each gets the smaller of its own timeout and remaining max-seconds budget, both integer 1..30 seconds. A queued target after the deadline is marked not_started_deadline with report:null. Results preserve input order and independent failures. The schema-version-1 mcp-endpoint-set report is complete only if all targets started, and verified only if all passed. It contains labels but no URLs. There is no endpoint discovery. The Python API is `reports.probe_many(inputs, timeout=10, max_seconds=30)`; validate_targets performs the same preflight without connections.

### Offline probe comparison

`.venv/bin/mcp-connect-diagnoser compare LEFT.json RIGHT.json --output NEW.json` reads regular strict-UTF-8 JSON files, at most 2 MiB each. It validates known report structure and compares only typed observations. It accepts original version-1 session reports, version-2/version-3 session reports and version-1 endpoint-set reports. The Python API is `reports.compare_reports(left, right)`. Request IDs, arbitrary text/extra fields, byte counts and timings are omitted. Original reports normalize new counters to zero. Endpoints match by safe labels regardless of row order.

The mcp-probe-comparison report has same_observations and changes with typed before/after values and known field paths. Absence differs from a present null. Malformed or unsupported reports refuse with exit 2. Exit 0 means comparison succeeded, including differing or failed connection observations. No network calls or source-file changes occur. Optional output paths must be new and are created with mode 0600; existing files and symlinks are refused. These unsigned records are consistency evidence, not authenticated provenance or causal diagnoses.

Catalogue comparison adds catalogue_comparisons: each entry has a field path and changed, unchanged or unavailable status. Only two complete fingerprints can be unchanged. Endpoint sets report each label separately, retaining unavailable entries when some endpoints have no fingerprint. Legacy version-1/version-2 reports have unknown catalogues even if extra fields claim a digest. same_observations still describes comparable operational fields when a catalogue is unavailable; read the catalogue status separately. Invalid version-3 digests or a digest inconsistent with incomplete discovery are refused.
