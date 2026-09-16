#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p reports artifacts

choose_python() {
  if command -v python3.12 >/dev/null 2>&1; then
    echo "python3.12"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    if python3 - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3,12) else 1)
PY
    then
      echo "python3"
      return
    fi
  fi
  if command -v brew >/dev/null 2>&1; then
    echo "Python 3.12 not found. Installing python@3.12 with Homebrew..." >&2
    brew install python@3.12 >&2 || exit 10
    echo "$(brew --prefix python@3.12)/bin/python3.12"
    return
  fi
  echo "ERROR: Python 3.12+ is required. Install Homebrew/Python 3.12 and rerun." >&2
  exit 10
}

PYTHON_BIN="$(choose_python)"
echo "Using: $PYTHON_BIN"

if [ ! -d .venv-phase1a ]; then
  "$PYTHON_BIN" -m venv .venv-phase1a || exit 11
fi
# shellcheck disable=SC1091
source .venv-phase1a/bin/activate
pip install -e '.[test]' >/dev/null || exit 13

echo ""
echo "[1/3] Running automated Phase 1B.1 + regression test suite..."
pytest -q 2>&1 | tee reports/PHASE_1B_1_TEST_RESULTS.txt
TEST_EXIT=${PIPESTATUS[0]}

echo ""
echo "[2/3] Running zero-trading security scan..."
python -m btceth_os.security_scan 2>&1 | tee reports/PHASE_1B_1_SECURITY_SCAN.txt
SECURITY_EXIT=${PIPESTATUS[0]}

echo ""
echo "[3/3] Running mechanical discovery, contract, and planner acceptance checks..."
TEST_EXIT="$TEST_EXIT" SECURITY_EXIT="$SECURITY_EXIT" python tools/verify_phase1b1.py
FINAL_EXIT=$?

exit "$FINAL_EXIT"
