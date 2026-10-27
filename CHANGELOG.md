# Changelog

## 1.0.2 (unreleased)

- Resume supported SSE streams with the exact UTF-8 event-ID bytes, up to 1024 bytes. Keep the original deadline, reconnect bounds, session/protocol headers and refusal to repeat the operation POST. Session-ID restrictions are unchanged.
- Preserve the existing 1024-character event-ID bound for completed responses. The UTF-8 byte bound applies when creating a resume header, so complete streams do not lose previously accepted inputs.
- Give constant next-action guidance for standard server-reported JSON-RPC error categories. Raw messages and error data remain omitted; a category is not a verified root cause.
- Add real socket regressions for Unicode cursors, exact and excessive byte lengths, failed resume, non-disclosure and cleanup. Require these tests in the source distribution.

## 1.0.1 (unreleased)

- Update the optional TypeScript SDK harness lock to `body-parser` 2.4.0 for [GHSA-27r3-jxmh-p828](https://github.com/expressjs/body-parser/security/advisories/GHSA-27r3-jxmh-p828). Direct SDK pins and the dependency-free product runtime are unchanged. Dedicated exploitation validation is NOT RUN.
- Avoid reverse-DNS lookup while binding owned literal-loopback fixtures, proxies and the supplied quickstart. Python 3.11 startup could otherwise stall before a probe deadline began.
- Accept legal common metadata on supported ping requests and results without disclosing its contents. Preserve strict parsing, bounded server requests and unsupported-method refusal.
- Add native SDK metadata sessions and an explicit compatibility table. The locked Python SDK rejects fractional progress tokens during typed construction; authored wire tests separately cover legal finite numbers.
- Pin Linux workflows to Ubuntu 24.04 and include the new compatibility fixtures in source distributions.

## 1.0.0

- Establish the documented CLI, Python API and artifact compatibility policy. Existing session schema 3, endpoint-set/comparison schema 1 and legacy readers remain supported.
- Reject non-regular native-record inputs with a structured error, including FIFOs that previously blocked while opening.
- Add a target-free `--version` command shared by console and module invocation.
- Supply a bounded credential-free JSON/SSE quickstart with saved metadata drift, intentional failure and recovery reports, plus a workflow diagram.
- Add pinned Ruff 0.17.1 CI and resolve existing lint findings without suppressing rules or changing frozen experiment values.

This is a bounded local developer tool. Human effectiveness, general protocol conformance, production and semantic tool correctness remain unqualified.
