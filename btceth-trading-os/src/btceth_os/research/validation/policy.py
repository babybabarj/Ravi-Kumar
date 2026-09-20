from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
import yaml


@dataclass(frozen=True)
class PolicyEvaluationResult:
    is_promoted: bool
    status: str  # APPROVED_FOR_PAPER, APPROVED_FOR_SHADOW, REJECTED
    checks: Dict[str, bool]
    rejection_reasons: List[str]


class StrategyValidationPolicy:
    """Evaluates strategy metrics against the machine-readable validation policy."""

    def __init__(self, policy_path: Path | str | None = None) -> None:
        if policy_path is None:
            # Default location at repo root
            policy_path = Path(__file__).resolve().parents[4] / "config" / "strategy_validation_policy.yaml"
        self.policy_path = Path(policy_path)
        self.config = self._load_policy()

    def _load_policy(self) -> dict[str, Any]:
        if not self.policy_path.exists():
            raise FileNotFoundError(f"Strategy validation policy not found at: {self.policy_path}")
        with open(self.policy_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def evaluate(
        self,
        *,
        out_of_sample_trades: int,
        net_return_base: float,
        net_return_stressed: float,
        annualized_sharpe: float,
        max_drawdown: float,
        deflated_sharpe_ratio: Optional[float],
        pbo: Optional[float],
        parameter_stability_ratio: float,
        trade_concentration_top1: float,
        profitable_years_ratio: float = 1.0,
        max_single_year_drawdown: float = 0.0,
        walk_forward_folds_count: int = 3,
    ) -> PolicyEvaluationResult:
        thresholds = self.config.get("thresholds", {})
        min_trades = int(thresholds.get("minimum_out_of_sample_trades", 30))
        min_folds = int(thresholds.get("minimum_walk_forward_folds", 3))
        max_dd = float(thresholds.get("maximum_acceptable_drawdown_pct", 0.15))
        min_sharpe = float(thresholds.get("minimum_annualized_sharpe", 1.00))
        max_top1 = float(thresholds.get("maximum_trade_concentration_top1_pct", 0.35))
        min_dsr = float(thresholds.get("statistical_significance", {}).get("minimum_deflated_sharpe_ratio", 0.95))
        max_pbo = float(thresholds.get("statistical_significance", {}).get("maximum_pbo", 0.50))
        min_param_stability = float(thresholds.get("parameter_stability", {}).get("minimum_profitable_neighbors_pct", 0.60))
        min_year_ratio = float(thresholds.get("multi_year_consistency", {}).get("minimum_profitable_years_ratio", 0.66))
        max_year_dd = float(thresholds.get("multi_year_consistency", {}).get("maximum_single_year_drawdown_pct", 0.12))

        checks: Dict[str, bool] = {}
        reasons: List[str] = []

        # 1. Sample adequacy
        checks["min_sample_trades"] = out_of_sample_trades >= min_trades
        if not checks["min_sample_trades"]:
            reasons.append(f"Insufficient OOS trades ({out_of_sample_trades} < {min_trades})")

        checks["min_walk_forward_folds"] = walk_forward_folds_count >= min_folds
        if not checks["min_walk_forward_folds"]:
            reasons.append(f"Insufficient walk-forward folds ({walk_forward_folds_count} < {min_folds})")

        # 2. Base profitability
        checks["base_net_profitability"] = net_return_base > 0.0
        if not checks["base_net_profitability"]:
            reasons.append(f"Negative net return after base costs ({net_return_base:.4f} <= 0)")

        # 3. Cost stress survival
        checks["cost_stress_survival"] = net_return_stressed > 0.0
        if not checks["cost_stress_survival"]:
            reasons.append(f"Fails cost stress survival: net return under stressed costs is {net_return_stressed:.4f} <= 0")

        # 4. Maximum drawdown
        checks["drawdown_within_limit"] = max_drawdown <= max_dd
        if not checks["drawdown_within_limit"]:
            reasons.append(f"Max drawdown exceeded limit ({max_drawdown:.3f} > {max_dd:.3f})")

        # 5. Annualized Sharpe
        checks["sharpe_ratio"] = annualized_sharpe >= min_sharpe
        if not checks["sharpe_ratio"]:
            reasons.append(f"Sharpe ratio below threshold ({annualized_sharpe:.2f} < {min_sharpe:.2f})")

        # 6. Trade concentration
        checks["trade_concentration"] = trade_concentration_top1 <= max_top1
        if not checks["trade_concentration"]:
            reasons.append(f"Excessive trade profit concentration (top 1 trade is {trade_concentration_top1:.1%} > {max_top1:.1%})")

        # 7. Parameter stability
        checks["parameter_stability"] = parameter_stability_ratio >= min_param_stability
        if not checks["parameter_stability"]:
            reasons.append(f"Parameter instability ({parameter_stability_ratio:.1%} profitable neighbors < {min_param_stability:.1%})")

        # 8. Multi-Year Consistency
        checks["multi_year_consistency"] = (
            profitable_years_ratio >= min_year_ratio and max_single_year_drawdown <= max_year_dd
        )
        if not checks["multi_year_consistency"]:
            reasons.append(
                f"Multi-year inconsistency: profitable years {profitable_years_ratio:.1%} < {min_year_ratio:.1%} "
                f"or max single-year drawdown {max_single_year_drawdown:.1%} > {max_year_dd:.1%}"
            )

        # 9. Deflated Sharpe Ratio
        if deflated_sharpe_ratio is None:
            checks["deflated_sharpe"] = False
            reasons.append("Deflated Sharpe Ratio is UNCOMPUTABLE")
        else:
            checks["deflated_sharpe"] = deflated_sharpe_ratio >= min_dsr
            if not checks["deflated_sharpe"]:
                reasons.append(f"Deflated Sharpe Ratio failed multiple testing penalty (DSR={deflated_sharpe_ratio:.3f} < {min_dsr:.2f})")

        # 10. Probability of Backtest Overfitting (PBO)
        if pbo is None:
            checks["pbo_limit"] = False
            reasons.append("PBO is UNCOMPUTABLE: insufficient parameter variants explored")
        else:
            checks["pbo_limit"] = pbo <= max_pbo
            if not checks["pbo_limit"]:
                reasons.append(f"High probability of backtest overfitting (PBO={pbo:.2f} > {max_pbo:.2f})")

        all_passed = all(checks.values())
        dsr_score = deflated_sharpe_ratio if deflated_sharpe_ratio is not None else 0.0
        if all_passed:
            status = "APPROVED_FOR_PAPER"
        elif (
            checks["base_net_profitability"]
            and checks["cost_stress_survival"]
            and checks["min_sample_trades"]
            and dsr_score >= 0.70
        ):
            status = "APPROVED_FOR_SHADOW"
        else:
            status = "REJECTED"

        return PolicyEvaluationResult(
            is_promoted=all_passed,
            status=status,
            checks=checks,
            rejection_reasons=reasons,
        )
