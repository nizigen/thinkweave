#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  PY_BIN="python"
fi

"$PY_BIN" "$ROOT/scripts/longform_eval_runner.py"
