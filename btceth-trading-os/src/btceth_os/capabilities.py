"""Research capability definitions and execution safety constraints for XAUUSDT.

Enforces:
- Separation of bar-level research from order-book depth research
- Rejection of fabricated quotes/fills (candle close != executable touch quote)
- Generation and enforcement of XAU_RESEARCH_CAPABILITY_MATRIX
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class CapabilityStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ResearchCapability:
    name: str
    status: CapabilityStatus
    allowed_for_research: bool
    reason: str
    constraints: list[str]


class ExecutionConstraintViolationError(RuntimeError):
    """Raised when an execution or research engine requests impossible quote/depth fills."""
    pass


DEFAULT_XAU_CAPABILITIES = {
    "BAR_DIRECTIONAL_RESEARCH": ResearchCapability(
        name="BAR_DIRECTIONAL_RESEARCH",
        status=CapabilityStatus.VERIFIED,
        allowed_for_research=True,
        reason="Checksum-verified 1m OHLCV contract klines available from 2026-01-06 with daily repair for 2026-06-29 gap.",
        constraints=[
            "Fills must assume conservative bar execution models; no touch/spread fills permitted.",
            "Candle close is not an executable touch quote.",
            "High/low difference must not be treated as a bid-ask spread.",
        ],
    ),
    "MARK_PRICE_RESEARCH": ResearchCapability(
        name="MARK_PRICE_RESEARCH",
        status=CapabilityStatus.VERIFIED,
        allowed_for_research=True,
        reason="Continuous 1m mark price klines available; off-hours smoothed with EWMA ±3% clamp.",
        constraints=["Mark price is used for liquidation and margin valuation, not direct taker fill price."],
    ),
    "INDEX_PRICE_RESEARCH": ResearchCapability(
        name="INDEX_PRICE_RESEARCH",
        status=CapabilityStatus.VERIFIED,
        allowed_for_research=True,
        reason="Continuous 1m index price klines available across all historical rule epochs.",
        constraints=["Index method reflects underlying reference feeds and changes across epochs."],
    ),
    "PREMIUM_INDEX_RESEARCH": ResearchCapability(
        name="PREMIUM_INDEX_RESEARCH",
        status=CapabilityStatus.VERIFIED,
        allowed_for_research=True,
        reason="Continuous 1m premium index klines available with zero/negative value support.",
        constraints=["Values can be zero or negative; numerical parser must use signed FinancialDecimal."],
    ),
    "FUNDING_RESEARCH": ResearchCapability(
        name="FUNDING_RESEARCH",
        status=CapabilityStatus.VERIFIED,
        allowed_for_research=True,
        reason="Realized funding events verified via monthly archives and live REST fallback.",
        constraints=["Funding interval shifts from 4h to 8h at 2026-01-30 12:15 UTC with cap/floor reduction."],
    ),
    "TRADE_PRINT_RESEARCH": ResearchCapability(
        name="TRADE_PRINT_RESEARCH",
        status=CapabilityStatus.VERIFIED,
        allowed_for_research=True,
        reason="Full trade tick stream verified via official monthly and daily archives.",
        constraints=["Pre-2026-01-06 trades remain quarantined."],
    ),
    "AGGTRADE_RESEARCH": ResearchCapability(
        name="AGGTRADE_RESEARCH",
        status=CapabilityStatus.VERIFIED,
        allowed_for_research=True,
        reason="Complete aggTrade stream verified via official archives with volume reconciliation to 1m klines.",
        constraints=["Aggregation combines simultaneous fills at identical price."],
    ),
    "BEST_BID_ASK_RESEARCH": ResearchCapability(
        name="BEST_BID_ASK_RESEARCH",
        status=CapabilityStatus.NOT_COMPUTABLE,
        allowed_for_research=False,
        reason="Binance public data vision archives do not publish tick bookTicker for XAUUSDT.",
        constraints=[
            "Historical best bid and best ask are completely unavailable in public archives.",
            "Strategies requiring top-of-book quotes cannot execute historical research.",
        ],
    ),
    "ORDERBOOK_DEPTH_RESEARCH": ResearchCapability(
        name="ORDERBOOK_DEPTH_RESEARCH",
        status=CapabilityStatus.NOT_COMPUTABLE,
        allowed_for_research=False,
        reason="Only coarse periodic percentage depth buckets exist; true L2/L3 order book snapshots and deltas are not published.",
        constraints=[
            "Percentage depth cannot reconstruct order book queue priority or market depth liquidity.",
            "Queue-position backtesting is blocked.",
        ],
    ),
    "SESSION_GAP_RESEARCH": ResearchCapability(
        name="SESSION_GAP_RESEARCH",
        status=CapabilityStatus.VERIFIED,
        allowed_for_research=True,
        reason="Distinct UnderlyingReferenceSession and PerpetualContractSession models separate underlying market closure from continuous contract trading.",
        constraints=["Underlying market closure does not excuse perpetual contract missing bars."],
    ),
    "RULE_EPOCH_REPLAY": ResearchCapability(
        name="RULE_EPOCH_REPLAY",
        status=CapabilityStatus.VERIFIED,
        allowed_for_research=True,
        reason="Source-backed ContractRuleEpochRegistry defines 7 verified historical epochs with primary-source hashes.",
        constraints=["Unknown historical fields are isolated and never backfilled from current snapshot."],
    ),
    "REALISTIC_FILL_RESEARCH": ResearchCapability(
        name="REALISTIC_FILL_RESEARCH",
        status=CapabilityStatus.NOT_COMPUTABLE,
        allowed_for_research=False,
        reason="Authentic executable touch quotes and orderbook depth deltas do not exist in historical archives.",
        constraints=[
            "Realistic fill simulation is strictly NOT_COMPUTABLE.",
            "No strategy may claim realistic historical fill edge on XAUUSDT from bar data alone.",
        ],
    ),
}


class ResearchCapabilityMatrix:
    def __init__(self, capabilities: dict[str, ResearchCapability] | None = None) -> None:
        self.capabilities = capabilities or dict(DEFAULT_XAU_CAPABILITIES)

    def assert_capability_allowed(self, capability_name: str) -> None:
        cap = self.capabilities.get(capability_name)
        if not cap:
            raise KeyError(f"Unknown research capability: {capability_name}")
        if not cap.allowed_for_research or cap.status in (CapabilityStatus.NOT_COMPUTABLE, CapabilityStatus.BLOCKED):
            raise ExecutionConstraintViolationError(
                f"Capability {capability_name} is {cap.status.value}: {cap.reason} Constraints: {cap.constraints}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
            "matrix_version": "1.0.0",
            "bar_level_research_ready": True,
            "orderbook_research_ready": False,
            "realistic_fills_ready": False,
            "capabilities": {
                name: {
                    "name": cap.name,
                    "status": cap.status.value,
                    "allowed_for_research": cap.allowed_for_research,
                    "reason": cap.reason,
                    "constraints": cap.constraints,
                }
                for name, cap in self.capabilities.items()
            },
        }

    def save_json(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
