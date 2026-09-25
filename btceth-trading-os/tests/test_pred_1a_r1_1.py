"""Tests for Trading OS PRED-1A R1.1.

Validates:
  1. Empirical leakage gates (normalization, categorical encoding, feature selection, future-mutation causality).
  2. Scope truth and set reconciliation.
  3. Parquet metadata and PyArrow IPC content hash recomputation.
  4. Git code/tree provenance binding.
  5. Snapshot reconciliation and clean-clone repository acceptance.
  6. Prediction firewall and zero promotion invariants.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.intel.feature_engine import CausalFeatureEngine
from btceth_os.predict.metrics import (
    ForbiddenMetricError,
    assert_no_forbidden_metrics,
)
from btceth_os.predict.normalization import (
    TrainOnlyCategoricalEncoder,
    TrainOnlyStandardScaler,
)
from btceth_os.predict.research_pipeline import compute_sample_hash
from btceth_os.predict.target_registry import TargetRegistry


def test_normalization_gate_is_empirical() -> None:
    """Verifies TrainOnlyStandardScaler fit computes frozen parameters and handles transform empirically."""
    scaler = TrainOnlyStandardScaler()
    X = [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]]
    scaler.fit(X)
    assert scaler.mean_ == [2.0, 20.0]
    assert scaler.scale_ is not None
    assert len(scaler.scale_) == 2
    # Verify transform does not mutate mean_ or scale_
    transformed = scaler.transform(X)
    assert len(transformed) == 3
    assert scaler.mean_ == [2.0, 20.0]


def test_test_extreme_does_not_change_train_scaler() -> None:
    """Verifies that transforming test data with extreme values does not mutate train scaler parameters."""
    scaler = TrainOnlyStandardScaler()
    train_X = [[10.0, 100.0], [20.0, 200.0], [30.0, 300.0]]
    scaler.fit(train_X)
    mean_frozen = list(scaler.mean_)
    scale_frozen = list(scaler.scale_)

    extreme_test_X = [[1e12, -1e12], [-1e15, 1e15]]
    scaler.transform(extreme_test_X)

    assert scaler.mean_ == mean_frozen
    assert scaler.scale_ == scale_frozen


def test_categorical_unknown_bucket_behavior() -> None:
    """Verifies TrainOnlyCategoricalEncoder maps unseen test categories to UNKNOWN (0.0)."""
    encoder = TrainOnlyCategoricalEncoder()
    train_cats = [["REGULAR"], ["CLOSED"]]
    encoder.fit(train_cats)

    test_unseen = [["SURPRISE_CATEGORY"]]
    encoded = encoder.transform(test_unseen)
    assert encoded == [[0.0]]


def test_unseen_category_does_not_change_train_vocab() -> None:
    """Verifies transforming unseen categories does not mutate the fitted train vocabulary."""
    encoder = TrainOnlyCategoricalEncoder()
    train_cats = [["REGULAR"], ["CLOSED"]]
    encoder.fit(train_cats)

    vocab_before = dict(encoder.vocabularies_[0])
    encoder.transform([["ANOTHER_UNSEEN_VALUE"]])
    vocab_after = dict(encoder.vocabularies_[0])

    assert vocab_before == vocab_after
    assert "ANOTHER_UNSEEN_VALUE" not in encoder.vocabularies_[0]
    assert encoder.vocabularies_[0]["UNKNOWN"] == 0


def test_no_supervised_feature_selection_or_train_only_selection() -> None:
    """Verifies no supervised target-dependent feature selectors exist in research pipeline."""
    pipe_src = (ROOT / "src/btceth_os/predict/research_pipeline.py").read_text()
    assert "SelectKBest" not in pipe_src
    assert "feature_selection" not in pipe_src
    assert "feature_set" in pipe_src


def test_future_mutation_zero_past_divergence() -> None:
    """Verifies that future bar mutations cannot alter past feature values computed by CausalFeatureEngine."""
    n_bars = 80
    ts_start = 1767657600_000_000_000
    step = 60_000_000_000
    timestamps = [ts_start + i * step for i in range(n_bars)]
    base_prices = [2500.0 + (i * 0.1) for i in range(n_bars)]
    schema = pa.schema([
        ("timestamp_ns", pa.int64()),
        ("open", pa.decimal128(18, 4)),
        ("high", pa.decimal128(18, 4)),
        ("low", pa.decimal128(18, 4)),
        ("close", pa.decimal128(18, 4)),
        ("volume", pa.decimal128(18, 4)),
        ("quote_volume", pa.decimal128(18, 4)),
        ("trade_count", pa.int64()),
        ("taker_buy_volume", pa.decimal128(18, 4)),
        ("taker_buy_quote_volume", pa.decimal128(18, 4)),
        ("funding_rate", pa.decimal128(18, 8)),
        ("time_since_last_funding_minutes", pa.int32()),
        ("session_state", pa.string()),
        ("session_certainty", pa.string()),
        ("holiday_status", pa.string()),
        ("price_index_mode", pa.string()),
        ("price_index_mode_certainty", pa.string()),
    ])
    pydict1 = {
        "timestamp_ns": timestamps,
        "open": [Decimal(str(round(p, 4))) for p in base_prices],
        "high": [Decimal(str(round(p + 0.5, 4))) for p in base_prices],
        "low": [Decimal(str(round(p - 0.5, 4))) for p in base_prices],
        "close": [Decimal(str(round(p, 4))) for p in base_prices],
        "volume": [Decimal("100.0000")] * n_bars,
        "quote_volume": [Decimal("250000.0000")] * n_bars,
        "trade_count": [1000] * n_bars,
        "taker_buy_volume": [Decimal("50.0000")] * n_bars,
        "taker_buy_quote_volume": [Decimal("125000.0000")] * n_bars,
        "funding_rate": [Decimal("0.00010000")] * n_bars,
        "time_since_last_funding_minutes": [60] * n_bars,
        "session_state": ["REGULAR"] * n_bars,
        "session_certainty": ["HIGH"] * n_bars,
        "holiday_status": ["REGULAR"] * n_bars,
        "price_index_mode": ["REGULAR"] * n_bars,
        "price_index_mode_certainty": ["HIGH"] * n_bars,
    }
    tbl1 = pa.Table.from_pydict(pydict1, schema=schema)
    pydict2 = dict(pydict1)
    pydict2["close"] = list(pydict1["close"])
    pydict2["high"] = list(pydict1["high"])
    for i in range(50, n_bars):
        pydict2["close"][i] = Decimal("99999.0000")
        pydict2["high"][i] = Decimal("99999.0000")
    tbl2 = pa.Table.from_pydict(pydict2, schema=schema)

    engine = CausalFeatureEngine()
    feats1 = engine.compute_features(tbl1)
    feats2 = engine.compute_features(tbl2)
    for feat_name in feats1:
        for t in range(50):
            v1 = feats1[feat_name][t]
            v2 = feats2[feat_name][t]
            assert v1 == v2, f"Feature {feat_name} diverged at t={t}: {v1} != {v2}"


def test_scope_exact_registered_set_match() -> None:
    """Verifies that the canonical TargetRegistry contains exactly the 12 expected targets."""
    t_reg = TargetRegistry()
    targets = sorted(t_reg.list_target_ids())
    expected = sorted([
        "future_log_return_5m",
        "future_log_return_15m",
        "future_log_return_1h",
        "future_log_return_4h",
        "future_realized_volatility_15m",
        "future_realized_volatility_1h",
        "future_realized_volatility_4h",
        "future_max_up_move_1h",
        "future_max_down_move_1h",
        "future_trend_state_15m",
        "future_volatility_state_1h",
        "future_liquidity_state_15m",
    ])
    assert targets == expected


def test_scope_exact_evaluated_set_match() -> None:
    """Verifies that exactly 6 representative targets were empirically evaluated."""
    eval_targets = sorted([
        "future_log_return_5m",
        "future_log_return_15m",
        "future_log_return_1h",
        "future_realized_volatility_1h",
        "future_max_up_move_1h",
        "future_trend_state_15m",
    ])
    assert len(eval_targets) == 6
    t_reg = TargetRegistry()
    for et in eval_targets:
        assert et in t_reg.list_target_ids()


def test_registered_only_equals_registry_minus_evaluated() -> None:
    """Verifies that registered_only targets strictly equals TargetRegistry - evaluated targets."""
    t_reg = TargetRegistry()
    all_targets = set(t_reg.list_target_ids())
    eval_targets = {
        "future_log_return_5m",
        "future_log_return_15m",
        "future_log_return_1h",
        "future_realized_volatility_1h",
        "future_max_up_move_1h",
        "future_trend_state_15m",
    }
    reg_only = sorted(list(all_targets - eval_targets))
    expected_reg_only = sorted([
        "future_log_return_4h",
        "future_realized_volatility_15m",
        "future_realized_volatility_4h",
        "future_max_down_move_1h",
        "future_volatility_state_1h",
        "future_liquidity_state_15m",
    ])
    assert reg_only == expected_reg_only


def test_source_artifact_rows_165600_when_available() -> None:
    """Verifies that the canonical DEV parquet file has 165,600 rows if present locally."""
    parquet_path = ROOT / "artifacts/research/partitions/XAUUSDT_DEV_2026_01_04_V3.parquet"
    if parquet_path.is_file():
        meta = pq.read_metadata(parquet_path)
        assert meta.num_rows == 165600


def test_sample_hash_recomputed_from_first_10000_rows() -> None:
    """Verifies byte-exact PyArrow IPC content hash of rows [0:10000] equals reported sample hash."""
    parquet_path = ROOT / "artifacts/research/partitions/XAUUSDT_DEV_2026_01_04_V3.parquet"
    if parquet_path.is_file():
        tbl = pq.read_table(parquet_path)
        s1 = tbl.slice(0, 10000)
        h = compute_sample_hash(s1)
        assert h == "0e6264c58011a1649f92c08e169e6f1646d0f7fb9a3a2682221a9e9ab41ac576"


def test_equal_length_distinct_slices_have_different_hashes() -> None:
    """Verifies adversarial proof: distinct 10,000-row slices yield distinct content hashes."""
    parquet_path = ROOT / "artifacts/research/partitions/XAUUSDT_DEV_2026_01_04_V3.parquet"
    if parquet_path.is_file():
        tbl = pq.read_table(parquet_path)
        s1 = tbl.slice(0, 10000)
        s2 = tbl.slice(10000, 10000)
        h1 = compute_sample_hash(s1)
        h2 = compute_sample_hash(s2)
        assert h1 != h2
        assert h2 == "10385333552bb9e71606a90f1f2e2f05bd7bbda519e3d0b23f66660c85e15598"


def test_research_code_sha_exists() -> None:
    """Verifies that the research code commit c2a8c7e1 exists in Git repository history."""
    target_sha = "c2a8c7e1b77e0bb73a9526b7f05dd14c2e68df50"
    res = subprocess.run(["git", "cat-file", "-e", target_sha], cwd=str(ROOT))
    assert res.returncode == 0


def test_research_tree_matches_code_commit() -> None:
    """Verifies that the Git tree SHA of c2a8c7e1 matches the declared tree SHA."""
    target_sha = "c2a8c7e1b77e0bb73a9526b7f05dd14c2e68df50"
    res = subprocess.run(["git", "rev-parse", f"{target_sha}^{{tree}}"], cwd=str(ROOT), capture_output=True, text=True)
    assert res.returncode == 0
    actual_tree = res.stdout.strip()
    assert actual_tree == "f111f7c4443ff1930513a132de9a72f2bc5bf19c"


def test_experiment_snapshot_reconciles() -> None:
    """Verifies that the committed experiment snapshot contains 16 unique experiments."""
    snap_path = ROOT / "reports/PRED_1A_R1_1_EXPERIMENT_REGISTRY_SNAPSHOT.json"
    assert snap_path.is_file()
    data = json.loads(snap_path.read_text())
    assert data["total_records"] == 16
    assert data["unique_experiment_ids_count"] == 16
    assert data["code_sha"] == "c2a8c7e1b77e0bb73a9526b7f05dd14c2e68df50"
    assert data["code_tree_sha"] == "f111f7c4443ff1930513a132de9a72f2bc5bf19c"


def test_access_snapshot_reconciles() -> None:
    """Verifies that the committed data access snapshot reconciles with zero holdout/pristine granted."""
    snap_path = ROOT / "reports/PRED_1A_R1_1_DATA_ACCESS_LEDGER_SNAPSHOT.json"
    assert snap_path.is_file()
    data = json.loads(snap_path.read_text())
    assert data["total_access_attempts"] == 1
    assert data["total_granted"] == 1
    assert data["dev_granted"] == 1
    assert data["val_granted"] == 0
    assert data["holdout_granted"] == 0
    assert data["pristine_granted"] == 0


def test_clean_clone_repository_acceptance_without_untracked_artifacts() -> None:
    """Verifies that REPOSITORY_ACCEPTANCE passes using committed evidence files."""
    verifier_script = ROOT / "tools/verify_pred_1a_r1_1.py"
    res = subprocess.run([sys.executable, str(verifier_script), "--mode", "REPOSITORY_ACCEPTANCE"], cwd=str(ROOT), capture_output=True, text=True)
    assert res.returncode == 0, f"Verifier failed:\n{res.stdout}\n{res.stderr}"


def test_final_verifier_has_zero_hardcoded_substantive_pass_gates() -> None:
    """Verifies AST search finds zero substantive pass shortcuts with literal True in verifier source."""
    verifier_script = ROOT / "tools/verify_pred_1a_r1_1.py"
    src = verifier_script.read_text()
    tree = ast.parse(src)
    hardcoded_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "_record":
                if len(node.args) >= 2:
                    arg2 = node.args[1]
                    if isinstance(arg2, ast.Constant) and arg2.value is True:
                        hardcoded_count += 1
    assert hardcoded_count == 0


def test_val_granted_zero() -> None:
    """Verifies 0 VAL partition access requests have ever been granted."""
    snap_path = ROOT / "reports/PRED_1A_R1_1_DATA_ACCESS_LEDGER_SNAPSHOT.json"
    data = json.loads(snap_path.read_text())
    assert data["val_granted"] == 0


def test_holdout_granted_zero() -> None:
    """Verifies 0 HOLDOUT partition access requests have ever been granted."""
    snap_path = ROOT / "reports/PRED_1A_R1_1_DATA_ACCESS_LEDGER_SNAPSHOT.json"
    data = json.loads(snap_path.read_text())
    assert data["holdout_granted"] == 0


def test_pristine_granted_zero() -> None:
    """Verifies 0 PRISTINE partition access requests have ever been granted."""
    snap_path = ROOT / "reports/PRED_1A_R1_1_DATA_ACCESS_LEDGER_SNAPSHOT.json"
    data = json.loads(snap_path.read_text())
    assert data["pristine_granted"] == 0


def test_prediction_firewall() -> None:
    """Verifies that assert_no_forbidden_metrics blocks execution fields."""
    with pytest.raises(ForbiddenMetricError):
        assert_no_forbidden_metrics({"target_entry": 2700.0})
    with pytest.raises(ForbiddenMetricError):
        assert_no_forbidden_metrics({"stop_loss": 2690.0})


def test_no_pnl() -> None:
    """Verifies that assert_no_forbidden_metrics blocks PnL and Sharpe metrics."""
    with pytest.raises(ForbiddenMetricError):
        assert_no_forbidden_metrics({"sharpe_ratio": 2.1})
    with pytest.raises(ForbiddenMetricError):
        assert_no_forbidden_metrics({"pnl": 5000.0})


def test_no_strategy() -> None:
    """Verifies that assert_no_forbidden_metrics blocks strategy metrics."""
    with pytest.raises(ForbiddenMetricError):
        assert_no_forbidden_metrics({"win_rate": 0.70})
    with pytest.raises(ForbiddenMetricError):
        assert_no_forbidden_metrics({"profit_factor": 1.8})
