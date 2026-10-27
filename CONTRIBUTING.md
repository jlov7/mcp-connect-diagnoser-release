# Contributing

Keep changes small and within the documented reproduction. Add a failing
regression for a defect, preserve frozen cases and negative outcomes, and run
`sh scripts/verify-release.sh`. Changes to transport or SDK behavior also require
the pinned `scripts/verify-native.sh` gate, with all 168 responses and no skips.
Run pinned `uvx --from ruff==0.17.1 ruff check src tests scripts examples` too.
Report exact commands, versions, counts and remaining unrun qualifications.
Preserve the [V1 compatibility policy](docs/STABILITY.md) and follow the
[release checks](docs/RELEASING.md).

Do not add real credentials, personal data, confidential logs or SDK installations
to the repository. Keep original-code MIT licensing and third-party provenance
intact. Changes to claims need evidence, not a relaxed validator or a removed
counterexample. Use synthetic reproductions in issues and pull requests. Review the
[security/support guidance](SECURITY.md) before sharing logs.
