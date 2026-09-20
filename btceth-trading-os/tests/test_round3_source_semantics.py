"""Unit tests for Research Round 3 source semantics and reference price rules."""
import json
from pathlib import Path
import pytest

from btceth_os.research.structural.basis_metrics import (
    compute_trade_basis,
    compute_trade_basis_ratio,
    compute_mark_spot_basis,
    compute_mark_spot_basis_ratio,
    compute_perp_index_basis,
)

ROOT = Path(__file__).resolve().parents[1]


def test_source_semantics_audit_artifacts_exist():
    md_file = ROOT / "reports" / "ROUND3_SOURCE_SEMANTICS_AUDIT.md"
    json_file = ROOT / "reports" / "ROUND3_SOURCE_SEMANTICS_AUDIT.json"
    assert md_file.exists(), "ROUND3_SOURCE_SEMANTICS_AUDIT.md must exist"
    assert json_file.exists(), "ROUND3_SOURCE_SEMANTICS_AUDIT.json must exist"

    data = json.loads(json_file.read_text())
    assert data["status"] == "REMEDIATED"
    assert len(data["findings"]) >= 3
    assert "BTCUSDT" in data["official_sources_verified"]
    assert "ETHUSDT" in data["official_sources_verified"]


def test_distinct_basis_formulas():
    # Scenario:
    # Traded Spot: $50,000
    # Traded Perp: $50,050 (Binance order book price)
    # Index Price: $50,010 (Global spot basket)
    # Mark Price: $50,030 (Smoothed liquidation reference)
    p_spot = 50000.0
    p_perp = 50050.0
    p_index = 50010.0
    p_mark = 50030.0

    trade_basis = compute_trade_basis(p_perp, p_spot)
    assert trade_basis == 50.0

    trade_basis_ratio = compute_trade_basis_ratio(p_perp, p_spot)
    assert abs(trade_basis_ratio - 0.001) < 1e-6  # 10 bps

    mark_spot_basis = compute_mark_spot_basis(p_mark, p_spot)
    assert mark_spot_basis == 30.0

    perp_index_basis = compute_perp_index_basis(p_perp, p_index)
    assert perp_index_basis == 40.0

    # Ensure none of these metrics are falsely collapsed into a single value
    assert trade_basis != mark_spot_basis
    assert trade_basis != perp_index_basis


def test_history_extension_plan_exists():
    plan = ROOT / "reports" / "ROUND3_HISTORY_EXTENSION_PLAN.md"
    assert plan.exists(), "ROUND3_HISTORY_EXTENSION_PLAN.md must exist"
    content = plan.read_text()
    assert "2020-01" in content
    assert "CORE_PRICE_HISTORY" in content
    assert "CARRY_HISTORY" in content
    assert "REFERENCE_PRICE_HISTORY" in content
