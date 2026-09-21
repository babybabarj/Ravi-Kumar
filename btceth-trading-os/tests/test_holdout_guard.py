from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
import pyarrow as pa
import pyarrow.parquet as pq

from btceth_os.research.data_guard import (
    DatasetRole,
    HoldoutAccessDeniedError,
    ResearchDataAccessGuard,
    ResearchOperation,
    load_research_parquet,
    LEDGER_PATH,
    HOLDOUT_WINDOW_START_NS,
    HOLDOUT_WINDOW_END_NS,
)


def test_direct_holdout_role_blocked() -> None:
    """Direct attempt to access LOCKED_HOLDOUT during research/tuning fails closed."""
    for op in [
        ResearchOperation.HYPOTHESIS_GENERATION,
        ResearchOperation.FEATURE_SELECTION,
        ResearchOperation.PARAMETER_TUNING,
        ResearchOperation.BACKTEST,
    ]:
        with pytest.raises(HoldoutAccessDeniedError) as exc_info:
            ResearchDataAccessGuard.check_access(
                operation=op,
                dataset_id="BTCUSDT_2024",
                dataset_role=DatasetRole.LOCKED_HOLDOUT,
            )
        assert "HOLDOUT_FIREWALL_VIOLATION" in str(exc_info.value)


def test_renamed_holdout_file_blocked_by_timestamp_metadata(tmp_path: Path) -> None:
    """Even if a holdout file is renamed to innocent name without '2024', guard blocks it based on timestamps/metadata."""
    # Create Parquet file with NO '2024' in filename: innocent_sample_data.parquet
    innocent_file = tmp_path / "innocent_sample_data.parquet"
    
    # Mid-2024 timestamp (June 15, 2024)
    ts_mid_2024 = int(datetime(2024, 6, 15, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    
    schema = pa.schema(
        [("ts_event_ns", pa.int64()), ("price", pa.float64())],
        metadata={
            b"dataset_role": b"LOCKED_HOLDOUT",
            b"start_ts_ns": str(ts_mid_2024).encode(),
            b"end_ts_ns": str(ts_mid_2024 + 3600_000_000_000).encode(),
        },
    )
    table = pa.Table.from_arrays([[ts_mid_2024], [65000.0]], schema=schema)
    pq.write_table(table, innocent_file)

    # Attempting to load this innocent-named file via load_research_parquet must fail!
    with pytest.raises(HoldoutAccessDeniedError) as exc_info:
        load_research_parquet(innocent_file, operation=ResearchOperation.BACKTEST)
    assert "HOLDOUT_FIREWALL_VIOLATION" in str(exc_info.value)


def test_holdout_timestamp_range_queries_blocked() -> None:
    """Queries overlapping the 2024-01-01 to 2024-11-30 window are strictly blocked."""
    # Start in 2023, ends in mid-2024 -> overlaps holdout
    start_2023 = int(datetime(2023, 11, 1, tzinfo=timezone.utc).timestamp() * 1e9)
    end_2024 = int(datetime(2024, 2, 1, tzinfo=timezone.utc).timestamp() * 1e9)
    with pytest.raises(HoldoutAccessDeniedError):
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.FEATURE_SELECTION,
            dataset_id="test_query",
            start_ts_ns=start_2023,
            end_ts_ns=end_2024,
        )


def test_prospective_forward_2025_data_allowed(tmp_path: Path) -> None:
    """Prospective data from 2025 is explicitly ALLOWED (not blocked by blanket >= 2024 rule)."""
    ts_2025 = int(datetime(2025, 3, 1, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    
    # Must pass guard check cleanly
    allowed = ResearchDataAccessGuard.check_access(
        operation=ResearchOperation.PROSPECTIVE_VALIDATION,
        dataset_id="BTCUSDT_2025_PROSPECTIVE",
        dataset_role=DatasetRole.PROSPECTIVE_FORWARD,
        start_ts_ns=ts_2025,
        end_ts_ns=ts_2025 + 3600_000_000_000,
    )
    assert allowed is True

    # Loading a 2025 parquet file succeeds
    p2025_file = tmp_path / "btcusdt_2025_forward.parquet"
    table = pa.Table.from_arrays(
        [[ts_2025], [95000.0]],
        schema=pa.schema(
            [("ts_event_ns", pa.int64()), ("price", pa.float64())],
            metadata={b"dataset_role": b"PROSPECTIVE_FORWARD", b"start_ts_ns": str(ts_2025).encode(), b"end_ts_ns": str(ts_2025).encode()},
        ),
    )
    pq.write_table(table, p2025_file)

    loaded = load_research_parquet(
        p2025_file,
        operation=ResearchOperation.PROSPECTIVE_VALIDATION,
        dataset_role=DatasetRole.PROSPECTIVE_FORWARD,
    )
    assert loaded.num_rows == 1


def test_prospective_forward_2026_data_allowed() -> None:
    """Prospective data from 2026 (e.g. current live forward data) is explicitly ALLOWED."""
    ts_2026 = int(datetime(2026, 9, 21, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    allowed = ResearchDataAccessGuard.check_access(
        operation=ResearchOperation.PROSPECTIVE_VALIDATION,
        dataset_id="BTCUSDT_2026_LIVE_FORWARD",
        dataset_role=DatasetRole.PROSPECTIVE_FORWARD,
        start_ts_ns=ts_2026,
        end_ts_ns=ts_2026 + 3600_000_000_000,
    )
    assert allowed is True


def test_development_and_validation_datasets_allowed() -> None:
    """2020-2023 development and validation datasets pass without error."""
    ts_2021 = int(datetime(2021, 6, 1, tzinfo=timezone.utc).timestamp() * 1e9)
    ts_2023 = int(datetime(2023, 6, 1, tzinfo=timezone.utc).timestamp() * 1e9)

    assert ResearchDataAccessGuard.check_access(
        operation=ResearchOperation.BACKTEST,
        dataset_id="BTCUSDT_DEV",
        dataset_role=DatasetRole.DEVELOPMENT,
        start_ts_ns=ts_2021,
        end_ts_ns=ts_2021 + 3600_000_000_000,
    ) is True

    assert ResearchDataAccessGuard.check_access(
        operation=ResearchOperation.BACKTEST,
        dataset_id="BTCUSDT_VAL",
        dataset_role=DatasetRole.VALIDATION,
        start_ts_ns=ts_2023,
        end_ts_ns=ts_2023 + 3600_000_000_000,
    ) is True


def test_ledger_records_access_events() -> None:
    """Verify that ledger records both blocked and allowed events with full metadata."""
    assert LEDGER_PATH.is_file(), "Ledger path must exist after tests run"
    lines = [json.loads(line) for line in LEDGER_PATH.read_text(encoding="utf-8").strip().splitlines() if line.strip()]
    assert len(lines) > 0

    decisions = {entry.get("decision") for entry in lines}
    assert "BLOCKED" in decisions
    assert "ALLOWED" in decisions
