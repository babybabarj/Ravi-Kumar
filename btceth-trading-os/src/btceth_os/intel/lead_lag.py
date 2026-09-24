"""Layer H: Cross-Asset Causality, Lead/Lag Safety & Clock Alignment for INTEL-1B.

Machine-enforces strict separation between causal live-eligible metrics and retrospective research diagnostics:
- CAUSAL_LIVE_ELIGIBLE_METRICS: Only admits observations with availability timestamp <= t and non-negative lag (lag >= 0).
- RETROSPECTIVE_RESEARCH_ONLY_METRICS: Retrospective lead/lag correlations that require lookahead relative to the historical observation anchor. Strictly forbidden from live intelligence snapshots.

Cross-Asset Clock Alignment:
Explicitly tracks asset observation availability (BTC, ETH, XAU) at snapshot timestamp t.
Partially available observations yield PARTIAL or UNKNOWN context, strictly prohibiting silent forward-filling across missing intervals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Sequence, Set


class MetricEligibilityCategory(str, Enum):
    CAUSAL_LIVE_ELIGIBLE = "CAUSAL_LIVE_ELIGIBLE"
    RETROSPECTIVE_RESEARCH_ONLY = "RETROSPECTIVE_RESEARCH_ONLY"


CAUSAL_LIVE_ELIGIBLE_METRICS: Set[str] = {
    "lagged_return_correlation",
    "contemporaneous_return_correlation",
    "rolling_cross_beta",
    "relative_volatility_ratio",
    "historical_lag_covariance",
    "causal_dispersion",
}

RETROSPECTIVE_RESEARCH_ONLY_METRICS: Set[str] = {
    "future_lead_correlation",
    "optimal_lead_lag_argmax",
    "cross_asset_predictive_lead_ratio",
    "retrospective_lead_information_flow",
}


class NegativeLagCausalityViolationError(Exception):
    """Raised when a negative lag is passed to a causal live intelligence calculation."""
    pass


class RetrospectiveMetricInLiveContextError(Exception):
    """Raised when a retrospective research metric is requested for a live snapshot."""
    pass


class ClockAlignmentViolationError(Exception):
    """Raised when observation availability timestamp violates causality relative to snapshot timestamp."""
    pass


@dataclass(frozen=True)
class CrossAssetClockAlignment:
    """Explicitly audits multi-asset availability timestamps at snapshot time t."""

    snapshot_timestamp_ns: int
    btc_available_at_ns: Optional[int]
    eth_available_at_ns: Optional[int]
    xau_available_at_ns: Optional[int]

    @property
    def is_fully_aligned(self) -> bool:
        return (
            self.btc_available_at_ns is not None
            and self.eth_available_at_ns is not None
            and self.xau_available_at_ns is not None
            and self.btc_available_at_ns <= self.snapshot_timestamp_ns
            and self.eth_available_at_ns <= self.snapshot_timestamp_ns
            and self.xau_available_at_ns <= self.snapshot_timestamp_ns
        )

    @property
    def context_state(self) -> str:
        available_count = sum(
            1
            for ts in (self.btc_available_at_ns, self.eth_available_at_ns, self.xau_available_at_ns)
            if ts is not None and ts <= self.snapshot_timestamp_ns
        )
        if available_count == 3:
            return "COMPLETE"
        if available_count > 0:
            return "PARTIAL"
        return "UNKNOWN"

    def assert_causality(self) -> None:
        """Assert no future availability timestamps leak into snapshot."""
        for name, ts in [
            ("BTC", self.btc_available_at_ns),
            ("ETH", self.eth_available_at_ns),
            ("XAU", self.xau_available_at_ns),
        ]:
            if ts is not None and ts > self.snapshot_timestamp_ns:
                raise ClockAlignmentViolationError(
                    f"CLOCK_ALIGNMENT_LEAKAGE: {name} availability timestamp ({ts}) > snapshot ({self.snapshot_timestamp_ns})"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_timestamp_ns": self.snapshot_timestamp_ns,
            "btc_available_at_ns": self.btc_available_at_ns,
            "eth_available_at_ns": self.eth_available_at_ns,
            "xau_available_at_ns": self.xau_available_at_ns,
            "is_fully_aligned": self.is_fully_aligned,
            "context_state": self.context_state,
        }


@dataclass(frozen=True)
class LeadLagSpecification:
    source_asset: str
    target_asset: str
    metric_name: str
    lag: int  # Must be >= 0 for live causal snapshots
    window: int
    minimum_samples: int
    timestamp_alignment_rule: str = "EXACT_TIMESTAMP_MATCH"
    metric_category: MetricEligibilityCategory = MetricEligibilityCategory.CAUSAL_LIVE_ELIGIBLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_asset": self.source_asset,
            "target_asset": self.target_asset,
            "metric_name": self.metric_name,
            "lag": self.lag,
            "window": self.window,
            "minimum_samples": self.minimum_samples,
            "timestamp_alignment_rule": self.timestamp_alignment_rule,
            "metric_category": self.metric_category.value,
        }


@dataclass(frozen=True)
class LeadLagResult:
    spec: LeadLagSpecification
    correlation: Optional[float]
    covariance: Optional[float]
    effective_samples: int
    is_causal_live_eligible: bool
    availability_timestamp_ns: int

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["spec"] = self.spec.to_dict()
        return d


class LeadLagSafetyGate:
    """Enforces mathematical causality and metric eligibility boundaries."""

    @staticmethod
    def validate_for_live_snapshot(spec: LeadLagSpecification) -> None:
        """Machine-enforce that retrospective research metrics cannot enter live snapshot."""
        if spec.metric_name in RETROSPECTIVE_RESEARCH_ONLY_METRICS:
            raise RetrospectiveMetricInLiveContextError(
                f"RETROSPECTIVE_METRIC_REJECTED: '{spec.metric_name}' requires future lookahead "
                f"and is strictly forbidden from live causal snapshots."
            )

        if spec.lag < 0:
            raise NegativeLagCausalityViolationError(
                f"NEGATIVE_LAG_FORBIDDEN: Requested lag={spec.lag} for '{spec.metric_name}'. "
                f"Negative lags inspect future observations and violate causal live invariants."
            )

        if spec.metric_category != MetricEligibilityCategory.CAUSAL_LIVE_ELIGIBLE:
            raise RetrospectiveMetricInLiveContextError(
                f"CATEGORY_INELIGIBLE: Metric category '{spec.metric_category}' is not live-eligible."
            )


class LeadLagEngine:
    """Computes cross-asset lead/lag metrics with machine-enforced causal boundaries."""

    @classmethod
    def compute_pair_lead_lag(
        cls,
        source_returns: Sequence[float],
        target_returns: Sequence[float],
        timestamps_ns: Sequence[int],
        spec: LeadLagSpecification,
        current_t_ns: int,
        is_live_context: bool = True,
    ) -> LeadLagResult:
        """Compute lead/lag relation with strict verification that no data past current_t_ns is accessed."""
        if is_live_context:
            LeadLagSafetyGate.validate_for_live_snapshot(spec)

        # Restrict inputs to observations at or before current_t_ns
        valid_indices = [i for i, ts in enumerate(timestamps_ns) if ts <= current_t_ns]
        if not valid_indices:
            return LeadLagResult(
                spec=spec,
                correlation=None,
                covariance=None,
                effective_samples=0,
                is_causal_live_eligible=(spec.lag >= 0 and spec.metric_name in CAUSAL_LIVE_ELIGIBLE_METRICS),
                availability_timestamp_ns=current_t_ns,
            )

        max_idx = valid_indices[-1]
        lag = spec.lag
        window = spec.window

        # Build pair aligned by lag: target at index i, source at index i - lag
        # For positive lag, target(t) is compared against source(t - lag).
        # For negative lag (retrospective only), target(t) is compared against source(t + |lag|).
        pairs: List[tuple[float, float]] = []

        start_idx = max(0, max_idx - window + 1)
        for i in range(start_idx, max_idx + 1):
            src_idx = i - lag
            if 0 <= src_idx <= max_idx:
                pairs.append((source_returns[src_idx], target_returns[i]))

        if len(pairs) < spec.minimum_samples:
            return LeadLagResult(
                spec=spec,
                correlation=None,
                covariance=None,
                effective_samples=len(pairs),
                is_causal_live_eligible=(spec.lag >= 0 and spec.metric_name in CAUSAL_LIVE_ELIGIBLE_METRICS),
                availability_timestamp_ns=current_t_ns,
            )

        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        n = len(pairs)

        mean_x = sum(xs) / n
        mean_y = sum(ys) / n

        var_x = sum((x - mean_x) ** 2 for x in xs) / n
        var_y = sum((y - mean_y) ** 2 for y in ys) / n
        cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in pairs) / n

        if var_x < 1e-18 or var_y < 1e-18:
            corr = 0.0
        else:
            corr = cov_xy / math.sqrt(var_x * var_y)
            corr = max(-1.0, min(1.0, corr))

        is_eligible = (spec.lag >= 0 and spec.metric_name in CAUSAL_LIVE_ELIGIBLE_METRICS)

        return LeadLagResult(
            spec=spec,
            correlation=round(corr, 6),
            covariance=round(cov_xy, 10),
            effective_samples=n,
            is_causal_live_eligible=is_eligible,
            availability_timestamp_ns=current_t_ns,
        )
