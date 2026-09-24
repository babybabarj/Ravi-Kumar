"""Layer D: Cross-Asset Context Engine for INTEL-1A.

Evaluates causal, descriptive statistical relationships across BTCUSDT, ETHUSDT, and XAUUSDT:
- Trailing return correlations
- Rolling covariance and beta estimates
- Relative volatility ratios
- Cross-asset return dispersion
- Lead/lag cross-correlation diagnostics
- Regime agreement / divergence

Strictly causal: information from asset B at time > t CANNOT enter asset A's state at time t.
Descriptive only: contains zero trade rules, signal thresholds, or profit optimizations.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _mean(vals: Sequence[float]) -> float:
    return sum(vals) / len(vals)


def _std(vals: Sequence[float], m: Optional[float] = None) -> float:
    if len(vals) < 2:
        return 0.0
    mu = m if m is not None else _mean(vals)
    var = sum((x - mu) ** 2 for x in vals) / (len(vals) - 1)
    return math.sqrt(max(0.0, var))


def _pearson_corr(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    if len(x) != len(y) or len(x) < 3:
        return None
    mx = _mean(x)
    my = _mean(y)
    sx = _std(x, mx)
    sy = _std(y, my)
    if sx < 1e-12 or sy < 1e-12:
        return 0.0
    cov = sum((x[i] - mx) * (y[i] - my) for i in range(len(x))) / (len(x) - 1)
    return cov / (sx * sy)


def _covariance_and_beta(
    dependent: Sequence[float], benchmark: Sequence[float]
) -> Tuple[Optional[float], Optional[float]]:
    if len(dependent) != len(benchmark) or len(dependent) < 3:
        return None, None
    md = _mean(dependent)
    mb = _mean(benchmark)
    var_b = sum((x - mb) ** 2 for x in benchmark) / (len(benchmark) - 1)
    if var_b < 1e-12:
        return 0.0, 0.0
    cov = sum((dependent[i] - md) * (benchmark[i] - mb) for i in range(len(dependent))) / (len(dependent) - 1)
    beta = cov / var_b
    return cov, beta


@dataclass(frozen=True)
class CrossAssetPairMetrics:
    asset_a: str
    asset_b: str
    lookback_window: int
    return_correlation: Optional[float]
    relative_volatility_ratio: Optional[float]  # vol(A) / vol(B)
    beta_a_to_b: Optional[float]
    lead_lag_lag1_corr_a_leads: Optional[float]  # corr(a_{t-1}, b_t)
    lead_lag_lag1_corr_b_leads: Optional[float]  # corr(b_{t-1}, a_t)
    correlation_instability: Optional[float]  # |corr_short - corr_long|

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CrossAssetContextSnapshot:
    timestamp_ns: int
    asset_pairs: Dict[str, CrossAssetPairMetrics]
    cross_asset_dispersion_60m: Optional[float]
    regime_agreement: Dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns,
            "asset_pairs": {k: v.to_dict() for k, v in self.asset_pairs.items()},
            "cross_asset_dispersion_60m": self.cross_asset_dispersion_60m,
            "regime_agreement": self.regime_agreement,
        }


class CrossAssetContextEngine:
    """Computes causal cross-asset context across aligned return streams up to time t."""

    @staticmethod
    def compute_pair_metrics(
        asset_a: str,
        asset_b: str,
        returns_a: Sequence[float],
        returns_b: Sequence[float],
        lookback: int = 60,
        short_lookback: int = 15,
    ) -> CrossAssetPairMetrics:
        """Computes pairwise metrics using exactly trailing observations up to current point."""
        n = min(len(returns_a), len(returns_b))
        if n < lookback:
            return CrossAssetPairMetrics(
                asset_a=asset_a,
                asset_b=asset_b,
                lookback_window=lookback,
                return_correlation=None,
                relative_volatility_ratio=None,
                beta_a_to_b=None,
                lead_lag_lag1_corr_a_leads=None,
                lead_lag_lag1_corr_b_leads=None,
                correlation_instability=None,
            )

        ra = list(returns_a[-lookback:])
        rb = list(returns_b[-lookback:])

        corr = _pearson_corr(ra, rb)
        std_a = _std(ra)
        std_b = _std(rb)
        rel_vol = (std_a / std_b) if std_b > 1e-12 else None
        _, beta = _covariance_and_beta(ra, rb)

        # Lead/lag cross-correlation (strictly trailing, no lookahead)
        # corr(a_{t-1}, b_t) -> does past a correlate with current b?
        a_leads_corr = _pearson_corr(ra[:-1], rb[1:]) if len(ra) > 3 else None
        # corr(b_{t-1}, a_t) -> does past b correlate with current a?
        b_leads_corr = _pearson_corr(rb[:-1], ra[1:]) if len(rb) > 3 else None

        # Correlation instability: |corr(short) - corr(long)|
        short_ra = list(returns_a[-short_lookback:])
        short_rb = list(returns_b[-short_lookback:])
        short_corr = _pearson_corr(short_ra, short_rb)
        instability = abs(short_corr - corr) if (short_corr is not None and corr is not None) else None

        return CrossAssetPairMetrics(
            asset_a=asset_a,
            asset_b=asset_b,
            lookback_window=lookback,
            return_correlation=corr,
            relative_volatility_ratio=rel_vol,
            beta_a_to_b=beta,
            lead_lag_lag1_corr_a_leads=a_leads_corr,
            lead_lag_lag1_corr_b_leads=b_leads_corr,
            correlation_instability=instability,
        )

    @classmethod
    def evaluate_multi_asset_context(
        cls,
        timestamp_ns: int,
        aligned_returns_by_asset: Dict[str, Sequence[float]],
        regimes_by_asset: Optional[Dict[str, str]] = None,
        lookback: int = 60,
    ) -> CrossAssetContextSnapshot:
        """Evaluates cross-asset context across available asset return streams."""
        assets = sorted(aligned_returns_by_asset.keys())
        pairs: Dict[str, CrossAssetPairMetrics] = {}

        for i in range(len(assets)):
            for j in range(i + 1, len(assets)):
                a, b = assets[i], assets[j]
                key = f"{a}_{b}"
                pairs[key] = cls.compute_pair_metrics(
                    a, b, aligned_returns_by_asset[a], aligned_returns_by_asset[b], lookback=lookback
                )

        # Cross-asset dispersion: standard deviation of asset returns across the universe in current bar
        current_returns = [
            aligned_returns_by_asset[a][-1]
            for a in assets
            if len(aligned_returns_by_asset[a]) > 0
        ]
        dispersion = _std(current_returns) if len(current_returns) >= 2 else None

        # Regime agreement
        agreement: Dict[str, bool] = {}
        if regimes_by_asset and len(regimes_by_asset) >= 2:
            reg_assets = sorted(regimes_by_asset.keys())
            for i in range(len(reg_assets)):
                for j in range(i + 1, len(reg_assets)):
                    a, b = reg_assets[i], reg_assets[j]
                    agreement[f"{a}_{b}"] = (
                        regimes_by_asset[a] == regimes_by_asset[b]
                        and regimes_by_asset[a] not in ("UNKNOWN", "UNCERTAIN")
                    )

        return CrossAssetContextSnapshot(
            timestamp_ns=timestamp_ns,
            asset_pairs=pairs,
            cross_asset_dispersion_60m=dispersion,
            regime_agreement=agreement,
        )
