"""One-Time Research Execution Runner for PRED-1A R1.

STAGE A: Executes predictive research models on the development partition once,
generating immutable research-run artifacts and append-only audit records.

Enforces:
  1. Only ONE logged data access to DEV during research execution.
  2. Strict binding of experiments to the tested Git commit SHA and tree SHA.
  3. Generation of immutable research artifacts at artifacts/research/pred_1a_r1_run_artifacts.json.
  4. Logging to dedicated R1 experiment registry and data access ledger.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from btceth_os.intel.data_access import IntelDatasetAccessAPI
from btceth_os.predict.experiment_budget import ExperimentBudgetGovernor
from btceth_os.predict.model_registry import ModelRegistry
from btceth_os.predict.research_pipeline import (
    FORBIDDEN_STALE_SHA,
    PredictiveResearchPipeline,
)
from btceth_os.predict.target_registry import TargetRegistry


def resolve_git(ref: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", ref],
            cwd=str(ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "UNKNOWN_GIT_SHA"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PRED-1A R1 research study.")
    parser.add_argument("--code-sha", type=str, default=None, help="Tested Git commit SHA")
    parser.add_argument("--tree-sha", type=str, default=None, help="Tested Git tree SHA")
    parser.add_argument("--force", action="store_true", help="Force rerun and overwrite research run artifact")
    args = parser.parse_args()

    artifacts_dir = ROOT / "artifacts" / "research"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    run_artifacts_path = artifacts_dir / "pred_1a_r1_run_artifacts.json"
    budget_config_path = ROOT / "config" / "pred_1a_r1_experiment_budget.json"
    registry_path = artifacts_dir / "pred_1a_r1_experiment_registry.jsonl"
    ledger_path = artifacts_dir / "pred_1a_r1_data_access_ledger.jsonl"

    if run_artifacts_path.is_file() and not args.force:
        print(f"Research artifacts already exist at {run_artifacts_path}. Use --force to rerun.")
        return

    code_sha = args.code_sha or resolve_git("HEAD")
    tree_sha = args.tree_sha or resolve_git("HEAD^{tree}")

    if code_sha == FORBIDDEN_STALE_SHA:
        print(f"ERROR: Cannot run research with forbidden stale SHA: {FORBIDDEN_STALE_SHA}", file=sys.stderr)
        sys.exit(1)

    print(f"Executing PRED-1A R1 Research Study...")
    print(f"  Code SHA: {code_sha}")
    print(f"  Tree SHA: {tree_sha}\n")

    # 1. Request official DEV dataset via IntelDatasetAccessAPI (logged in R1 access ledger)
    dev_table = IntelDatasetAccessAPI.request_dataset(
        asset="XAU",
        dataset_role="DEVELOPMENT",
        purpose="PRED_1A_R1_RESEARCH",
        caller="tools/run_pred_1a_r1_research.py",
        phase="PRED_1A_R1",
        max_rows=10000,
        ledger_path=ledger_path,
    )
    sample_table = dev_table.slice(0, 10000)

    # 2. Initialize registries and budget governor
    target_registry = TargetRegistry()
    model_registry = ModelRegistry()
    budget_governor = ExperimentBudgetGovernor(
        config_path=budget_config_path,
        registry_path=registry_path,
    )

    # 3. Create pipeline with injected provenance
    pipeline = PredictiveResearchPipeline(
        target_registry=target_registry,
        model_registry=model_registry,
        budget_governor=budget_governor,
        code_sha=code_sha,
        code_tree_sha=tree_sha,
        phase="PRED_1A_R1",
        research_run_id="PRED_1A_R1_RUN_001",
    )

    # 4. Run the study
    study_results = pipeline.run_study(
        sample_table,
        asset="XAUUSDT",
        max_rows=10000,
        n_folds=4,
        source_artifact_path=ROOT / "artifacts/research/partitions/XAUUSDT_DEV_2026_01_04_V3.parquet",
        code_sha=code_sha,
        code_tree_sha=tree_sha,
    )

    # 5. Save immutable research run artifact
    run_artifacts_path.write_text(json.dumps(study_results, indent=2) + "\n")
    print(f"\nWrote immutable research artifacts to {run_artifacts_path}")

    # 6. Summary metrics
    print(f"\nPRED-1A R1 Research Execution Complete:")
    print(f"  Research Run ID       : {study_results['research_run_id']}")
    print(f"  Sample Hash           : {study_results['sample_hash']}")
    print(f"  Artifact SHA256       : {study_results['source_artifact_sha256']}")
    print(f"  Experiments Logged    : {len(budget_governor.load_registry())}")
    print(f"  Status                : {study_results['status']}")


if __name__ == "__main__":
    main()
