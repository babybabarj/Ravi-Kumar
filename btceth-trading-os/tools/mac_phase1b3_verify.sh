#!/usr/bin/env bash
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -x .venv-phase1a/bin/python ]; then
  echo "ERROR: run the existing Phase 1 verification bootstrap first (.venv-phase1a missing)." >&2
  exit 10
fi

.venv-phase1a/bin/python tools/verify_phase1b3.py
