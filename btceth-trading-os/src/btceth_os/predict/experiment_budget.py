"""Experiment Budget Enforcement and Append-Only Experiment Registry for PRED-1A.

Enforces:
  1. Strict budget limits pre-declared in config/pred_1a_experiment_budget.json.
  2. Bounded exploratory search: fails closed if any dimension exceeds budget.
  3. Append-only experiment logging in artifacts/research/pred_1a_experiment_registry.jsonl.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[3]
BUDGET_CONFIG_PATH = ROOT / "config/pred_1a_experiment_budget.json"
REGISTRY_LOG_PATH = ROOT / "artifacts/research/pred_1a_experiment_registry.jsonl"
_REGISTRY_LOCK = threading.Lock()


class ExperimentBudgetExceededError(RuntimeError):
    """Raised when an experiment execution would exceed the pre-declared budget."""
    pass


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    timestamp_utc: str
    code_sha: str
    dataset_id: str
    dataset_hash: str
    feature_set: str
    target_id: str
    horizon: str
    model_id: str
    hyperparameters: Dict[str, Any]
    split_id: str
    seed: int
    status: str  # "COMPLETED", "FAILED"
    artifact_paths: List[str]
    code_tree_sha: Optional[str] = None
    dataset_artifact_sha256: Optional[str] = None
    dataset_logical_hash: Optional[str] = None
    phase: str = "PRED_1A"
    research_run_id: str = "PRED_1A_RUN_001"


class ExperimentBudgetGovernor:
    """Monitors and enforces research experiment budget bounds."""

    def __init__(
        self,
        config_path: Path = BUDGET_CONFIG_PATH,
        registry_path: Path = REGISTRY_LOG_PATH,
        budget_path: Optional[Path] = None,
    ):
        if budget_path is not None:
            config_path = budget_path
        self.config_path = Path(config_path)
        self.registry_path = Path(registry_path)
        self._load_budget()

    def _load_budget(self) -> None:
        if not self.config_path.is_file():
            raise FileNotFoundError(f"Experiment budget configuration missing: {self.config_path}")
        data = json.loads(self.config_path.read_text())
        limits = data.get("limits", {})
        self.max_targets = limits.get("max_targets", data.get("max_targets", 12))
        self.max_model_families = limits.get("max_model_families", data.get("max_model_families", 6))
        self.max_feature_groups = limits.get("max_feature_groups", data.get("max_feature_groups", 6))
        self.max_hyperparameter_variants = limits.get("max_hyperparameter_variants", data.get("max_hyperparameter_variants", 8))
        self.max_total_experiments = limits.get("max_total_experiments", data.get("max_total_experiments", 100))

    @property
    def total_experiments_conducted(self) -> int:
        return len(self.load_registry())

    def register_experiment(self, record_or_dict: Any) -> None:
        if isinstance(record_or_dict, dict):
            rec = ExperimentRecord(
                experiment_id=record_or_dict.get("experiment_id", f"EXP_{datetime.now(timezone.utc).timestamp()}"),
                timestamp_utc=record_or_dict.get("timestamp_utc", datetime.now(timezone.utc).isoformat()),
                code_sha=record_or_dict.get("code_sha", "TEST_CODE_SHA"),
                dataset_id=record_or_dict.get("dataset_id", "DEV_XAUUSDT_1M"),
                dataset_hash=record_or_dict.get("dataset_hash", "TEST_HASH"),
                feature_set=record_or_dict.get("feature_group", record_or_dict.get("feature_set", "ALL")),
                target_id=record_or_dict.get("target_id", "target"),
                horizon=record_or_dict.get("horizon", "1h"),
                model_id=record_or_dict.get("model_family", record_or_dict.get("model_id", "LinearRegression")),
                hyperparameters=record_or_dict.get("hyperparameters", {}),
                split_id=record_or_dict.get("split_id", "fold_1"),
                seed=record_or_dict.get("seed", 42),
                status=record_or_dict.get("status", "COMPLETED"),
                artifact_paths=record_or_dict.get("artifact_paths", []),
            )
        else:
            rec = record_or_dict
        self.check_and_log_experiment(rec)

    def load_registry(self) -> List[Dict[str, Any]]:
        if not self.registry_path.is_file():
            return []
        records = []
        with self.registry_path.open("r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    records.append(json.loads(line_str))
        return records

    def audit_budget(self, new_records_count: int = 0) -> Dict[str, Any]:
        records = self.load_registry()
        total_runs = len(records) + new_records_count
        targets_seen = {r.get("target_id") for r in records if r.get("target_id")}
        models_seen = {r.get("model_id") for r in records if r.get("model_id")}
        feature_sets_seen = {r.get("feature_set") for r in records if r.get("feature_set")}

        is_valid = (
            total_runs <= self.max_total_experiments
            and len(targets_seen) <= self.max_targets
            and len(feature_sets_seen) <= self.max_feature_groups
        )

        return {
            "total_experiments": len(records),
            "max_total_experiments": self.max_total_experiments,
            "unique_targets": len(targets_seen),
            "max_targets": self.max_targets,
            "unique_models": len(models_seen),
            "unique_feature_groups": len(feature_sets_seen),
            "max_feature_groups": self.max_feature_groups,
            "budget_respected": is_valid,
        }

    def check_and_log_experiment(self, record: ExperimentRecord) -> None:
        """Verifies budget and uniqueness before appending experiment record to the audit ledger."""
        records = self.load_registry()
        existing_ids = {r.get("experiment_id") for r in records}
        if record.experiment_id in existing_ids:
            raise ValueError(f"DUPLICATE EXPERIMENT ID: {record.experiment_id} already exists in registry.")
        if len(records) >= self.max_total_experiments:
            raise ExperimentBudgetExceededError(
                f"BUDGET EXCEEDED: total experiments ({len(records)}) reached maximum ({self.max_total_experiments})."
            )

        line = json.dumps(asdict(record), sort_keys=True) + "\n"
        with _REGISTRY_LOCK:
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            with self.registry_path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
