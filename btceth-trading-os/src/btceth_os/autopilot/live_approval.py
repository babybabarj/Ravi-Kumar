from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any


class ProposalStatus(StrEnum):
    AWAITING_OWNER_APPROVAL = "AWAITING_OWNER_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


@dataclass
class TradeProposal:
    proposal_id: str
    instrument: str
    market: str
    side: str
    entry_type: str
    proposed_quantity: Decimal
    notional: Decimal
    current_price: Decimal
    stop_price: Decimal
    targets: str
    max_expected_loss: Decimal
    estimated_fees: Decimal
    estimated_funding: Decimal
    estimated_slippage: Decimal
    strategy_id: str
    strategy_version: str
    market_regime: str
    reason: str
    signal_ts_ns: int
    created_at_ns: int
    expires_at_ns: int
    status: ProposalStatus = ProposalStatus.AWAITING_OWNER_APPROVAL

    def is_expired(self, now_ns: int) -> bool:
        return now_ns >= self.expires_at_ns

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = format(v, "f")
        return d


class MockExecutionAdapter:
    """In-memory mock adapter used strictly in testing to verify approval routing."""

    def __init__(self) -> None:
        self.dispatched_proposals: list[TradeProposal] = []

    def dispatch_mock_order(self, proposal: TradeProposal) -> str:
        self.dispatched_proposals.append(proposal)
        return f"MOCK_DISPATCH_{proposal.proposal_id}"


class LiveApprovalGate:
    """Approval gate for future real-money mode. Never submits live orders during this wave."""

    def __init__(self, default_ttl_seconds: int = 120) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self.proposals: dict[str, TradeProposal] = {}
        self.mock_adapter = MockExecutionAdapter()

    def generate_proposal(
        self,
        *,
        instrument: str,
        market: str,
        side: str,
        entry_type: str,
        proposed_quantity: Decimal,
        current_price: Decimal,
        stop_price: Decimal,
        targets_str: str,
        max_expected_loss: Decimal,
        estimated_fees: Decimal,
        estimated_funding: Decimal,
        estimated_slippage: Decimal,
        strategy_id: str,
        strategy_version: str,
        market_regime: str,
        reason: str,
        signal_ts_ns: int,
        now_ns: int,
        ttl_seconds: int | None = None,
    ) -> TradeProposal:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expires_at = now_ns + (ttl * 1_000_000_000)
        seed = f"{instrument}:{side}:{proposed_quantity}:{current_price}:{signal_ts_ns}"
        prop_id = hashlib.sha256(seed.encode()).hexdigest()[:16]

        proposal = TradeProposal(
            proposal_id=prop_id,
            instrument=instrument,
            market=market,
            side=side,
            entry_type=entry_type,
            proposed_quantity=proposed_quantity,
            notional=proposed_quantity * current_price,
            current_price=current_price,
            stop_price=stop_price,
            targets=targets_str,
            max_expected_loss=max_expected_loss,
            estimated_fees=estimated_fees,
            estimated_funding=estimated_funding,
            estimated_slippage=estimated_slippage,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            market_regime=market_regime,
            reason=reason,
            signal_ts_ns=signal_ts_ns,
            created_at_ns=now_ns,
            expires_at_ns=expires_at,
        )
        self.proposals[prop_id] = proposal
        return proposal

    def approve(self, proposal_id: str, now_ns: int) -> tuple[bool, str]:
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            return False, "PROPOSAL_NOT_FOUND"

        if proposal.status != ProposalStatus.AWAITING_OWNER_APPROVAL:
            return False, f"PROPOSAL_ALREADY_{proposal.status.value}"

        if proposal.is_expired(now_ns):
            proposal.status = ProposalStatus.EXPIRED
            return False, "APPROVAL_EXPIRED"

        proposal.status = ProposalStatus.APPROVED
        # Route to mock adapter only
        self.mock_adapter.dispatch_mock_order(proposal)
        return True, "APPROVED_MOCK_DISPATCHED"

    def reject(self, proposal_id: str, now_ns: int, reason: str = "MANUAL_REJECT") -> tuple[bool, str]:
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            return False, "PROPOSAL_NOT_FOUND"
        proposal.status = ProposalStatus.REJECTED
        return True, "PROPOSAL_REJECTED"

    def get_pending(self, now_ns: int) -> list[TradeProposal]:
        out = []
        for p in self.proposals.values():
            if p.status == ProposalStatus.AWAITING_OWNER_APPROVAL:
                if p.is_expired(now_ns):
                    p.status = ProposalStatus.EXPIRED
                else:
                    out.append(p)
        return out
