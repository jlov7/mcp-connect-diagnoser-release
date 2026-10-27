# Security

This tool uses authored loopback fixtures and an offline native-record verifier.
Do not use real credentials or production traces. It has no telemetry and does
not accept a remote target URL in the console interface. Native reproduction
starts only the documented synthetic SDK servers on literal 127.0.0.1.

Treat supplied records as untrusted data. The offline verifier enforces its
schema, count, byte and header bounds and executes no supplied code. Record
integrity is not authenticity. Review native logs before sharing: SDK error
bodies can contain local stack paths. Keep confidential reports and exploitable
production details out of public reports. This is not a security certification
or a production gateway.

## Support and private reporting

For usage problems, follow the minimal-report guidance in [release/support policy](docs/RELEASING.md).
For a suspected vulnerability, use the repository host's private reporting
channel if it is available, or contact the repository maintainer privately before
posting exploitable details. Do not upload credentials or production traces.
No response-time commitment or security certification is provided.
