#!/bin/sh
# Run from source or an extracted release archive. Retain scratch for inspection.
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
mkdir -p .release-scratch
run=$(mktemp -d "$root/.release-scratch/verify.XXXXXXXX")
export UV_CACHE_DIR="${UV_CACHE_DIR:-$root/.release-scratch/uv-cache}"
python_version=${PYTHON_VERSION:-3.13}
PYTHONPATH="$root/src" uv run --no-project --python "$python_version" python -m unittest discover -s tests -v
uv build --python "$python_version" --build-constraints requirements-release.txt --out-dir "$run/dist"
uv run --no-project --python "$python_version" python scripts/verify_package.py "$run"
printf 'Package verification scratch: %s\n' "$run"
