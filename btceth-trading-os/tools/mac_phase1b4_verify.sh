#!/usr/bin/env bash
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
.venv-phase1a/bin/python tools/verify_phase1b4.py
