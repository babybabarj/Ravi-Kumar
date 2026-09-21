from __future__ import annotations

from pathlib import Path

import pytest

from btceth_os.sources.binance.timestamp_audit import TimestampPolicyAuditor


def test_spot_pre_2025_millisecond_policy(tmp_path: Path):
    """Spot trades in 2024 must be 13 digits (ms)."""
    csv_file = tmp_path / "spot_2024.csv"
    csv_file.write_text(
        "trade_id,price,qty,quote_qty,time,is_buyer_maker,is_best_match\n"
        "1,50000.0,0.1,5000.0,1735603200000,true,true\n"  # 13 digits (2024-12-31)
    )

    res = TimestampPolicyAuditor.audit_file(
        csv_file,
        dataset_id="BINANCE:SPOT:BTCUSDT:TRADES",
        symbol="BTCUSDT",
        market="spot",
        period_key="2024-12",
    )
    assert res.declared_policy_unit == "ms"
    assert res.digits_observed == 13
    assert res.policy_compliant is True


def test_spot_post_2025_microsecond_policy(tmp_path: Path):
    """Spot trades in 2025+ must be 16 digits (us)."""
    csv_file = tmp_path / "spot_2025.csv"
    csv_file.write_text(
        "trade_id,price,qty,quote_qty,time,is_buyer_maker,is_best_match\n"
        "1,90000.0,0.1,9000.0,1735689600000000,true,true\n"  # 16 digits (2025-01-01)
    )

    res = TimestampPolicyAuditor.audit_file(
        csv_file,
        dataset_id="BINANCE:SPOT:BTCUSDT:TRADES",
        symbol="BTCUSDT",
        market="spot",
        period_key="2025-01",
    )
    assert res.declared_policy_unit == "us"
    assert res.digits_observed == 16
    assert res.policy_compliant is True


def test_spot_2025_rejects_millisecond_regression(tmp_path: Path):
    """If Spot 2025 has only 13 digits, it violates declared microsecond policy."""
    csv_file = tmp_path / "spot_2025_bad.csv"
    csv_file.write_text(
        "trade_id,price,qty,quote_qty,time,is_buyer_maker,is_best_match\n"
        "1,90000.0,0.1,9000.0,1735689600000,true,true\n"  # 13 digits when 16 expected!
    )

    res = TimestampPolicyAuditor.audit_file(
        csv_file,
        dataset_id="BINANCE:SPOT:BTCUSDT:TRADES",
        symbol="BTCUSDT",
        market="spot",
        period_key="2025-01",
    )
    assert res.declared_policy_unit == "us"
    assert res.digits_observed == 13
    assert res.policy_compliant is False


def test_usdm_fixed_millisecond_across_years(tmp_path: Path):
    """USD-M remains 13 digits (ms) across 2024, 2025, and 2026."""
    csv_2024 = tmp_path / "usdm_2024.csv"
    csv_2024.write_text("open_time,open,high,low,close\n1732953600000,50000,51000,49000,50500\n")

    csv_2025 = tmp_path / "usdm_2025.csv"
    csv_2025.write_text("open_time,open,high,low,close\n1735689600000,90000,91000,89000,90500\n")

    res_2024 = TimestampPolicyAuditor.audit_file(
        csv_2024, "BINANCE:USD_M_PERP:BTCUSDT:KLINES_1M", "BTCUSDT", "usdm", "2024-11"
    )
    assert res_2024.declared_policy_unit == "ms"
    assert res_2024.digits_observed == 13
    assert res_2024.policy_compliant is True

    res_2025 = TimestampPolicyAuditor.audit_file(
        csv_2025, "BINANCE:USD_M_PERP:BTCUSDT:KLINES_1M", "BTCUSDT", "usdm", "2025-01"
    )
    assert res_2025.declared_policy_unit == "ms"
    assert res_2025.digits_observed == 13
    assert res_2025.policy_compliant is True
