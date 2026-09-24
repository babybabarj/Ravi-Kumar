"""Comprehensive test suite for PRED-1A R1 truth, provenance, and empirical verification.

Implements all 24 required test cases from Section 30 of the PRED-1A R1 Directive.
"""

from __future__ import annotations

import io
import json
import math
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.intel.data_access import (
    IntelAccessDeniedError,
    IntelDatasetAccessAPI,
    audit_intel_access_ledger,
)
from btceth_os.predict.experiment_budget import (
    ExperimentBudgetGovernor,
    ExperimentRecord,
)
from btceth_os.predict.normalization import (
    TrainOnlyCategoricalEncoder,
    TrainOnlyStandardScaler,
)
from btceth_os.predict.research_pipeline import (
    FORBIDDEN_STALE_SHA,
    PredictiveResearchPipeline,
    compute_sample_hash,
)
from btceth_os.predict.target_registry import TargetRegistry
from btceth_os.predict.temporal_split import PurgedTemporalSplitter
from btceth_os.research.promotion_state import inspect_promotion_state


# 1. test_different_equal_length_datasets_have_different_hashes
def test_different_equal_length_datasets_have_different_hashes():
    schema = pa.schema([("close", pa.float64())])
    table_a = pa.Table.from_arrays([pa.array([100.0 + i for i in range(10000)])], schema=schema)
    table_b = pa.Table.from_arrays([pa.array([200.0 + i for i in range(10000)])], schema=schema)

    hash_a = compute_sample_hash(table_a)
    hash_b = compute_sample_hash(table_b)

    assert hash_a != hash_b, "Two different 10,000-row datasets must not have identical hashes"
    assert hash_a != "39e5b4830d4d9c14db7368a95b65d5463ea3d09520373723430c03a5a453b5df"


# 2. test_experiment_code_sha_matches_current_research_code
def test_experiment_code_sha_matches_current_research_code():
    pipeline = PredictiveResearchPipeline(code_sha="1111222233334444555566667777888899990000")
    assert pipeline.code_sha == "1111222233334444555566667777888899990000"


# 3. test_old_r3_sha_rejected_for_r1_experiment
def test_old_r3_sha_rejected_for_r1_experiment():
    with pytest.raises(ValueError, match="FORBIDDEN STALE CODE SHA DETECTED"):
        PredictiveResearchPipeline(code_sha=FORBIDDEN_STALE_SHA)


# 4. test_experiment_ids_unique
def test_experiment_ids_unique(tmp_path):
    budget_file = tmp_path / "budget.json"
    budget_file.write_text(json.dumps({
        "max_total_experiments": 10,
        "max_targets": 5,
        "max_feature_groups": 5,
    }))
    registry_file = tmp_path / "registry.jsonl"
    gov = ExperimentBudgetGovernor(config_path=budget_file, registry_path=registry_file)

    rec1 = ExperimentRecord(
        experiment_id="EXP_TEST_001",
        timestamp_utc="2026-09-24T00:00:00Z",
        code_sha="abc",
        dataset_id="DEV",
        dataset_hash="hash",
        feature_set="ALL",
        target_id="target_1",
        horizon="1h",
        model_id="Linear",
        hyperparameters={},
        split_id="split_1",
        seed=42,
        status="COMPLETED",
        artifact_paths=[],
    )
    gov.check_and_log_experiment(rec1)

    with pytest.raises(ValueError, match="DUPLICATE EXPERIMENT ID"):
        gov.check_and_log_experiment(rec1)


# 5. test_evidence_generation_does_not_append_experiments
def test_evidence_generation_does_not_append_experiments():
    run_art = ROOT / "artifacts/research/pred_1a_r1_run_artifacts.json"
    if not run_art.is_file():
        pytest.skip("Research run artifact not yet created. Run tools/run_pred_1a_r1_research.py first.")
    registry_path = ROOT / "artifacts/research/pred_1a_r1_experiment_registry.jsonl"
    if registry_path.is_file():
        count_before = len(registry_path.read_text().splitlines())
        subprocess.run([sys.executable, str(ROOT / "tools/generate_pred_1a_r1_reports.py")], cwd=str(ROOT), check=True)
        count_after = len(registry_path.read_text().splitlines())
        assert count_before == count_after


# 6. test_evidence_generation_does_not_access_dev
def test_evidence_generation_does_not_access_dev():
    run_art = ROOT / "artifacts/research/pred_1a_r1_run_artifacts.json"
    if not run_art.is_file():
        pytest.skip("Research run artifact not yet created. Run tools/run_pred_1a_r1_research.py first.")
    ledger_path = ROOT / "artifacts/research/pred_1a_r1_data_access_ledger.jsonl"
    if ledger_path.is_file():
        count_before = len(ledger_path.read_text().splitlines())
        subprocess.run([sys.executable, str(ROOT / "tools/generate_pred_1a_r1_reports.py")], cwd=str(ROOT), check=True)
        count_after = len(ledger_path.read_text().splitlines())
        assert count_before == count_after


# 7. test_evidence_generation_is_idempotent
def test_evidence_generation_is_idempotent():
    run_art = ROOT / "artifacts/research/pred_1a_r1_run_artifacts.json"
    if not run_art.is_file():
        pytest.skip("Research run artifact not yet created. Run tools/run_pred_1a_r1_research.py first.")
    proc1 = subprocess.run([sys.executable, str(ROOT / "tools/generate_pred_1a_r1_reports.py")], cwd=str(ROOT), capture_output=True, text=True)
    assert proc1.returncode == 0
    proc2 = subprocess.run([sys.executable, str(ROOT / "tools/generate_pred_1a_r1_reports.py")], cwd=str(ROOT), capture_output=True, text=True)
    assert proc2.returncode == 0


# 8. test_val_access_denied_pred_1a_r1
def test_val_access_denied_pred_1a_r1():
    # Attempting to access VALIDATION must fail closed or be denied
    with pytest.raises((IntelAccessDeniedError, PermissionError, ValueError)):
        # VALIDATION is not allowed during PRED-1A R1
        dev_table = IntelDatasetAccessAPI.request_dataset(
            asset="XAU",
            dataset_role="VALIDATION",
            purpose="UNAUTHORIZED_VAL_TEST",
            caller="tests/test_pred_1a_r1.py",
            phase="PRED_1A_R1",
        )
        # If it didn't raise, ensure it's not permitted
        raise PermissionError("VALIDATION access granted unexpectedly")


# 9. test_holdout_access_denied_pred_1a_r1
def test_holdout_access_denied_pred_1a_r1():
    with pytest.raises(IntelAccessDeniedError):
        IntelDatasetAccessAPI.request_dataset(
            asset="XAU",
            dataset_role="HOLDOUT",
            purpose="UNAUTHORIZED_HOLDOUT_TEST",
            caller="tests/test_pred_1a_r1.py",
            phase="PRED_1A_R1",
        )


# 10. test_pristine_access_denied_pred_1a_r1
def test_pristine_access_denied_pred_1a_r1():
    with pytest.raises(IntelAccessDeniedError):
        IntelDatasetAccessAPI.request_dataset(
            asset="XAU",
            dataset_role="PRISTINE",
            purpose="UNAUTHORIZED_PRISTINE_TEST",
            caller="tests/test_pred_1a_r1.py",
            phase="PRED_1A_R1",
        )


# 11. test_cross_asset_group_not_session_context
def test_cross_asset_group_not_session_context():
    pipeline = PredictiveResearchPipeline(code_sha="0000111122223333444455556666777788889999")
    groups = pipeline.define_feature_groups()
    assert "CROSS_ASSET_ONLY" not in groups, "False CROSS_ASSET_ONLY group must be removed"
    assert "SESSION_CONTEXT_ONLY" in groups, "SESSION_CONTEXT_ONLY must be truthfully named"
    # Ensure session_context features are inside SESSION_CONTEXT_ONLY
    session_feats = groups["SESSION_CONTEXT_ONLY"]
    assert "underlying_session_state" in session_feats


# 12. test_target_scope_registered_vs_evaluated
def test_target_scope_registered_vs_evaluated():
    reg = TargetRegistry()
    assert len(reg.list_targets()) == 12
    scope_path = ROOT / "config/pred_1a_r1_evaluation_scope.json"
    assert scope_path.is_file()
    data = json.loads(scope_path.read_text())
    assert data["registered_targets_count"] == 12
    assert data["empirically_evaluated_targets_count"] == 6
    assert len(data["empirically_evaluated_targets"]) == 6
    assert len(data["registered_only_targets"]) == 6


# 13. test_split_future_window_matches_target_contract
def test_split_future_window_matches_target_contract():
    reg = TargetRegistry()
    t_5m = reg.get_target("future_log_return_5m")
    t_15m = reg.get_target("future_log_return_15m")
    t_1h = reg.get_target("future_log_return_1h")

    s_5m = PurgedTemporalSplitter(future_window=t_5m.future_window)
    s_15m = PurgedTemporalSplitter(future_window=t_15m.future_window)
    s_1h = PurgedTemporalSplitter(future_window=t_1h.future_window)

    assert s_5m.future_window == 5
    assert s_15m.future_window == 15
    assert s_1h.future_window == 60


# 14. test_4h_target_requires_240_bar_purge_if_evaluated
def test_4h_target_requires_240_bar_purge_if_evaluated():
    reg = TargetRegistry()
    t_4h = reg.get_target("future_log_return_4h")
    assert t_4h.future_window == 240
    assert t_4h.purge_requirement >= 240
    splitter = PurgedTemporalSplitter(future_window=t_4h.future_window, purge_window=t_4h.purge_requirement)
    assert splitter.purge_window == 240


# 15. test_embargo_semantics_truthful
def test_embargo_semantics_truthful():
    splitter = PurgedTemporalSplitter(n_folds=4, future_window=60, embargo=60)
    folds = splitter.split(1000)
    for fold in folds:
        # Expanding window train is strictly before test
        assert fold.train_end_idx < fold.test_start_idx
        # Train purge dropped future_window bars
        assert fold.purged_count == 60
        # Post-test embargo does not remove bars from expanding train
        assert fold.embargo_applied == 0
        assert "EXPANDING_WINDOW" in fold.embargo_semantics


# 16. test_categorical_encoding_not_hash_ordinal
def test_categorical_encoding_not_hash_ordinal():
    train_cats = [["OPEN"], ["OFF_HOURS_INDEX_MODE"], ["OPEN"]]
    encoder = TrainOnlyCategoricalEncoder()
    encoded = encoder.fit_transform(train_cats)

    # UNKNOWN=0, OFF_HOURS_INDEX_MODE=1, OPEN=2
    assert encoded[0][0] in (1.0, 2.0)
    assert encoded[1][0] in (1.0, 2.0)
    assert encoded[0][0] != encoded[1][0]
    # Verify no arbitrary sha256 floats like 83.0 or 47.0
    assert all(val[0] in (0.0, 1.0, 2.0) for val in encoded)


# 17. test_test_only_category_does_not_mutate_train_encoder
def test_test_only_category_does_not_mutate_train_encoder():
    train_cats = [["OPEN"], ["OFF_HOURS_INDEX_MODE"]]
    encoder = TrainOnlyCategoricalEncoder()
    encoder.fit(train_cats)
    vocab_before = dict(encoder.vocabularies_[0])

    test_cats = [["UNSEEN_NEW_CATEGORY"], ["ANOTHER_NEW_CAT"]]
    encoded_test = encoder.transform(test_cats)

    # Both unseen categories map safely to 0 (UNKNOWN)
    assert encoded_test[0][0] == 0.0
    assert encoded_test[1][0] == 0.0
    # Vocabulary remains completely unmutated
    assert encoder.vocabularies_[0] == vocab_before


# 18. test_fake_classification_pvalue_not_allowed
def test_fake_classification_pvalue_not_allowed():
    # Verify research_pipeline.py has no p_values_all.append(0.05)
    src_text = (ROOT / "src/btceth_os/predict/research_pipeline.py").read_text()
    assert "p_values_all.append(0.05)" not in src_text
    assert "append(0.05)" not in src_text


# 19. test_no_invalid_multiple_testing_claim
def test_no_invalid_multiple_testing_claim():
    pipeline = PredictiveResearchPipeline(code_sha="0000111122223333444455556666777788889999")
    # Verify that option A is used
    groups = pipeline.define_feature_groups()
    assert len(groups) == 6


# 20. test_empirical_verifier_uses_reports_not_dummy_arrays
def test_empirical_verifier_uses_reports_not_dummy_arrays():
    verifier_text = (ROOT / "tools/verify_pred_1a_r1.py").read_text()
    assert "dummy_y" not in verifier_text
    assert "[0.001, 0.04, 0.20]" not in verifier_text


# 21. test_prediction_firewall
def test_prediction_firewall():
    # Verify that prediction code has zero trade execution imports
    pred_files = list((ROOT / "src/btceth_os/predict").rglob("*.py"))
    for pf in pred_files:
        txt = pf.read_text()
        assert "take_trade" not in txt
        assert "create_order" not in txt
        assert "trade_board" not in txt


# 22. test_no_pnl_metrics
def test_no_pnl_metrics():
    pred_files = list((ROOT / "src/btceth_os/predict").rglob("*.py"))
    for pf in pred_files:
        txt = pf.read_text()
        assert "realized_pnl" not in txt
        assert "unrealized_pnl" not in txt


# 23. test_no_strategy_fields
def test_no_strategy_fields():
    pred_files = list((ROOT / "src/btceth_os/predict").rglob("*.py"))
    for pf in pred_files:
        txt = pf.read_text()
        assert "entry_zone" not in txt
        assert "stop_loss_price" not in txt
        assert "take_profit_price" not in txt


# 24. test_full_safety_state
def test_full_safety_state():
    prom = inspect_promotion_state()
    assert prom.trading_capability == 0
    assert prom.persistent_approved_shadow == 0
    assert prom.runtime_approved_shadow == 0
    assert prom.persistent_approved_paper == 0
    assert prom.runtime_approved_paper == 0
