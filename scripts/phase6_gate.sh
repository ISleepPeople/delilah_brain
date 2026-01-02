#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

VENV_BIN="$(pwd)/.venv/bin"
"$VENV_BIN/pytest" -q tests/phase6
