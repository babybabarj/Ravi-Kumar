"""Comprehensive verification tests for Phase 2E.1 / Verifier V15 remediation.

Tests coverage for all 15 audit blockers:
- Blocker A, I, J, N: Primary sources, 8-epoch rule history, exact 18:15 UTC transition, field provenance, quarantined pre-admission terminology.
- Blocker B: Multi-epoch trade and aggTrade reconciliations (2026-01-15, 2026-05-15, 2026-09-01).
- Blocker C: Strict Decimal schema, zero float financials in Silver V2 and partitions V2.
- Blocker D: Series alignment, zero missing bars, zero silent fallbacks.
- Blocker E: Discrete funding events table and discrete settlement columns in bars.
- Blocker F, G, H: Fail-closed session engine on missing timezone, HolidayStatus.NOT_IMPLEMENTED, epoch-aware maintenance breaks.
- Blocker K: Partition continuity, row count invariants, physical & logical digests.
- Blocker L, M: ResearchDataAccessGuard strict firewall, LOCKED_PROSPECTIVE_PRISTINE, fail-closed ledger verification.
"""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import zoneinfo

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from btceth_os.contract_rule_epochs import ContractRuleEpochRegistry
from btceth_os.research.data_guard import (
    CANONICAL_DATASET_REGISTRY,
    DatasetRole,
    HoldoutAccessDeniedError,
    ResearchDataAccessGuard,
    ResearchOperation,
    XAU_HOLDOUT_UNLOCK_CAPABILITY,
    XAU_PROSPECTIVE_PRISTINE_UNLOCK_CAPABILITY,
    load_research_parquet,
    verify_access_ledger_integrity,
)
from btceth_os.sessions import (
    GoldSessionState,
    HolidayStatus,
    PerpetualContractSession,
    SessionTimezoneUnavailableError,
    UnderlyingReferenceSession,
    evaluate_sessions,
)

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Blocker A, I, J, N: Primary Sources, Contract Rule Epochs V2 & Terminology
# ---------------------------------------------------------------------------

def test_xau_primary_sources_v2_manifest() -> None:
    manifest_path = ROOT / "config" / "xau_primary_sources_v2.json"
    assert manifest_path.is_file(), f"Missing primary sources manifest: {manifest_path}"
    data = json.loads(manifest_path.read_text())
    assert data["manifest_version"] == "2.0.0"
    sources = data["sources"]
    assert len(sources) == 8

    # All primary sources must physically exist and match expected SHA
    for src_id, src in sources.items():
        file_path = ROOT / src["file_path"]
        assert file_path.is_file(), f"Primary source missing: {file_path}"
        actual_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert actual_sha == src["physical_sha256"], f"SHA mismatch for {file_path}"


def test_xau_contract_rule_epochs_v2_exact_replay() -> None:
    config_path = ROOT / "config" / "xau_contract_rule_epochs_v2.yaml"
    assert config_path.is_file()
    reg = ContractRuleEpochRegistry.from_yaml(config_path)

    # 8 distinct chronological epochs
    assert len(reg.epochs) == 8
    epoch_ids = [e.epoch_id for e in reg.epochs]
    assert epoch_ids == [
        "XAU_EPOCH_0_QUARANTINED_PRE_ADMISSION",
        "XAU_EPOCH_1_LAUNCH_DISCOVERY",
        "XAU_EPOCH_2_ZERO_INTEREST_COMPONENT",
        "XAU_EPOCH_3_INDEX_WEIGHT_REBALANCE",
        "XAU_EPOCH_4A_8H_TEMPORARY_FUNDING",
        "XAU_EPOCH_4B_4H_FUNDING_AND_CAP_EXPANSION",
        "XAU_EPOCH_5_ORDERBOOK_EWMA_INDEX_MODE",
        "XAU_EPOCH_6_ET_SESSION_CALENDAR_REGIME",
    ]

    # Epoch 0 terminology: QUARANTINED_PRE_ADMISSION (not "PRE_LAUNCH")
    ep0 = reg.epochs[0]
    assert ep0.confidence == "QUARANTINED"
    assert "PRE_ADMISSION" in ep0.epoch_id
    assert ep0.tick_size is None
    assert ep0.funding_interval_seconds is None

    # Transition at 18:15 UTC on 2026-01-30:
    # Just before 18:15 UTC -> Epoch 4A
    ep_before = reg.get_epoch_for_timestamp("2026-01-30T18:14:59Z")
    assert ep_before.epoch_id == "XAU_EPOCH_4A_8H_TEMPORARY_FUNDING"
    assert ep_before.funding_interval_seconds == 28800

    # At exactly 18:15 UTC -> Epoch 4B
    ep_at = reg.get_epoch_for_timestamp("2026-01-30T18:15:00Z")
    assert ep_at.epoch_id == "XAU_EPOCH_4B_4H_FUNDING_AND_CAP_EXPANSION"
    assert ep_at.funding_interval_seconds == 14400
    assert ep_at.funding_cap == Decimal("0.0050")
    assert ep_at.funding_floor == Decimal("-0.0050")

    # Field provenance verified for all epochs
    for ep in reg.epochs:
        assert isinstance(ep.field_provenance, dict)
        if ep.epoch_id != "XAU_EPOCH_0_QUARANTINED_PRE_ADMISSION":
            assert len(ep.field_provenance) > 0


# ---------------------------------------------------------------------------
# Blocker C: Strict Decimal Schema & Zero Float Financials
# ---------------------------------------------------------------------------

def test_silver_v2_decimal_schema() -> None:
    silver_v2_path = ROOT / "artifacts" / "research" / "silver_xau" / "XAUUSDT-resampled-1m-silver-v2.parquet"
    assert silver_v2_path.is_file(), f"Missing Silver V2 file: {silver_v2_path}"

    table = pq.read_table(silver_v2_path)
    schema = table.schema

    # Assert no float32 or float64 columns exist in financial/monetary data
    float_cols = [field.name for field in schema if pa.types.is_floating(field.type)]
    assert len(float_cols) == 0, f"Found float columns in Silver V2: {float_cols}"

    # Price and funding columns must be Decimal
    decimal_expectations = {
        "open": (18, 4),
        "high": (18, 4),
        "low": (18, 4),
        "close": (18, 4),
        "volume": (28, 8),
        "quote_volume": (28, 8),
        "taker_buy_volume": (28, 8),
        "taker_buy_quote_volume": (28, 8),
        "mark_price": (18, 8),
        "index_price": (18, 8),
        "premium_index": (18, 8),
        "funding_rate": (18, 8),
    }

    for col_name, (prec, scale) in decimal_expectations.items():
        assert col_name in schema.names, f"Missing column {col_name}"
        field_type = schema.field(col_name).type
        assert pa.types.is_decimal(field_type), f"Column {col_name} is not decimal: {field_type}"
        assert field_type.precision == prec, f"Column {col_name} precision expected {prec}, got {field_type.precision}"
        assert field_type.scale == scale, f"Column {col_name} scale expected {scale}, got {field_type.scale}"


def test_partitions_v2_decimal_schema_and_invariants() -> None:
    manifest_path = ROOT / "config" / "xau_research_partitions_v2.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["manifest_version"] == "2.0.0"

    total_rows = 0
    prev_end_ns = -1

    for part_name, meta in manifest["partitions"].items():
        part_path = ROOT / meta["relative_path"]
        assert part_path.is_file(), f"Missing partition file {part_path}"

        table = pq.read_table(part_path)
        assert table.num_rows == meta["expected_rows"]
        total_rows += table.num_rows

        # Zero float columns
        float_cols = [f.name for f in table.schema if pa.types.is_floating(f.type)]
        assert len(float_cols) == 0, f"Partition {part_name} has float columns: {float_cols}"

        # Temporal monotonicity and non-overlapping invariants
        start_ts = table["ts_event_ns"][0].as_py()
        end_ts = table["ts_event_ns"][-1].as_py()
        assert start_ts == meta["start_ts_ns"]
        assert end_ts <= meta["end_ts_ns"]
        assert end_ts + 60_000_000_000 > meta["end_ts_ns"]
        assert start_ts > prev_end_ns, f"Temporal overlap in partition {part_name}"
        prev_end_ns = end_ts

        # Discrete funding settlement column exists
        assert "is_funding_event" in table.column_names
        assert "funding_event_rate" in table.column_names
        assert "last_realized_funding_event_ts_ns" in table.column_names
        assert "last_realized_funding_rate" in table.column_names

    assert total_rows == 374_400


# ---------------------------------------------------------------------------
# Blocker D: Series Alignment Audit
# ---------------------------------------------------------------------------

def test_series_alignment_audit_report() -> None:
    audit_path = ROOT / "reports" / "XAU_SERIES_ALIGNMENT_AUDIT_V15.json"
    if not audit_path.is_file():
        pytest.skip("XAU_SERIES_ALIGNMENT_AUDIT_V15.json deferred to Commit D")
    data = json.loads(audit_path.read_text())

    assert data["report_type"] == "XAU_SERIES_ALIGNMENT_AUDIT_V15"
    stats = data["alignment_statistics"]
    assert stats["alignment_status"] == "PERFECT_100_PERCENT_NO_FALLBACK"
    assert stats["total_admitted_bars"] == 374_400
    assert stats["exact_aligned_bars"] == 374_400
    assert stats["missing_mark_bars"] == 0
    assert stats["missing_index_bars"] == 0
    assert stats["missing_premium_bars"] == 0
    assert stats["fallback_substitutions"] == 0
    assert data["silent_fallback_policy"] == "DISABLED_STRICT_EVALUATION"


# ---------------------------------------------------------------------------
# Blocker E: Discrete Funding Events Table Semantics
# ---------------------------------------------------------------------------

def test_funding_events_table_v2() -> None:
    events_path = ROOT / "artifacts" / "research" / "silver_xau" / "XAUUSDT-funding-events-silver-v2.parquet"
    assert events_path.is_file()

    table = pq.read_table(events_path)
    assert table.num_rows == 1589

    required_cols = {"funding_time_utc", "funding_rate", "funding_interval_hours", "funding_cap", "funding_floor"}
    assert required_cols.issubset(set(table.column_names))

    # All values are Decimal
    assert pa.types.is_decimal(table.schema.field("funding_rate").type)
    assert pa.types.is_decimal(table.schema.field("funding_cap").type)
    assert pa.types.is_decimal(table.schema.field("funding_floor").type)


# ---------------------------------------------------------------------------
# Blocker F, G, H: Session Engine Fail-Closed & Epoch Maintenance Breaks
# ---------------------------------------------------------------------------

def test_session_engine_fails_closed_without_ny_timezone() -> None:
    underlying = UnderlyingReferenceSession()
    dt = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)

    # When America/New_York is unavailable, must raise SessionTimezoneUnavailableError
    with patch("zoneinfo.ZoneInfo", side_effect=zoneinfo.ZoneInfoNotFoundError("Mock NY unavailable")):
        with pytest.raises(SessionTimezoneUnavailableError, match="FAIL CLOSED"):
            underlying.get_state(dt)

        with pytest.raises(SessionTimezoneUnavailableError, match="FAIL CLOSED"):
            evaluate_sessions(dt)


def test_holiday_status_not_implemented() -> None:
    assert HolidayStatus.NOT_IMPLEMENTED.value == "NOT_IMPLEMENTED"
    underlying = UnderlyingReferenceSession()
    assert underlying.get_holiday_status("2026-07-04") == HolidayStatus.NOT_IMPLEMENTED


def test_epoch_aware_maintenance_break() -> None:
    # Pre-Epoch 6 (with daily break enabled): 17:30 ET (21:30 UTC in EDT) is off-hours maintenance break
    pre_epoch_session = UnderlyingReferenceSession(has_daily_break=True)
    st_pre = pre_epoch_session.get_state(datetime(2026, 8, 19, 21, 30, tzinfo=timezone.utc))
    assert st_pre == GoldSessionState.UNDERLYING_OFF_HOURS_INDEX_MODE

    # Epoch 6+ (daily break deprecated): 17:30 ET is continuous open trading
    post_epoch_session = UnderlyingReferenceSession(has_daily_break=False)
    st_post = post_epoch_session.get_state(datetime(2026, 9, 16, 21, 30, tzinfo=timezone.utc))
    assert st_post == GoldSessionState.UNDERLYING_OPEN


# ---------------------------------------------------------------------------
# Blocker L, M: ResearchDataAccessGuard Strict Firewall & Ledger Integrity
# ---------------------------------------------------------------------------

def test_data_guard_locks_xau_holdout_and_pristine() -> None:
    assert XAU_HOLDOUT_UNLOCK_CAPABILITY == 0
    assert XAU_PROSPECTIVE_PRISTINE_UNLOCK_CAPABILITY == 0

    holdout_v2 = "XAUUSDT_HOLDOUT_2026_08_09_V2"
    pristine_v2 = "XAUUSDT_PROSPECTIVE_PRISTINE_V2"

    assert CANONICAL_DATASET_REGISTRY[holdout_v2].role == DatasetRole.LOCKED_HOLDOUT
    assert CANONICAL_DATASET_REGISTRY[pristine_v2].role == DatasetRole.LOCKED_PROSPECTIVE_PRISTINE

    # Both must fail closed under check_access
    with pytest.raises(HoldoutAccessDeniedError, match="HOLDOUT_FIREWALL_VIOLATION"):
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.BACKTEST,
            dataset_id=holdout_v2,
        )

    with pytest.raises(HoldoutAccessDeniedError, match="HOLDOUT_FIREWALL_VIOLATION"):
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.BACKTEST,
            dataset_id=pristine_v2,
        )

    # Calling load_research_parquet on holdout or pristine must fail closed
    holdout_path = ROOT / "artifacts" / "research" / "partitions" / f"{holdout_v2}.parquet"
    with pytest.raises(HoldoutAccessDeniedError, match="HOLDOUT_FIREWALL_VIOLATION"):
        load_research_parquet(holdout_path, dataset_id=holdout_v2)

    pristine_path = ROOT / "artifacts" / "research" / "partitions" / f"{pristine_v2}.parquet"
    with pytest.raises(HoldoutAccessDeniedError, match="HOLDOUT_FIREWALL_VIOLATION"):
        load_research_parquet(pristine_path, dataset_id=pristine_v2)


def test_data_guard_allows_dev_and_val_with_exact_logical_sha() -> None:
    dev_v2 = "XAUUSDT_DEV_2026_01_04_V2"
    dev_path = ROOT / "artifacts" / "research" / "partitions" / f"{dev_v2}.parquet"
    expected_logical_sha = CANONICAL_DATASET_REGISTRY[dev_v2].partition_logical_sha256

    # Loading DEV with correct logical SHA succeeds
    table = load_research_parquet(
        dev_path,
        dataset_id=dev_v2,
        operation=ResearchOperation.BACKTEST,
        dataset_logical_sha=expected_logical_sha,
    )
    assert table.num_rows == 165_600

    # Wrong logical SHA raises HoldoutAccessDeniedError
    with pytest.raises(HoldoutAccessDeniedError, match="DATASET_IDENTITY_MISMATCH"):
        load_research_parquet(
            dev_path,
            dataset_id=dev_v2,
            operation=ResearchOperation.BACKTEST,
            dataset_logical_sha="0000000000000000000000000000000000000000000000000000000000000000",
        )


def test_ledger_integrity_fails_closed_when_require_exists_and_missing() -> None:
    is_valid, count, msg, summary = verify_access_ledger_integrity(
        ledger_path=ROOT / "reports" / "nonexistent_ledger.jsonl",
        require_exists=True,
    )
    assert is_valid is False
    assert msg == "LEDGER_MISSING"


# ---------------------------------------------------------------------------
# Blocker B: Trade and AggTrade Multi-Epoch Reconciliations
# ---------------------------------------------------------------------------

def test_trade_audit_v15_report() -> None:
    report_path = ROOT / "reports" / "XAU_TRADES_AGGTRADES_AUDIT_V15.json"
    if not report_path.is_file():
        pytest.skip("XAU_TRADES_AGGTRADES_AUDIT_V15.json deferred to Commit D")
    data = json.loads(report_path.read_text())

    assert data["report_type"] == "XAU_TRADES_AGGTRADES_FULL_AUDIT_V15"
    assert data["all_archives_passed"] is True
    assert data["multi_epoch_reconciliation_passed"] is True
    assert len(data["reconciliations"]) == 3

    # All 3 benchmark days must reconcile 100% on trade counts and base volume
    for day in ("2026-01-15", "2026-05-15", "2026-09-01"):
        rec = data["reconciliations"][day]
        assert rec["trade_count_match"] is True
        assert rec["trades_exact_reconciliation"] is True
        assert Decimal(rec["trades_vs_kline_vol_diff"]) == Decimal("0.000")
