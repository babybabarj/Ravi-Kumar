"""TRADING OS — PRED-1A: Leakage-Safe Predictive Research Foundation.

Provides:
  - Target Registry and formal target contracts
  - Purged and embargoed chronological temporal splitting
  - Train-only feature scalers and leakage guards
  - Naive baseline models
  - Candidate predictive models (Linear, Ridge, Logistic, Shallow Trees)
  - Research evaluation metrics (strictly devoid of P&L/trade performance)
  - Model calibration and reliability curve diagnostics
  - Temporal fold stability and effect size analysis
  - Multiple testing adjustments (Bonferroni, Benjamini-Hochberg)
  - Experiment budget enforcement and append-only experiment logging
  - Predictive research snapshot schema and recursive execution firewall
"""

from __future__ import annotations

__all__ = [
    "TargetDefinition",
    "TargetRegistry",
    "PurgedTemporalSplitter",
    "TemporalSplitFold",
    "LeakageViolationError",
]

from btceth_os.predict.target_registry import TargetDefinition, TargetRegistry
from btceth_os.predict.temporal_split import (
    LeakageViolationError,
    PurgedTemporalSplitter,
    TemporalSplitFold,
)
