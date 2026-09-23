"""Tests for XAUUSDT research capability matrix and execution constraints."""

import json
from pathlib import Path
import pytest

from btceth_os.capabilities import (
    CapabilityStatus,
    DEFAULT_XAU_CAPABILITIES,
    ExecutionConstraintViolationError,
    ResearchCapabilityMatrix,
)


def test_capabilities_presence_and_status():
    required_caps = {
        "BAR_DIRECTIONAL_RESEARCH": CapabilityStatus.VERIFIED,
        "MARK_PRICE_RESEARCH": CapabilityStatus.VERIFIED,
        "INDEX_PRICE_RESEARCH": CapabilityStatus.VERIFIED,
        "PREMIUM_INDEX_RESEARCH": CapabilityStatus.VERIFIED,
        "FUNDING_RESEARCH": CapabilityStatus.VERIFIED,
        "TRADE_PRINT_RESEARCH": CapabilityStatus.VERIFIED,
        "AGGTRADE_RESEARCH": CapabilityStatus.VERIFIED,
        "BEST_BID_ASK_RESEARCH": CapabilityStatus.NOT_COMPUTABLE,
        "ORDERBOOK_DEPTH_RESEARCH": CapabilityStatus.NOT_COMPUTABLE,
        "SESSION_GAP_RESEARCH": CapabilityStatus.VERIFIED,
        "RULE_EPOCH_REPLAY": CapabilityStatus.VERIFIED,
        "REALISTIC_FILL_RESEARCH": CapabilityStatus.NOT_COMPUTABLE,
    }

    matrix = ResearchCapabilityMatrix()
    for cap_name, expected_status in required_caps.items():
        assert cap_name in matrix.capabilities, f"Missing capability {cap_name}"
        cap = matrix.capabilities[cap_name]
        assert cap.status == expected_status, f"Expected {expected_status} for {cap_name}, got {cap.status}"
        if expected_status == CapabilityStatus.NOT_COMPUTABLE:
            assert cap.allowed_for_research is False
        else:
            assert cap.allowed_for_research is True


def test_execution_constraints_enforced():
    matrix = ResearchCapabilityMatrix()

    # Allowed capabilities do not raise
    matrix.assert_capability_allowed("BAR_DIRECTIONAL_RESEARCH")
    matrix.assert_capability_allowed("TRADE_PRINT_RESEARCH")
    matrix.assert_capability_allowed("AGGTRADE_RESEARCH")

    # Disallowed capabilities must raise ExecutionConstraintViolationError
    with pytest.raises(ExecutionConstraintViolationError, match="NOT_COMPUTABLE"):
        matrix.assert_capability_allowed("BEST_BID_ASK_RESEARCH")

    with pytest.raises(ExecutionConstraintViolationError, match="NOT_COMPUTABLE"):
        matrix.assert_capability_allowed("ORDERBOOK_DEPTH_RESEARCH")

    with pytest.raises(ExecutionConstraintViolationError, match="NOT_COMPUTABLE"):
        matrix.assert_capability_allowed("REALISTIC_FILL_RESEARCH")

    # Unknown capability raises KeyError
    with pytest.raises(KeyError):
        matrix.assert_capability_allowed("NON_EXISTENT_CAPABILITY")


def test_matrix_serialization(tmp_path: Path):
    matrix = ResearchCapabilityMatrix()
    d = matrix.to_dict()

    assert d["instrument_id"] == "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT"
    assert d["bar_level_research_ready"] is True
    assert d["orderbook_research_ready"] is False
    assert d["realistic_fills_ready"] is False

    test_file = tmp_path / "capability_matrix.json"
    matrix.save_json(test_file)
    assert test_file.exists()

    loaded = json.loads(test_file.read_text())
    assert loaded == d
