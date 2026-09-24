"""Layer G: Regime Stability & Threshold Sensitivity Audit for INTEL-1B.

Performs rigorous empirical stability validation of descriptive market regimes:
1. Regime Stability Audit:
   - Evaluates state persistence, durations, transition frequencies, and rapid flip rates.
   - Cross-evaluated on DEVELOPMENT partitions for BTC, ETH, and XAU.
2. Threshold Sensitivity Audit:
   - Perturbs classification boundaries by +/- epsilon (+/- 5%, 10%, 15%).
   - Measures classification disagreement rate and transition elasticity.
   - Strictly observational: identifies stable parameter regions WITHOUT optimizing for return or Sharpe.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .market_state import (
    FundingRegime,
    LiquidityActivityRegime,
    MarketQualityRegime,
    MarketStateEngine,
    MarketStateSnapshot,
    TrendRegime,
    VolatilityRegime,
)
from .state_transitions import DimensionTransitionMetrics, StateTransitionEngine


@dataclass(frozen=True)
class ThresholdPerturbationResult:
    parameter_name: str
    baseline_value: float
    perturbation_pct: float
    perturbed_value: float
    total_bars: int
    disagreement_count: int
    disagreement_rate: float
    baseline_transitions: int
    perturbed_transitions: int
    transition_difference: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ThresholdSensitivitySummary:
    parameter_name: str
    dimension: str
    baseline_value: float
    perturbation_results: List[ThresholdPerturbationResult]
    max_disagreement_rate: float
    mean_disagreement_rate: float
    is_classification_stable: bool  # e.g. mean disagreement < 15% under +/-10% perturbation

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["perturbation_results"] = [r.to_dict() for r in self.perturbation_results]
        return d


class RegimeStabilityAuditor:
    """Evaluates the empirical stability of regime definitions across multi-asset DEV data."""

    @classmethod
    def audit_asset_stability(
        cls,
        asset: str,
        snapshots: Sequence[MarketStateSnapshot],
        timestamps_ns: Sequence[int],
        data_qualities: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Produce full descriptive stability summary across all 5 dimensions."""
        tracked = StateTransitionEngine.track_snapshots(
            asset=asset,
            snapshots=snapshots,
            timestamps_ns=timestamps_ns,
            data_qualities=data_qualities,
        )

        dim_summaries: Dict[str, Any] = {}
        for dim, metrics in tracked.items():
            dim_summaries[dim] = {
                "total_bars": metrics.total_bars,
                "state_counts": metrics.state_counts,
                "transition_count": metrics.transition_count,
                "reversal_count": metrics.reversal_count,
                "rapid_flip_rate": round(metrics.rapid_flip_rate, 4),
                "unknown_fraction": round(metrics.unknown_fraction, 4),
                "degraded_fraction": round(metrics.degraded_fraction, 4),
                "persistence_probability": round(metrics.persistence_probability, 4),
                "mean_duration_bars": {k: round(v, 2) for k, v in metrics.mean_duration_by_state.items()},
                "median_duration_bars": metrics.median_duration_by_state,
                "p10_duration_bars": metrics.p10_duration_by_state,
                "p90_duration_bars": metrics.p90_duration_by_state,
            }

        return {
            "asset": asset,
            "total_bars": len(snapshots),
            "dimensions": dim_summaries,
            "overall_regime_coherence": "AUDITED_DESCRIPTIVE_ONLY",
        }


class ThresholdSensitivityAuditor:
    """Measures classification sensitivity to small perturbations in numerical thresholds."""

    @staticmethod
    def audit_trend_threshold(
        feature_tuples: Sequence[Tuple[Optional[float], Optional[float], Optional[float]]],
        param_name: str,
        baseline_val: float,
        perturbations: Sequence[float] = (-0.10, -0.05, 0.05, 0.10),
    ) -> ThresholdSensitivitySummary:
        """Audit sensitivity of trend classification to efficiency and persistence thresholds."""
        n = len(feature_tuples)
        if n == 0:
            return ThresholdSensitivitySummary(
                parameter_name=param_name,
                dimension="TREND",
                baseline_value=baseline_val,
                perturbation_results=[],
                max_disagreement_rate=0.0,
                mean_disagreement_rate=0.0,
                is_classification_stable=True,
            )

        # Baseline evaluation
        baseline_states = [
            MarketStateEngine.classify_trend(er, dp, sl)[0]
            for er, dp, sl in feature_tuples
        ]
        base_trans = sum(1 for i in range(1, n) if baseline_states[i] != baseline_states[i - 1])

        results: List[ThresholdPerturbationResult] = []

        for p_pct in perturbations:
            perturbed_val = baseline_val * (1.0 + p_pct)
            perturbed_states: List[str] = []

            for er, dp, sl in feature_tuples:
                eff_er = er
                eff_dp = dp
                eff_sl = sl

                # Apply perturbation to the targeted threshold parameter
                eff_high = perturbed_val if param_name == "efficiency_ratio_high" else 0.40
                eff_low = perturbed_val if param_name == "efficiency_ratio_low" else 0.25
                dp_up = perturbed_val if param_name == "directional_persistence_up" else 0.65
                dp_down = perturbed_val if param_name == "directional_persistence_down" else 0.35

                if eff_er is None or eff_dp is None or eff_sl is None:
                    st = TrendRegime.UNCERTAIN.value
                elif eff_er > eff_high:
                    if eff_dp >= dp_up and eff_sl > 0.0001:
                        st = TrendRegime.UP.value
                    elif eff_dp <= dp_down and eff_sl < -0.0001:
                        st = TrendRegime.DOWN.value
                    else:
                        st = TrendRegime.UNCERTAIN.value
                elif eff_er < eff_low:
                    st = TrendRegime.RANGE.value
                else:
                    st = TrendRegime.UNCERTAIN.value

                perturbed_states.append(st)

            disagreements = sum(1 for b, p in zip(baseline_states, perturbed_states) if b != p)
            disagreement_rate = float(disagreements / n)
            pert_trans = sum(1 for i in range(1, n) if perturbed_states[i] != perturbed_states[i - 1])

            results.append(
                ThresholdPerturbationResult(
                    parameter_name=param_name,
                    baseline_value=baseline_val,
                    perturbation_pct=p_pct,
                    perturbed_value=perturbed_val,
                    total_bars=n,
                    disagreement_count=disagreements,
                    disagreement_rate=round(disagreement_rate, 4),
                    baseline_transitions=base_trans,
                    perturbed_transitions=pert_trans,
                    transition_difference=pert_trans - base_trans,
                )
            )

        rates = [r.disagreement_rate for r in results]
        max_rate = max(rates) if rates else 0.0
        mean_rate = sum(rates) / len(rates) if rates else 0.0

        return ThresholdSensitivitySummary(
            parameter_name=param_name,
            dimension="TREND",
            baseline_value=baseline_val,
            perturbation_results=results,
            max_disagreement_rate=round(max_rate, 4),
            mean_disagreement_rate=round(mean_rate, 4),
            is_classification_stable=(mean_rate < 0.15),
        )

    @staticmethod
    def audit_volatility_threshold(
        vol_tuples: Sequence[Tuple[Optional[float], Optional[float]]],
        param_name: str,
        baseline_val: float,
        perturbations: Sequence[float] = (-0.10, -0.05, 0.05, 0.10),
    ) -> ThresholdSensitivitySummary:
        """Audit sensitivity of volatility classification to percentile boundaries."""
        n = len(vol_tuples)
        if n == 0:
            return ThresholdSensitivitySummary(
                parameter_name=param_name,
                dimension="VOLATILITY",
                baseline_value=baseline_val,
                perturbation_results=[],
                max_disagreement_rate=0.0,
                mean_disagreement_rate=0.0,
                is_classification_stable=True,
            )

        baseline_states = [
            MarketStateEngine.classify_volatility(vp, sv)[0]
            for vp, sv in vol_tuples
        ]
        base_trans = sum(1 for i in range(1, n) if baseline_states[i] != baseline_states[i - 1])

        results: List[ThresholdPerturbationResult] = []

        for p_pct in perturbations:
            perturbed_val = baseline_val * (1.0 + p_pct)
            perturbed_states: List[str] = []

            for vp, sv in vol_tuples:
                low_th = perturbed_val if param_name == "vol_percentile_low" else 0.20
                norm_th = perturbed_val if param_name == "vol_percentile_normal" else 0.75
                high_th = perturbed_val if param_name == "vol_percentile_high" else 0.95

                if vp is None:
                    st = VolatilityRegime.UNKNOWN.value
                elif vp < low_th:
                    st = VolatilityRegime.LOW.value
                elif vp <= norm_th:
                    st = VolatilityRegime.NORMAL.value
                elif vp <= high_th:
                    st = VolatilityRegime.HIGH.value
                else:
                    st = VolatilityRegime.EXTREME.value
                perturbed_states.append(st)

            disagreements = sum(1 for b, p in zip(baseline_states, perturbed_states) if b != p)
            disagreement_rate = float(disagreements / n)
            pert_trans = sum(1 for i in range(1, n) if perturbed_states[i] != perturbed_states[i - 1])

            results.append(
                ThresholdPerturbationResult(
                    parameter_name=param_name,
                    baseline_value=baseline_val,
                    perturbation_pct=p_pct,
                    perturbed_value=perturbed_val,
                    total_bars=n,
                    disagreement_count=disagreements,
                    disagreement_rate=round(disagreement_rate, 4),
                    baseline_transitions=base_trans,
                    perturbed_transitions=pert_trans,
                    transition_difference=pert_trans - base_trans,
                )
            )

        rates = [r.disagreement_rate for r in results]
        max_rate = max(rates) if rates else 0.0
        mean_rate = sum(rates) / len(rates) if rates else 0.0

        return ThresholdSensitivitySummary(
            parameter_name=param_name,
            dimension="VOLATILITY",
            baseline_value=baseline_val,
            perturbation_results=results,
            max_disagreement_rate=round(max_rate, 4),
            mean_disagreement_rate=round(mean_rate, 4),
            is_classification_stable=(mean_rate < 0.15),
        )
