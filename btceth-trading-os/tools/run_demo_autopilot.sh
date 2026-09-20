#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV="$ROOT_DIR/.venv-phase1a"
if [[ -f "$VENV/bin/python" ]]; then
    PYTHON="$VENV/bin/python"
else
    PYTHON="python3"
fi

exec "$PYTHON" -m btceth_os.autopilot "$@"
