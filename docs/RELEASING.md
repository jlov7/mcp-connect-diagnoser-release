# Release and support policy

The CLI's compatibility promises are defined in [stability](STABILITY.md). The package and source archive ship the same original-code MIT licence. Optional SDKs and build/lint tools retain their own licences.

## Maintainer checks

1. Add a failure-reproducing regression for each behavior defect. Preserve existing frozen definitions, negative records and partial outputs.
2. Update `pyproject.toml`, `mcp_connect_diagnoser.__version__`, package identity checks and [CHANGELOG](../CHANGELOG.md) consistently. Describe any contract migration.
3. Run `sh scripts/verify-release.sh` and pinned `uvx --from ruff==0.17.1 ruff check src tests scripts examples`. The package gate includes the supplied quickstart and source/installed tests.
4. For transport or SDK changes, run the unchanged locked `scripts/verify-native.sh` job. It has no skip path. Preserve failed attempts and use fresh output names.
5. Retain exact source/package hashes, commands, counts/skips and limitations. Inspect the sdist/wheel for private paths, credentials, caches, planning files and missing docs/assets. Check all README examples and local links against the package.
6. Require successful CI for the exact reviewed commit before integrating a release. A workflow definition or earlier commit's green check is insufficient. Repository-host enforcement may depend on the hosting plan; this remains a maintainer process requirement.
7. Review original-code rights, third-party provenance, release notes and distribution contents before distribution. Tag only the reviewed commit after the maintainer approves that release.

Reproduce the core check with Python 3.11, 3.12 and 3.13, and the native job with its separately pinned Python/Node/SDK versions. A locally passing suite is software evidence at those boundaries. It does not establish independent scientific validation, human productivity, tool-body semantics or production readiness.

## Report a problem

For a usage or reproducible behavior problem, open an issue in the repository that supplied this source. Include `mcp-connect-diagnoser --version`, Python/OS versions, the command with sensitive paths removed, exit code, request ID and a minimal synthetic reproducer. Consult [security/support](../SECURITY.md) before sharing reports. There is no response-time or long-term support commitment.
