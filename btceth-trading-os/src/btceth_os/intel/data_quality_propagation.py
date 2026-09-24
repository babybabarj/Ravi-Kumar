"""Layer E: Data Quality Propagation Engine for INTEL-1B.

Enforces fail-closed downstream propagation of data quality states into intelligence regimes:
- GOOD: Intelligence computation allowed; standard uncertainty classification.
- DEGRADED: Intelligence computation allowed with explicit warnings propagated to uncertainties.
- UNRELIABLE: Downstream market regimes are forced to UNKNOWN / UNCERTAIN; zero confident classification.
- UNKNOWN: Downstream market regimes are forced to UNKNOWN / UNCERTAIN; zero confident classification.
"""

from __future__ import annotations

from typing import List, Optional

from .data_quality import BarDataQualityAssessment, DataQualityStatus
from .market_state import (
    FundingRegime,
    LiquidityActivityRegime,
    MarketQualityRegime,
    MarketStateSnapshot,
    TrendRegime,
    VolatilityRegime,
)


class DataQualityPropagationEngine:
    """Propagates upstream data quality assessments through market intelligence states."""

    @classmethod
    def propagate(
        cls,
        assessment: BarDataQualityAssessment,
        raw_state: MarketStateSnapshot,
    ) -> MarketStateSnapshot:
        """Apply deterministic propagation rules to ensure corrupted data never yields false certainty."""
        status = assessment.status

        if status == DataQualityStatus.GOOD.value:
            # Good quality: preserve computed state
            return raw_state

        if status == DataQualityStatus.DEGRADED.value:
            # Degraded: preserve state but inject quality warnings into uncertainties
            merged_uncertainties = sorted(
                set(raw_state.uncertainties + assessment.reasons + ["DATA_QUALITY_DEGRADED"])
            )
            return MarketStateSnapshot(
                trend_state=raw_state.trend_state,
                volatility_state=raw_state.volatility_state,
                activity_state=raw_state.activity_state,
                funding_state=raw_state.funding_state,
                market_quality_state=MarketQualityRegime.DEGRADED.value,
                uncertainties=merged_uncertainties,
            )

        # UNRELIABLE or UNKNOWN: Fail-closed override. All regimes become unknown/uncertain.
        reasons = assessment.reasons or [f"DATA_QUALITY_{status}"]
        override_uncertainties = sorted(
            set(raw_state.uncertainties + reasons + [f"PROPAGATED_FAIL_CLOSED_{status}"])
        )
        return MarketStateSnapshot(
            trend_state=TrendRegime.UNCERTAIN.value,
            volatility_state=VolatilityRegime.UNKNOWN.value,
            activity_state=LiquidityActivityRegime.UNKNOWN.value,
            funding_state=FundingRegime.UNKNOWN.value,
            market_quality_state=(
                MarketQualityRegime.UNRELIABLE.value
                if status == DataQualityStatus.UNRELIABLE.value
                else MarketQualityRegime.UNKNOWN.value
            ),
            uncertainties=override_uncertainties,
        )
