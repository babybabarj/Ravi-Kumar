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
    verify_access_ledger_integrity,
    LEDGER_PATH,
    HOLDOUT_WINDOW_START_NS,
    HOLDOUT_WINDOW_END_NS,
    HOLDOUT_UNLOCK_CAPABILITY,
)


def test_adversarial_matrix_2024_holdout_precedence() -> None:
    """Holdout timestamp intersection must strictly take precedence over ANY caller-supplied role."""
    ts_mid_2024 = int(datetime(2024, 6, 15, tzinfo=timezone.utc).timestamp() * 1e9)

    # 1. 2024 timestamps + PROSPECTIVE_FORWARD => MUST BLOCK!
    with pytest.raises(HoldoutAccessDeniedError) as exc:
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.PROSPECTIVE_VALIDATION,
            dataset_id="FORGED_PROSPECTIVE_2024",
            dataset_role=DatasetRole.PROSPECTIVE_FORWARD,
            start_ts_ns=ts_mid_2024,
            end_ts_ns=ts_mid_2024 + 3600_000_000_000,
        )
    assert "HOLDOUT_FIREWALL_VIOLATION" in str(exc.value)

    # 2. 2024 timestamps + DEVELOPMENT => MUST BLOCK!
    with pytest.raises(HoldoutAccessDeniedError) as exc:
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.BACKTEST,
            dataset_id="FORGED_DEV_2024",
            dataset_role=DatasetRole.DEVELOPMENT,
            start_ts_ns=ts_mid_2024,
            end_ts_ns=ts_mid_2024 + 3600_000_000_000,
        )
    assert "HOLDOUT_FIREWALL_VIOLATION" in str(exc.value)

    # 3. 2024 timestamps + VALIDATION => MUST BLOCK!
    with pytest.raises(HoldoutAccessDeniedError) as exc:
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.BACKTEST,
            dataset_id="FORGED_VAL_2024",
            dataset_role=DatasetRole.VALIDATION,
            start_ts_ns=ts_mid_2024,
            end_ts_ns=ts_mid_2024 + 3600_000_000_000,
        )
    assert "HOLDOUT_FIREWALL_VIOLATION" in str(exc.value)

    # 4. 2024 timestamps + SHADOW => MUST BLOCK!
    with pytest.raises(HoldoutAccessDeniedError) as exc:
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.SHADOW_EVALUATION,
            dataset_id="FORGED_SHADOW_2024",
            dataset_role=DatasetRole.SHADOW,
            start_ts_ns=ts_mid_2024,
            end_ts_ns=ts_mid_2024 + 3600_000_000_000,
        )
    assert "HOLDOUT_FIREWALL_VIOLATION" in str(exc.value)

    # 5. 2024 timestamps + PAPER => MUST BLOCK!
    with pytest.raises(HoldoutAccessDeniedError) as exc:
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.PAPER_EVALUATION,
            dataset_id="FORGED_PAPER_2024",
            dataset_role=DatasetRole.PAPER,
            start_ts_ns=ts_mid_2024,
            end_ts_ns=ts_mid_2024 + 3600_000_000_000,
        )
    assert "HOLDOUT_FIREWALL_VIOLATION" in str(exc.value)


def test_final_holdout_audit_fails_closed() -> None:
    """FINAL_HOLDOUT_AUDIT must fail closed because HOLDOUT_UNLOCK_CAPABILITY = 0."""
    assert HOLDOUT_UNLOCK_CAPABILITY == 0
    with pytest.raises(HoldoutAccessDeniedError) as exc:
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.FINAL_HOLDOUT_AUDIT,
            dataset_id="BTCUSDT_2024_HOLDOUT",
            dataset_role=DatasetRole.LOCKED_HOLDOUT,
        )
    assert "HOLDOUT_FIREWALL_VIOLATION" in str(exc.value)
    assert "HOLDOUT_UNLOCK_CAPABILITY is ZERO" in str(exc.value)


def test_unknown_provenance_fails_closed() -> None:
    """Unknown dataset identity and timestamps must NEVER default to DEVELOPMENT; must fail closed."""
    with pytest.raises(HoldoutAccessDeniedError) as exc:
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.BACKTEST,
            dataset_id="MYSTERIOUS_UNREGISTERED_DATASET",
        )
    assert "DATASET_PROVENANCE_UNKNOWN" in str(exc.value)


def test_corrupt_metadata_fails_closed(tmp_path: Path) -> None:
    """If metadata reading fails or file is corrupt, guard must fail closed (no silent continue)."""
    corrupt_file = tmp_path / "corrupt_data.parquet"
    corrupt_file.write_bytes(b"NOT_A_REAL_PARQUET_FILE_CORRUPT_BYTES")

    with pytest.raises(HoldoutAccessDeniedError) as exc:
        load_research_parquet(corrupt_file, operation=ResearchOperation.BACKTEST, dataset_id="unknown_file")
    assert "DATASET_METADATA_INVALID" in str(exc.value)


def test_dataset_identity_mismatch_fails_closed() -> None:
    """If caller claims canonical dataset_v3.1.0 but provides wrong logical SHA, access is denied."""
    with pytest.raises(HoldoutAccessDeniedError) as exc:
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.BACKTEST,
            dataset_id="dataset_v3.1.0",
            dataset_logical_sha="0000000000000000000000000000000000000000000000000000000000000000",
        )
    assert "DATASET_IDENTITY_MISMATCH" in str(exc.value)


def test_renamed_holdout_file_blocked_by_metadata(tmp_path: Path) -> None:
    """Renamed holdout file with innocent name is blocked by metadata timestamps."""
    innocent_file = tmp_path / "innocent_dev_data.parquet"
    ts_mid_2024 = int(datetime(2024, 6, 15, tzinfo=timezone.utc).timestamp() * 1e9)
    
    schema = pa.schema(
        [("ts_event_ns", pa.int64()), ("price", pa.float64())],
        metadata={
            b"dataset_role": b"PROSPECTIVE_FORWARD",  # Forged metadata claiming prospective!
            b"start_ts_ns": str(ts_mid_2024).encode(),
            b"end_ts_ns": str(ts_mid_2024 + 3600_000_000_000).encode(),
        },
    )
    table = pa.Table.from_arrays([[ts_mid_2024], [65000.0]], schema=schema)
    pq.write_table(table, innocent_file)

    with pytest.raises(HoldoutAccessDeniedError) as exc:
        load_research_parquet(innocent_file, operation=ResearchOperation.BACKTEST)
    assert "HOLDOUT_FIREWALL_VIOLATION" in str(exc.value)


def test_prospective_forward_policy_matrix(tmp_path: Path) -> None:
    """PROSPECTIVE_FORWARD data allows forward validation but strictly blocks tuning/optimization."""
    ts_2025 = int(datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp() * 1e9)

    # 1. Forward validation => ALLOWED
    allowed = ResearchDataAccessGuard.check_access(
        operation=ResearchOperation.PROSPECTIVE_VALIDATION,
        dataset_id="BTCUSDT_2025_PROSPECTIVE",
        dataset_role=DatasetRole.PROSPECTIVE_FORWARD,
        start_ts_ns=ts_2025,
        end_ts_ns=ts_2025 + 3600_000_000_000,
    )
    assert allowed is True

    # 2. Parameter tuning on 2025 => BLOCKED!
    with pytest.raises(HoldoutAccessDeniedError) as exc:
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.PARAMETER_TUNING,
            dataset_id="BTCUSDT_2025_PROSPECTIVE",
            dataset_role=DatasetRole.PROSPECTIVE_FORWARD,
            start_ts_ns=ts_2025,
            end_ts_ns=ts_2025 + 3600_000_000_000,
        )
    assert "PROSPECTIVE_TUNING_BLOCKED" in str(exc.value)

    # 3. Feature selection on 2026 => BLOCKED!
    ts_2026 = int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp() * 1e9)
    with pytest.raises(HoldoutAccessDeniedError) as exc:
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.FEATURE_SELECTION,
            dataset_id="BTCUSDT_2026_LIVE_FORWARD",
            dataset_role=DatasetRole.PROSPECTIVE_FORWARD,
            start_ts_ns=ts_2026,
            end_ts_ns=ts_2026 + 3600_000_000_000,
        )
    assert "PROSPECTIVE_TUNING_BLOCKED" in str(exc.value)

    # 4. Backtest / optimization on 2025 => BLOCKED!
    with pytest.raises(HoldoutAccessDeniedError) as exc:
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.BACKTEST,
            dataset_id="BTCUSDT_2025_PROSPECTIVE",
            dataset_role=DatasetRole.PROSPECTIVE_FORWARD,
            start_ts_ns=ts_2025,
            end_ts_ns=ts_2025 + 3600_000_000_000,
        )
    assert "PROSPECTIVE_TUNING_BLOCKED" in str(exc.value)


def test_development_and_validation_datasets_allowed() -> None:
    """Canonical 2020-2023 development and validation datasets pass cleanly."""
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


def test_access_ledger_hash_chain_integrity() -> None:
    """Verify cryptographic continuity of the access ledger hash chain and zero allowed holdout accesses."""
    ok, count, msg, summary = verify_access_ledger_integrity()
    assert ok is True, f"Hash chain integrity failed: {msg}"
    assert count > 0, "Ledger must have recorded entries"
    assert summary["allowed_holdout_accesses"] == 0, "Must have zero allowed holdout accesses"


def test_access_ledger_tamper_detection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tampering with an entry in the ledger breaks hash chain verification."""
    # Create isolated test ledger
    test_ledger = tmp_path / "test_ledger.jsonl"
    monkeypatch.setattr("btceth_os.research.data_guard.LEDGER_PATH", test_ledger)

    # Perform 3 access requests to populate ledger
    ResearchDataAccessGuard.check_access(
        operation=ResearchOperation.BACKTEST,
        dataset_id="BTCUSDT_DEV",
        dataset_role=DatasetRole.DEVELOPMENT,
        start_ts_ns=1600000000_000_000_000,
        end_ts_ns=1600003600_000_000_000,
    )
    with pytest.raises(HoldoutAccessDeniedError):
        ResearchDataAccessGuard.check_access(
            operation=ResearchOperation.HYPOTHESIS_GENERATION,
            dataset_id="BTCUSDT_2024_HOLDOUT",
            dataset_role=DatasetRole.LOCKED_HOLDOUT,
        )
    ResearchDataAccessGuard.check_access(
        operation=ResearchOperation.PROSPECTIVE_VALIDATION,
        dataset_id="BTCUSDT_2025_PROSPECTIVE",
        dataset_role=DatasetRole.PROSPECTIVE_FORWARD,
        start_ts_ns=1740000000_000_000_000,
        end_ts_ns=1740003600_000_000_000,
    )

    # Verify pristine ledger passes
    ok, count, msg, summary = verify_access_ledger_integrity()
    assert ok is True
    assert count == 3

    # Tamper with entry 2
    lines = test_ledger.read_text(encoding="utf-8").splitlines()
    tampered_entry = json.loads(lines[1])
    tampered_entry["decision"] = "ALLOWED"  # Tamper with recorded decision!
    lines[1] = json.dumps(tampered_entry)
    test_ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Re-verifying must detect tampering!
    ok_tampered, count_tampered, msg_tampered, _ = verify_access_ledger_integrity()
    assert ok_tampered is False
    assert "TAMPER_DETECTED" in msg_tampered
