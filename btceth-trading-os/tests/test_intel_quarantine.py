"""Regression tests for Trade Board quarantine and separate BTC bot isolation.

Enforces Section 0 and Section 22 of the INTEL specification:
- Trade board decision engine is quarantined and absent from active intelligence tree.
- Zero source code in src/btceth_os depends on /Users/ravi/BTCUSD trade bot.
- Forbidden execution fields (BUY, SELL, LONG, SHORT, STOP_LOSS, TAKE_PROFIT, etc.) are strictly rejected.
- Strategy and execution layers remain NOT IMPLEMENTED.
"""

from pathlib import Path
import pytest

from btceth_os.intel.snapshot import (
    FORBIDDEN_EXECUTION_FIELDS,
    ExecutionFieldForbiddenError,
    IntelligenceSnapshot,
    assert_no_execution_fields,
)

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src" / "btceth_os"


def test_trade_board_engine_is_quarantined_and_absent():
    """Verify src/btceth_os/trade_board.py is completely absent from active code."""
    trade_board_path = SRC_DIR / "trade_board.py"
    assert not trade_board_path.exists(), (
        f"QUARANTINE BREACH: {trade_board_path} must not exist in active INTEL branch."
    )


def test_no_source_references_separate_btc_bot_directory():
    """Scan all python files in src/btceth_os to ensure zero references to separate bot."""
    prohibited_patterns = [
        "BTCUSD trade bot",
        "veteran_playbook",
        "pre_move_engine",
        "shadow_trader",
        "forward_predictions.sqlite",
        "regime_history.sqlite",
    ]

    violations = []
    for py_file in SRC_DIR.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for pattern in prohibited_patterns:
            if pattern in content:
                violations.append(f"{py_file.relative_to(ROOT)} contains prohibited reference: '{pattern}'")

    assert not violations, f"SEPARATE BTC BOT CONTAMINATION FOUND:\n" + "\n".join(violations)


def test_execution_fields_unconditionally_prohibited_in_intelligence():
    """Verify that execution directives are strictly forbidden at schema and dict levels."""
    for field in (
        "BUY", "SELL", "LONG", "SHORT", "ENTRY", "EXIT", "ENTRY_PRICE",
        "STOP_LOSS", "TAKE_PROFIT", "LEVERAGE", "POSITION_SIZE", "SIGNAL",
    ):
        with pytest.raises(ExecutionFieldForbiddenError):
            assert_no_execution_fields({"timestamp": "2026-09-24T00:00:00Z", field: "test"})

        with pytest.raises(ExecutionFieldForbiddenError):
            assert_no_execution_fields({"timestamp": "2026-09-24T00:00:00Z", "nested": {field: 123}})


def test_intelligence_snapshot_rejects_trade_directives():
    """Verify that IntelligenceSnapshot cannot be instantiated with execution fields."""
    with pytest.raises(ExecutionFieldForbiddenError):
        IntelligenceSnapshot(
            timestamp_utc="2026-09-24T00:00:00Z",
            asset="BTCUSDT",
            feature_set="INTEL_FEATURESET_V1",
            market_quality="HEALTHY",
            trend_state="UP",
            volatility_state="NORMAL",
            activity_state="NORMAL",
            funding_state="NEUTRAL",
            session_state="CONTINUOUS_24X7",
            features={"price": 60000.0, "TAKE_PROFIT": 65000.0},
        )
