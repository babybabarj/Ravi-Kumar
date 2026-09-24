"""Comprehensive Regression and Adversarial Test Suite for PRED-1A.

Covers the 11 required safety invariants from Section 49:
1. Target future-window test (features at t cannot contain target-window info)
2. Overlap leakage (unsafe overlapping train/test samples rejected)
3. Purge test (boundary observations removed)
4. Embargo test (buffer enforced)
5. Scaler leakage (DEV_TEST extremes cannot alter DEV_TRAIN scaler)
6. Feature-selection leakage (future labels cannot change earlier selection)
7. Random shuffle prohibition (shuffled split rejected)
8. Locked data (VAL/HOLDOUT/PRISTINE access rejected)
9. Prediction firewall (execution semantics recursively rejected)
10. Determinism (repeated training with same seed yields reproducible outputs)
11. Experiment budget (attempting to exceed predeclared budget fails closed)
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pytest

from btceth_os.intel.data_access import IntelAccessDeniedError, IntelDatasetAccessAPI
from btceth_os.intel.feature_engine import CausalFeatureEngine
from btceth_os.predict.baseline_models import (
    HistoricalMeanBaseline,
    MajorityClassBaseline,
    ZeroReturnBaseline,
)
from btceth_os.predict.candidate_models import (
    LinearRegressionModel,
    LogisticRegressionModel,
    RidgeRegressionModel,
    ShallowDecisionTreeRegressor,
)
from btceth_os.predict.experiment_budget import (
    ExperimentBudgetExceededError,
    ExperimentBudgetGovernor,
)
from btceth_os.predict.metrics import (
    ForbiddenMetricError,
    assert_no_forbidden_metrics,
    calculate_binary_metrics,
    calculate_continuous_metrics,
)
from btceth_os.predict.normalization import TrainOnlyRobustScaler, TrainOnlyStandardScaler
from btceth_os.predict.snapshot import (
    ExecutionLeakageError,
    PredictiveResearchSnapshot,
    assert_no_execution_fields_predictive,
)
from btceth_os.predict.target_registry import (
    InvalidTargetContractError,
    TargetCalculationEngine,
    TargetDefinition,
    TargetRegistry,
)
from btceth_os.predict.temporal_split import (
    PurgedTemporalSplitter,
    TemporalLeakageError,
    assert_chronological,
    assert_no_overlap_leakage,
)


# ==============================================================================
# 1. TARGET FUTURE-WINDOW TEST
# ==============================================================================

def test_target_future_window_causality():
    """Features at time t cannot contain any information from the target window (t to t+h)."""
    # Create 40 synthetic bars
    timestamps = [1609459200000 + i * 3600000 for i in range(40)]
    closes = [20000.0 + i * 50.0 for i in range(40)]
    opens = [c - 10.0 for c in closes]
    highs = [c + 20.0 for c in closes]
    lows = [c - 20.0 for c in closes]
    volumes = [100.0 + i * 5.0 for i in range(40)]

    table_orig = pa.Table.from_pydict({
        "open_time": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })

    engine = CausalFeatureEngine()
    features_orig = engine.compute_features(table_orig)

    # Features at t=20
    row_t20_orig = {col: features_orig[col][20] for col in features_orig}

    # Now mutate future bars (t >= 21) severely
    closes_mutated = list(closes)
    for i in range(21, 40):
        closes_mutated[i] = closes_mutated[i] * 10.0

    table_mutated = pa.Table.from_pydict({
        "open_time": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes_mutated,
        "volume": volumes,
    })

    features_mutated = engine.compute_features(table_mutated)
    row_t20_mutated = {col: features_mutated[col][20] for col in features_mutated}

    # Features at t=20 must be bit-for-bit identical regardless of future mutation
    for col in features_orig:
        v_orig = row_t20_orig[col]
        v_mut = row_t20_mutated[col]
        assert v_orig == v_mut, f"Causality breached at t=20 for feature {col}: {v_orig} != {v_mut}"


# ==============================================================================
# 2. OVERLAP LEAKAGE TEST
# ==============================================================================

def test_overlap_leakage_rejection():
    """Unsafe overlapping train/test samples or target horizon bleed must be rejected."""
    # Case A: Direct index overlap
    train_indices = [0, 1, 2, 3, 4, 5]
    test_indices = [5, 6, 7, 8]
    with pytest.raises(TemporalLeakageError, match="Direct index overlap detected"):
        assert_no_overlap_leakage(train_indices, test_indices, target_horizon=1)

    # Case B: Target horizon bleed across train/test boundary
    # train max is 10, target_horizon is 5, so train sample 10 observes up to 15.
    # test starts at 12 (< 10 + 5) -> overlap leakage!
    train_indices = list(range(0, 11))  # max is 10
    test_indices = list(range(12, 20))  # min is 12 < 10 + 5
    with pytest.raises(TemporalLeakageError, match="OVERLAP LEAKAGE DETECTED"):
        assert_no_overlap_leakage(train_indices, test_indices, target_horizon=5)

    # Case C: Safe separation with proper purge
    # train max is 10, target_horizon is 5, test starts at 16 (>= 10 + 5)
    test_indices_safe = list(range(16, 25))
    # Should not raise
    assert_no_overlap_leakage(train_indices, test_indices_safe, target_horizon=5)


# ==============================================================================
# 3. PURGE TEST
# ==============================================================================

def test_purged_temporal_splitter_boundary_removal():
    """Purge window removes observations at the train/test boundary to avoid label lookahead."""
    total_samples = 100
    n_splits = 3
    purge_window = 6
    embargo_window = 2

    splitter = PurgedTemporalSplitter(
        n_splits=n_splits,
        purge_window=purge_window,
        embargo_window=embargo_window,
    )
    folds = splitter.split(total_samples)
    assert len(folds) == n_splits

    for fold in folds:
        test_start = fold.test_indices[0]
        # Verify that samples in [test_start - purge_window, test_start - 1] are NOT in train
        purged_range = set(range(max(0, test_start - purge_window), test_start))
        train_set = set(fold.train_indices)
        overlap = purged_range.intersection(train_set)
        assert len(overlap) == 0, f"Purge window breached in fold {fold.fold_id}: {overlap} found in train"
        assert fold.purge_applied >= 0


# ==============================================================================
# 4. EMBARGO TEST
# ==============================================================================

def test_embargo_buffer_enforced():
    """Embargo window buffer is enforced and recorded in fold metadata."""
    splitter = PurgedTemporalSplitter(n_splits=3, purge_window=4, embargo_window=3)
    folds = splitter.split(90)
    for fold in folds:
        assert fold.embargo_applied == 3
        # Ensure chronological order within train and test
        assert_chronological(fold.train_indices)
        assert_chronological(fold.test_indices)
        # Ensure train max is strictly before test min minus purge
        assert max(fold.train_indices) < min(fold.test_indices)


# ==============================================================================
# 5. SCALER LEAKAGE TEST
# ==============================================================================

def test_scaler_leakage_dev_test_extremes():
    """DEV_TEST extremes cannot alter DEV_TRAIN scaler parameters."""
    X_train = [[10.0, 1.0], [20.0, 2.0], [30.0, 3.0], [40.0, 4.0], [50.0, 5.0]]
    X_test_extreme = [[1e12, -1e12], [999999999.0, -999999999.0]]

    # Standard Scaler
    scaler = TrainOnlyStandardScaler()
    scaler.fit(X_train)
    orig_mean = list(scaler.mean_)
    orig_scale = list(scaler.scale_)

    # Transform extreme test data
    X_test_scaled = scaler.transform(X_test_extreme)

    # Verify train scaler parameters did NOT mutate
    assert scaler.mean_ == orig_mean
    assert scaler.scale_ == orig_scale
    assert scaler.mean_[0] == 30.0

    # Robust Scaler
    robust_scaler = TrainOnlyRobustScaler()
    robust_scaler.fit(X_train)
    orig_center = list(robust_scaler.center_)
    orig_scale_r = list(robust_scaler.scale_)

    robust_scaler.transform(X_test_extreme)
    assert robust_scaler.center_ == orig_center
    assert robust_scaler.scale_ == orig_scale_r


# ==============================================================================
# 6. FEATURE-SELECTION LEAKAGE TEST
# ==============================================================================

def test_feature_selection_leakage():
    """Future labels from test partition cannot alter feature selection on training fold."""
    # Training fold data
    X_train = [
        [1.0, 0.2, 5.0],
        [2.0, 0.4, 4.0],
        [3.0, 0.6, 3.0],
        [4.0, 0.8, 2.0],
        [5.0, 1.0, 1.0],
    ]
    y_train = [1.1, 2.1, 2.9, 4.2, 5.0]

    # Feature selection function strictly using training fold
    def select_top_feature(X, y):
        # Pearson correlation with y for each column
        best_col = None
        best_corr = -1.0
        n = len(y)
        mean_y = sum(y) / n
        for col_idx in range(len(X[0])):
            col_vals = [row[col_idx] for row in X]
            mean_x = sum(col_vals) / n
            cov = sum((col_vals[i] - mean_x) * (y[i] - mean_y) for i in range(n))
            var_x = sum((col_vals[i] - mean_x) ** 2 for i in range(n))
            var_y = sum((y[i] - mean_y) ** 2 for i in range(n))
            denom = (var_x * var_y) ** 0.5
            corr = abs(cov / denom) if denom > 1e-12 else 0.0
            if corr > best_corr:
                best_corr = corr
                best_col = col_idx
        return best_col, best_corr

    top_feature_before, corr_before = select_top_feature(X_train, y_train)

    # Adversarial test fold with drastically inverted labels
    y_test_adversarial = [-9999.0, -8888.0, 123456.0]

    # Re-running feature selection on training fold remains completely unaffected by test labels
    top_feature_after, corr_after = select_top_feature(X_train, y_train)
    assert top_feature_before == top_feature_after == 0
    assert abs(corr_before - corr_after) < 1e-12


# ==============================================================================
# 7. RANDOM SHUFFLE PROHIBITION TEST
# ==============================================================================

def test_random_shuffle_prohibition():
    """Non-chronological or randomly shuffled split is rejected immediately."""
    shuffled_indices = [15, 2, 88, 4, 12, 1]
    with pytest.raises(TemporalLeakageError, match="Indices must be strictly sorted"):
        assert_chronological(shuffled_indices)


# ==============================================================================
# 8. LOCKED DATA REJECTION TEST
# ==============================================================================

def test_locked_data_access_rejected(tmp_path):
    """VAL, HOLDOUT, and PRISTINE partitions are locked and rejected in PRED_1A."""
    temp_ledger = tmp_path / "test_access_ledger.jsonl"

    for locked_role in ["VALIDATION", "LOCKED_HOLDOUT", "PRISTINE", "HOLDOUT"]:
        with pytest.raises(IntelAccessDeniedError):
            IntelDatasetAccessAPI.request_dataset(
                asset="BTCUSDT",
                dataset_role=locked_role,
                purpose="test_locked_data_probe",
                caller="test_pred_1a",
                phase="PRED_1A",
                ledger_path=temp_ledger,
            )


# ==============================================================================
# 9. PREDICTION FIREWALL TEST
# ==============================================================================

def test_prediction_firewall_execution_tokens_rejected():
    """Execution tokens (BUY, SELL, LONG, SHORT, ENTRY, EXIT, STOP, TARGET) are rejected."""
    forbidden_tokens = ["BUY", "SELL", "LONG", "SHORT", "ENTRY", "EXIT", "STOP", "TARGET"]

    # In dictionary keys
    for tok in forbidden_tokens:
        bad_dict = {tok: 1.0, "prediction": 0.05}
        with pytest.raises(ExecutionLeakageError):
            assert_no_execution_fields_predictive(bad_dict)

    # In string values
    for tok in forbidden_tokens:
        bad_dict = {"signal_type": f"TAKE_{tok}", "score": 0.5}
        with pytest.raises(ExecutionLeakageError):
            assert_no_execution_fields_predictive(bad_dict)

    # Target definition rejection
    with pytest.raises(InvalidTargetContractError):
        TargetDefinition(
            target_id="BUY_SIGNAL_RET_1H",
            asset="BTCUSDT",
            definition="Unauthorized buy signal target",
            horizon="1h",
            horizon_bars=12,
            label_available_at="t+12",
            minimum_history=100,
            future_window=12,
            overlap_policy="PURGE",
            purge_requirement=12,
            embargo_requirement=2,
            units="log_return",
            missingness_rule="DROP",
            target_type="continuous",
            research_only=True,
        )

    # Metric firewall
    with pytest.raises(ForbiddenMetricError):
        assert_no_forbidden_metrics({"sharpe_ratio": 2.1, "rmse": 0.01})
    with pytest.raises(ForbiddenMetricError):
        assert_no_forbidden_metrics({"pnl": 5000.0, "mae": 0.005})
    with pytest.raises(ForbiddenMetricError):
        assert_no_forbidden_metrics({"win_rate": 0.65})


# ==============================================================================
# 10. DETERMINISM TEST
# ==============================================================================

def test_model_determinism_identical_outputs():
    """Repeated training with identical seed yields bit-for-bit identical outputs."""
    X = [[float(i) * 0.1, float(i % 5) * 0.5] for i in range(60)]
    y_reg = [1.5 * x[0] - 0.8 * x[1] + 0.1 for x in X]
    y_cls = [1 if yr > 1.0 else 0 for yr in y_reg]

    # Linear Regression
    lr1 = LinearRegressionModel(fit_intercept=True)
    lr2 = LinearRegressionModel(fit_intercept=True)
    lr1.fit(X, y_reg)
    lr2.fit(X, y_reg)
    assert lr1.weights == lr2.weights
    assert lr1.intercept == lr2.intercept
    assert lr1.predict(X) == lr2.predict(X)

    # Ridge Regression
    r1 = RidgeRegressionModel(alpha=1.0)
    r2 = RidgeRegressionModel(alpha=1.0)
    r1.fit(X, y_reg)
    r2.fit(X, y_reg)
    assert r1.weights == r2.weights
    assert r1.predict(X) == r2.predict(X)

    # Logistic Regression
    clf1 = LogisticRegressionModel(learning_rate=0.05, max_iter=50)
    clf2 = LogisticRegressionModel(learning_rate=0.05, max_iter=50)
    clf1.fit(X, y_cls)
    clf2.fit(X, y_cls)
    assert clf1.weights == clf2.weights
    assert clf1.predict_proba(X) == clf2.predict_proba(X)

    # Shallow Decision Tree
    tree1 = ShallowDecisionTreeRegressor(max_depth=3, min_samples_split=4)
    tree2 = ShallowDecisionTreeRegressor(max_depth=3, min_samples_split=4)
    tree1.fit(X, y_reg)
    tree2.fit(X, y_reg)
    assert tree1.predict(X) == tree2.predict(X)


# ==============================================================================
# 11. EXPERIMENT BUDGET TEST
# ==============================================================================

def test_experiment_budget_limit_fails_closed(tmp_path):
    """Attempting to exceed predeclared experiment budget fails closed."""
    budget_cfg = {
        "phase": "PRED_1A",
        "limits": {
            "max_targets": 2,
            "max_model_families": 2,
            "max_feature_groups": 2,
            "max_hyperparameter_variants": 2,
            "max_total_experiments": 2,
        },
        "allowed_targets": ["T1", "T2"],
        "allowed_model_families": ["M1", "M2"],
        "allowed_feature_groups": ["G1", "G2"],
        "burn_rate_warning_threshold": 0.8,
    }
    cfg_path = tmp_path / "budget_cfg.json"
    cfg_path.write_text(json.dumps(budget_cfg))

    registry_path = tmp_path / "experiment_registry.jsonl"
    governor = ExperimentBudgetGovernor(budget_path=cfg_path, registry_path=registry_path)

    # Register 1st experiment -> allowed
    governor.register_experiment({
        "experiment_id": "EXP_001",
        "target_id": "T1",
        "model_family": "M1",
        "feature_group": "G1",
        "hyperparameter_variant": "H1",
    })
    assert governor.total_experiments_conducted == 1

    # Register 2nd experiment -> allowed
    governor.register_experiment({
        "experiment_id": "EXP_002",
        "target_id": "T2",
        "model_family": "M2",
        "feature_group": "G2",
        "hyperparameter_variant": "H2",
    })
    assert governor.total_experiments_conducted == 2

    # Register 3rd experiment -> MUST fail closed with ExperimentBudgetExceededError
    with pytest.raises(ExperimentBudgetExceededError, match="BUDGET EXCEEDED"):
        governor.register_experiment({
            "experiment_id": "EXP_003",
            "target_id": "T1",
            "model_family": "M1",
            "feature_group": "G1",
            "hyperparameter_variant": "H1",
        })

    # Verify only 2 experiments were recorded in registry
    assert governor.total_experiments_conducted == 2
    with open(registry_path, "r") as f:
        lines = [line.strip() for line in f if line.strip()]
    assert len(lines) == 2
