"""Layer L: Feature Quality, Redundancy, Distribution, Drift & Perturbation Audits for INTEL-1B.

Performs exhaustive descriptive audits on DEVELOPMENT data:
1. Feature Distribution Audit:
   - Descriptive summary (count, missing, min, max, median, p01, p05, p95, p99, mean, std, finite_fraction).
   - Detection of constant features, infinities, and singularities.
2. Feature Redundancy Audit:
   - Evaluates pairwise correlation and rank correlation on DEV.
   - Categorizes pairs into REDUNDANCY_HIGH (>=0.95), REDUNDANCY_MODERATE (0.80-0.95), REDUNDANCY_LOW (<0.80).
3. Feature Drift Foundation:
   - Evaluates chronological DEV partitions (DEV_EARLY, DEV_MIDDLE, DEV_LATE).
   - Computes Population Stability Index (PSI), Wasserstein distance, mean shift, and variance ratio.
4. Feature Perturbation Isolation:
   - Adversarially mutates single inputs (e.g. funding) and proves non-dependent features remain invariant.

Non-profitability invariant:
Zero P&L, Sharpe, win-rate, or target return optimization.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class FeatureDistributionStats:
    feature_name: str
    count: int
    missing_count: int
    finite_fraction: float
    minimum: Optional[float]
    maximum: Optional[float]
    median: Optional[float]
    p01: Optional[float]
    p05: Optional[float]
    p95: Optional[float]
    p99: Optional[float]
    mean: Optional[float]
    std: Optional[float]
    is_constant: bool
    has_infinities: bool
    has_nan: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeaturePairRedundancy:
    feature_a: str
    feature_b: str
    pearson_correlation: float
    spearman_rank_correlation: float
    redundancy_level: str  # REDUNDANCY_HIGH, REDUNDANCY_MODERATE, REDUNDANCY_LOW

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeatureDriftRecord:
    feature_name: str
    early_mean: Optional[float]
    late_mean: Optional[float]
    mean_shift: Optional[float]
    variance_ratio: Optional[float]
    psi: Optional[float]
    wasserstein_distance: Optional[float]
    drift_status: str  # STABLE, MODERATE_DRIFT, SIGNIFICANT_DRIFT

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FeatureDistributionAuditor:
    """Computes descriptive statistical distribution summaries on development data."""

    @staticmethod
    def _percentile(values: Sequence[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_v = sorted(values)
        idx = (len(sorted_v) - 1) * p
        lower = int(math.floor(idx))
        upper = int(math.ceil(idx))
        if lower == upper:
            return sorted_v[lower]
        weight = idx - lower
        return sorted_v[lower] * (1.0 - weight) + sorted_v[upper] * weight

    @classmethod
    def audit_series(cls, feature_name: str, values: Sequence[Optional[float]]) -> FeatureDistributionStats:
        n = len(values)
        if n == 0:
            return FeatureDistributionStats(
                feature_name=feature_name,
                count=0,
                missing_count=0,
                finite_fraction=1.0,
                minimum=None,
                maximum=None,
                median=None,
                p01=None,
                p05=None,
                p95=None,
                p99=None,
                mean=None,
                std=None,
                is_constant=False,
                has_infinities=False,
                has_nan=False,
            )

        valid_vals: List[float] = []
        missing_cnt = 0
        has_inf = False
        has_nan = False

        for v in values:
            if v is None:
                missing_cnt += 1
            elif isinstance(v, (int, float)):
                if math.isnan(v):
                    has_nan = True
                    missing_cnt += 1
                elif math.isinf(v):
                    has_inf = True
                    missing_cnt += 1
                else:
                    valid_vals.append(float(v))
            else:
                try:
                    vf = float(v)
                    if math.isnan(vf):
                        has_nan = True
                        missing_cnt += 1
                    elif math.isinf(vf):
                        has_inf = True
                        missing_cnt += 1
                    else:
                        valid_vals.append(vf)
                except (ValueError, TypeError):
                    missing_cnt += 1

        finite_frac = len(valid_vals) / n if n > 0 else 0.0
        if not valid_vals:
            return FeatureDistributionStats(
                feature_name=feature_name,
                count=0,
                missing_count=missing_cnt,
                finite_fraction=finite_frac,
                minimum=None,
                maximum=None,
                median=None,
                p01=None,
                p05=None,
                p95=None,
                p99=None,
                mean=None,
                std=None,
                is_constant=False,
                has_infinities=has_inf,
                has_nan=has_nan,
            )

        valid_cnt = len(valid_vals)
        mean_v = sum(valid_vals) / valid_cnt
        var_v = sum((x - mean_v) ** 2 for x in valid_vals) / valid_cnt
        std_v = math.sqrt(var_v)

        min_v = min(valid_vals)
        max_v = max(valid_vals)
        med_v = cls._percentile(valid_vals, 0.5)
        p01_v = cls._percentile(valid_vals, 0.01)
        p05_v = cls._percentile(valid_vals, 0.05)
        p95_v = cls._percentile(valid_vals, 0.95)
        p99_v = cls._percentile(valid_vals, 0.99)

        is_const = (max_v == min_v) or (std_v < 1e-12)

        return FeatureDistributionStats(
            feature_name=feature_name,
            count=valid_cnt,
            missing_count=missing_cnt,
            finite_fraction=round(finite_frac, 4),
            minimum=round(min_v, 6),
            maximum=round(max_v, 6),
            median=round(med_v, 6),
            p01=round(p01_v, 6),
            p05=round(p05_v, 6),
            p95=round(p95_v, 6),
            p99=round(p99_v, 6),
            mean=round(mean_v, 6),
            std=round(std_v, 6),
            is_constant=is_const,
            has_infinities=has_inf,
            has_nan=has_nan,
        )


class FeatureRedundancyAuditor:
    """Computes pairwise linear and rank correlation across feature series on DEV."""

    @staticmethod
    def _rank(vals: Sequence[float]) -> List[float]:
        n = len(vals)
        indexed = sorted(enumerate(vals), key=lambda x: x[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
                j += 1
            avg_rank = (i + j + 2.0) / 2.0
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    @classmethod
    def compute_pair_redundancy(
        cls,
        name_a: str,
        vals_a: Sequence[Optional[float]],
        name_b: str,
        vals_b: Sequence[Optional[float]],
    ) -> FeaturePairRedundancy:
        pairs: List[Tuple[float, float]] = []
        for a, b in zip(vals_a, vals_b):
            if a is not None and b is not None:
                try:
                    fa, fb = float(a), float(b)
                    if not (math.isnan(fa) or math.isnan(fb) or math.isinf(fa) or math.isinf(fb)):
                        pairs.append((fa, fb))
                except (ValueError, TypeError):
                    continue

        if len(pairs) < 10:
            return FeaturePairRedundancy(
                feature_a=name_a,
                feature_b=name_b,
                pearson_correlation=0.0,
                spearman_rank_correlation=0.0,
                redundancy_level="REDUNDANCY_LOW",
            )

        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        n = len(pairs)

        mx = sum(xs) / n
        my = sum(ys) / n
        vx = sum((x - mx) ** 2 for x in xs) / n
        vy = sum((y - my) ** 2 for y in ys) / n
        cov = sum((x - mx) * (y - my) for x, y in pairs) / n

        p_corr = cov / math.sqrt(vx * vy) if vx > 1e-16 and vy > 1e-16 else 0.0
        p_corr = max(-1.0, min(1.0, p_corr))

        # Spearman rank correlation
        rx = cls._rank(xs)
        ry = cls._rank(ys)
        mrx = sum(rx) / n
        mry = sum(ry) / n
        vrx = sum((r - mrx) ** 2 for r in rx) / n
        vry = sum((r - mry) ** 2 for r in ry) / n
        cov_r = sum((x - mrx) * (y - mry) for x, y in zip(rx, ry)) / n

        s_corr = cov_r / math.sqrt(vrx * vry) if vrx > 1e-16 and vry > 1e-16 else 0.0
        s_corr = max(-1.0, min(1.0, s_corr))

        max_abs = max(abs(p_corr), abs(s_corr))
        if max_abs >= 0.95:
            level = "REDUNDANCY_HIGH"
        elif max_abs >= 0.80:
            level = "REDUNDANCY_MODERATE"
        else:
            level = "REDUNDANCY_LOW"

        return FeaturePairRedundancy(
            feature_a=name_a,
            feature_b=name_b,
            pearson_correlation=round(p_corr, 4),
            spearman_rank_correlation=round(s_corr, 4),
            redundancy_level=level,
        )


class FeatureDriftAuditor:
    """Evaluates descriptive stability and distribution drift across chronological DEV intervals."""

    @staticmethod
    def _compute_psi(early: List[float], late: List[float], num_bins: int = 10) -> float:
        if not early or not late:
            return 0.0
        all_vals = sorted(early)
        quantiles = [all_vals[int(len(all_vals) * i / num_bins)] for i in range(1, num_bins)]
        bins = [-math.inf] + quantiles + [math.inf]

        psi = 0.0
        eps = 1e-4

        for i in range(len(bins) - 1):
            low, high = bins[i], bins[i + 1]
            e_cnt = sum(1 for x in early if low < x <= high)
            l_cnt = sum(1 for x in late if low < x <= high)

            e_pct = max(eps, e_cnt / len(early))
            l_pct = max(eps, l_cnt / len(late))

            psi += (l_pct - e_pct) * math.log(l_pct / e_pct)

        return max(0.0, psi)

    @staticmethod
    def _compute_wasserstein(early: List[float], late: List[float]) -> float:
        """1D Wasserstein metric computed via quantile integration."""
        if not early or not late:
            return 0.0
        s_early = sorted(early)
        s_late = sorted(late)
        n = 100
        dist = 0.0
        for i in range(n):
            p = (i + 0.5) / n
            q_e = s_early[int((len(s_early) - 1) * p)]
            q_l = s_late[int((len(s_late) - 1) * p)]
            dist += abs(q_e - q_l)
        return dist / n

    @classmethod
    def audit_chronological_drift(
        cls,
        feature_name: str,
        chronological_values: Sequence[Optional[float]],
    ) -> FeatureDriftRecord:
        clean: List[float] = []
        for v in chronological_values:
            if v is not None:
                try:
                    vf = float(v)
                    if not (math.isnan(vf) or math.isinf(vf)):
                        clean.append(vf)
                except (ValueError, TypeError):
                    continue
        n = len(clean)

        if n < 30:
            return FeatureDriftRecord(
                feature_name=feature_name,
                early_mean=None,
                late_mean=None,
                mean_shift=None,
                variance_ratio=None,
                psi=None,
                wasserstein_distance=None,
                drift_status="INSUFFICIENT_DATA",
            )

        third = n // 3
        early = clean[:third]
        late = clean[-third:]

        m_early = sum(early) / len(early)
        m_late = sum(late) / len(late)
        mean_shift = m_late - m_early

        var_early = sum((x - m_early) ** 2 for x in early) / len(early)
        var_late = sum((x - m_late) ** 2 for x in late) / len(late)
        var_ratio = var_late / var_early if var_early > 1e-12 else 1.0

        psi = cls._compute_psi(early, late)
        wass = cls._compute_wasserstein(early, late)

        if psi < 0.10:
            status = "STABLE"
        elif psi < 0.25:
            status = "MODERATE_DRIFT"
        else:
            status = "SIGNIFICANT_DRIFT"

        return FeatureDriftRecord(
            feature_name=feature_name,
            early_mean=round(m_early, 6),
            late_mean=round(m_late, 6),
            mean_shift=round(mean_shift, 6),
            variance_ratio=round(var_ratio, 4),
            psi=round(psi, 4),
            wasserstein_distance=round(wass, 6),
            drift_status=status,
        )


class FeaturePerturbationTester:
    """Verifies that features only change when their declared dependencies are mutated."""

    @staticmethod
    def verify_isolation(
        base_features: Dict[str, Any],
        mutated_features: Dict[str, Any],
        mutated_input: str,
        declared_dependents: Set[str],
    ) -> Tuple[bool, List[str]]:
        """Assert that features NOT in declared_dependents produce exact identical values."""
        violations: List[str] = []

        for feat_name, base_val in base_features.items():
            if feat_name in declared_dependents:
                continue
            mut_val = mutated_features.get(feat_name)
            if base_val != mut_val:
                violations.append(
                    f"LEAKAGE_DETECTED: Feature '{feat_name}' mutated when unrelated input '{mutated_input}' changed! "
                    f"Base={base_val}, Mutated={mut_val}"
                )

        return len(violations) == 0, violations
