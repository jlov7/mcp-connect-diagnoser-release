#!/bin/sh
# Explicit optional gate. No skip path and no dependency installation in this script.
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
: "${SDK_PYTHON:?Set SDK_PYTHON to the absolute locked SDK environment interpreter}"
: "${NODE_BIN:?Set NODE_BIN to the absolute Node 24.15.0 executable}"
: "${NATIVE_OUTPUT:?Set NATIVE_OUTPUT to a fresh absolute JSON evidence path}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$root/.release-scratch/uv-cache}"
test "$("$NODE_BIN" --version)" = v24.15.0
cd "$root"
PYTHONPATH="$root/src" uv run --no-project --python "$SDK_PYTHON" python tests/sdk/gate.py \
  --python "$SDK_PYTHON" --node "$NODE_BIN" --output "$NATIVE_OUTPUT"
PYTHONPATH="$root/src" uv run --no-project --python "$SDK_PYTHON" python -m mcp_connect_diagnoser summarize "$NATIVE_OUTPUT"
PYTHONPATH="$root/src" uv run --no-project --python "$SDK_PYTHON" python scripts/verify_session.py \
  --python "$SDK_PYTHON" --output "${NATIVE_OUTPUT%.json}.sessions.json"
PYTHONPATH="$root/src" uv run --no-project --python "$SDK_PYTHON" python scripts/verify_ping_metadata.py \
  --python "$SDK_PYTHON" --output "${NATIVE_OUTPUT%.json}.metadata.json"
