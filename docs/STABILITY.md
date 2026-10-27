# V1 stability and compatibility

Version 1.0.0 establishes the following bounded developer-tool contract. Version 1.0.1 fixes common ping-metadata compatibility within that contract. Version 1.0.2 corrects UTF-8 event-ID resumption and adds constant advice for standard server-reported RPC error categories. It does not certify MCP conformance, security, production fitness or human usefulness.

## CLI

The stable commands are `probe`, `probe-many`, `compare` and `summarize`. Their current required arguments and documented flags remain supported throughout 1.x. `--help` and `--version` work without a target. The console script and `python -m mcp_connect_diagnoser` use the same command name and version.

Exit 0 means checks passed, or valid reports were compared even if different. Exit 1 means an observed connection failure or native control/fidelity failure. Exit 2 means usage, input or output-file failure. JSON errors use `requestID` and `error.code`, `error.message`, `error.next_step` on stderr. Stable error codes are `invalid_record`, `invalid_input` and `output_failed`. Advisory wording, help layout, request IDs and stack locations are not machine contracts.

An output path must be new and is created mode 0600. Probe/set validation and output reservation precede connecting. Existing files and symlinks are refused. Partial output from a failed write is preserved; retries require a fresh name. Input JSON files must be regular files at most 2 MiB. Non-regular inputs, including FIFOs, are refused without waiting for a writer. Input symlinks may resolve to regular files.

## Python API

These public imports and signatures are supported throughout 1.x:

| Module | Supported functions/types |
| --- | --- |
| `mcp_connect_diagnoser.session_probe` | `probe_session(url, *, timeout=10)`, `SessionInputError` |
| `mcp_connect_diagnoser.reports` | `load_json(path)`, `validate_targets(inputs, *, timeout=10, max_seconds=30)`, `probe_many(inputs, *, timeout=10, max_seconds=30)`, `compare_reports(left, right)` |
| `mcp_connect_diagnoser.native_records` | `load_record(path)`, `summarize(record)`, `RecordError` |

Calls return ordinary Python dictionaries/lists in the documented report formats. `validate_targets` returns validated `(label, (host, port, path))` pairs without connecting. Invalid probe/set/comparison inputs raise `SessionInputError`; invalid frozen records raise `RecordError`. These are `ValueError` subclasses. An observed network/protocol failure returns a failed report rather than becoming invalid-input success.

Names beginning with an underscore, internal HTTP helpers, fixture/proxy classes and SDK runner internals are not stable APIs. `__version__` matches installed package metadata. Runtime dependencies remain empty.

## Report artifacts

| Artifact | Current version and compatibility |
| --- | --- |
| Session probe | `schema_version: 3`, `report_type: "mcp-session-probe"`. `compare` continues to read legacy schema 1 and 2. Schema 1 has no report_type and no ping/reconnect counters. |
| Endpoint set | `schema_version: 1`, `report_type: "mcp-endpoint-set"`. Contains safe labels, outcomes and nested session reports. |
| Comparison | `schema_version: 1`, `report_type: "mcp-probe-comparison"`. Contains `same_observations`, typed `changes` and `catalogue_comparisons`. |
| Native frozen record | Exact scope and definition SHA-256 `e9e7811a19276af102b78197ee4ba3a69eec8d5569459690ccf93a487eb49d7f`, 168 rows. It is a separate format without the probe schema_version field. |

Field meanings, supported stage/failure/outcome values and numerical bounds in [usage](USAGE.md) remain compatible through 1.x. Readers must tolerate additional report fields and use typed observations, not JSON property order, whitespace, advisory text, timing, response byte counts or UUID values. The strict native-record format requires its exact field set and frozen definition; it is not an extensible arbitrary-trace format.

A catalogue digest covers all advertised tool fields after complete validated discovery, sorted by unique tool name with recursively sorted object keys, UTF-8, compact JSON, `ensure_ascii=False` and `allow_nan=False`. Tool order and page partition normalize; array order and numeric JSON representation do not. Changing this algorithm requires a new report schema with an explicit migration. A legacy or incomplete catalogue is `unavailable`, never evidence of equality. Neither hashes nor successful comparisons authenticate the author or establish semantic compatibility.

## Release compatibility

Patch releases fix defects and clarify documentation while retaining the supported contracts. Minor releases may add commands/options, optional fields or supported environments; they retain existing 1.x readers and documented defaults. Removing a command/public API, changing exit meanings, narrowing supported inputs/environments or reinterpreting an existing schema requires a major release and migration notes. A defect fix that rejects input already documented as invalid is not a compatibility break.

Supported verification targets are Python 3.11 to 3.13 on POSIX macOS/Linux. CI covers those Python versions on Linux; other operating systems or Python versions are not qualified. Pinned optional SDK versions are reproduction inputs, not a promise to support arbitrary upstream releases. Security fixes and any unavoidable compatibility impact must be called out in the changelog. No LTS or response-time commitment is implied.
