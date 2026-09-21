"""Tests for the mechanical holdout firewall (Package 1)."""
from datetime import datetime, timezone
from pathlib import Path
import pytest

from btceth_os.research.holdout_firewall import (
    HOLDOUT_START_TS_NS,
    HoldoutSecurityViolationError,
    enforce_path_firewall,
    enforce_timestamp_firewall,
)


def test_firewall_blocks_2024_market_files():
    """Verify that any file path referring to 2024 market data is rejected with hard error."""
    forbidden_paths = [
        "artifacts/research/silver_v3/BTCUSDT-spot-1m-2024-01.parquet",
        "data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-05.zip",
        "artifacts/research/silver_v3/ETHUSDT-funding-2024-11.parquet",
        "/tmp/market_cache_2024_klines.parquet",
    ]
    for p in forbidden_paths:
        with pytest.raises(HoldoutSecurityViolationError) as exc_info:
            enforce_path_firewall(p)
        assert "HOLDOUT FIREWALL VIOLATION" in str(exc_info.value)


def test_firewall_allows_pre_2024_files():
    """Verify that 2020-2023 development and validation files pass without error."""
    allowed_paths = [
        "artifacts/research/silver_v3/BTCUSDT-spot-1m-2020-01-2023-12.parquet",
        "artifacts/research/silver_v3/BTCUSDT-resampled-1h-v3.1.0.parquet",
        "artifacts/research/silver_v3/ETHUSDT-funding-2020-01-2023-12-v3.1.parquet",
    ]
    for p in allowed_paths:
        enforce_path_firewall(p)  # Should not raise


def test_firewall_blocks_2024_timestamps():
    """Verify that timestamps at or after 2024-01-01 00:00:00 UTC are blocked."""
    # 2024-01-01 00:00:00 UTC
    ts_2024 = HOLDOUT_START_TS_NS
    with pytest.raises(HoldoutSecurityViolationError) as exc_info:
        enforce_timestamp_firewall(ts_2024)
    assert "HOLDOUT FIREWALL VIOLATION" in str(exc_info.value)

    # 2024-06-15
    ts_mid_2024 = int(datetime(2024, 6, 15, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    with pytest.raises(HoldoutSecurityViolationError):
        enforce_timestamp_firewall(ts_mid_2024)


def test_firewall_allows_pre_2024_timestamps():
    """Verify that 2020-2023 timestamps are allowed."""
    ts_2020 = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    ts_2023 = int(datetime(2023, 12, 31, 23, 59, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    enforce_timestamp_firewall(ts_2020)
    enforce_timestamp_firewall(ts_2023)
