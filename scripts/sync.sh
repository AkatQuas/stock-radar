#!/usr/bin/env bash
# Like `uv sync`, then apply patches/ (patch-package-py).
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync "$@"
uv run --group dev p12y apply
