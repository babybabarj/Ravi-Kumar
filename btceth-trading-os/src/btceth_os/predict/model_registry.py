"""Versioned Model Registry for PRED-1A.

Catalogs approved candidate research models, their hyperparameters, training constraints,
and runtime library metadata:
  - model_id
  - model_family
  - target_id
  - feature_set_id
  - hyperparameters
  - random_seed
  - training_window
  - purge_window
  - embargo_window
  - normalization_contract
  - model_version
  - library_versions
"""

from __future__ import annotations

import platform
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ModelContract:
    model_id: str
    model_family: str
    target_id: str
    feature_set_id: str
    hyperparameters: Dict[str, Any]
    random_seed: int
    training_window: str
    purge_window: int
    embargo_window: int
    normalization_contract: str
    model_version: str
    library_versions: Dict[str, str]
    research_only: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_current_library_versions() -> Dict[str, str]:
    """Captures runtime environment version metadata."""
    versions = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    try:
        import pyarrow
        versions["pyarrow"] = pyarrow.__version__
    except ImportError:
        pass
    return versions


class ModelRegistry:
    """Registry managing approved model definitions and contracts."""

    def __init__(self):
        self._models: Dict[str, ModelContract] = {}

    def register_model(self, contract: ModelContract) -> None:
        if contract.model_id in self._models:
            raise ValueError(f"Model '{contract.model_id}' is already registered.")
        self._models[contract.model_id] = contract

    def get_model(self, model_id: str) -> ModelContract:
        if model_id not in self._models:
            raise KeyError(f"Model '{model_id}' not found in registry.")
        return self._models[model_id]

    def list_models(self) -> List[ModelContract]:
        return list(self._models.values())

    def list_model_ids(self) -> List[str]:
        return list(self._models.keys())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "registry_version": "1.0.0",
            "models_count": len(self._models),
            "models": [asdict(m) for m in self._models.values()],
        }
