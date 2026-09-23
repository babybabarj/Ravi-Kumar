"""Tests for XAU session semantics and GoldSessionState."""

from datetime import datetime, timezone
import pytest

from btceth_os.sessions import (
    CombinedSessionSnapshot,
    GoldSessionState,
    PerpetualContractSession,
    UnderlyingReferenceSession,
    evaluate_sessions,
)


def test_perpetual_contract_session_trades_24_7() -> None:
    session = PerpetualContractSession()
    # Weekend Saturday noon UTC
    sat = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    assert session.get_state(sat) == GoldSessionState.CONTRACT_TRADING

    # Underlying daily break 21:30 UTC (17:30 ET)
    break_time = datetime(2026, 9, 16, 21, 30, tzinfo=timezone.utc)
    assert session.get_state(break_time) == GoldSessionState.CONTRACT_TRADING


def test_underlying_reference_session_identifies_off_hours() -> None:
    underlying = UnderlyingReferenceSession()

    # Saturday is off-hours index mode
    sat = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    assert underlying.get_state(sat) == GoldSessionState.UNDERLYING_OFF_HOURS_INDEX_MODE

    # Wednesday 14:00 UTC (10:00 ET) is regular open
    wed = datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc)
    assert underlying.get_state(wed) == GoldSessionState.UNDERLYING_OPEN


def test_evaluate_sessions_keeps_clocks_distinct() -> None:
    # During weekend, contract is tradable even though underlying is in off-hours mode
    sat = datetime(2026, 9, 19, 15, 0, tzinfo=timezone.utc)
    snap = evaluate_sessions(sat)
    assert snap.underlying_state == GoldSessionState.UNDERLYING_OFF_HOURS_INDEX_MODE
    assert snap.contract_state == GoldSessionState.CONTRACT_TRADING
    assert snap.is_contract_tradable is True
