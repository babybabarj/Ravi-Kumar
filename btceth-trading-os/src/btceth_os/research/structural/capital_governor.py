from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


class CapitalExhaustionError(RuntimeError):
    """Raised when capital or concurrency limits are exceeded under REJECT policy."""
    pass


@dataclass(frozen=True)
class CapitalPolicy:
    policy_name: str = "CANONICAL_V1"
    starting_equity: Decimal = Decimal("10000.0")
    max_gross_exposure_ratio: Decimal = Decimal("3.0")        # Max 3.0x gross notional
    max_strategy_allocation_ratio: Decimal = Decimal("1.0")   # Max fraction per single strategy
    perp_leverage: Decimal = Decimal("10.0")                  # 10x leverage -> 10% initial margin
    margin_buffer_ratio: Decimal = Decimal("0.05")            # 5% maintenance/volatility buffer
    reserve_cash_requirement: Decimal = Decimal("0.0")        # Explicit cash reserve floor
    max_concurrent_episodes: int = 5
    scale_down_enabled: bool = False                          # Strict default: SCALE_DOWN = DISABLED

    @property
    def perp_effective_margin_rate(self) -> Decimal:
        """Initial margin rate + maintenance buffer rate."""
        return (Decimal("1.0") / self.perp_leverage) + self.margin_buffer_ratio

    def compute_spot_perp_commitment(self, spot_notional: Decimal, perp_notional: Decimal) -> Decimal:
        """Derive explicit capital required for a spot+perp cash-and-carry trade.

        Capital = Spot cash (100% notional) + Perp margin (initial margin + buffer).
        Eliminates ungrounded magic multipliers.
        """
        perp_margin = perp_notional * self.perp_effective_margin_rate
        return spot_notional + perp_margin

    def compute_relative_pair_commitment(self, asset1_notional: Decimal, asset2_notional: Decimal) -> Decimal:
        """Derive explicit capital required for a 2-perp relative funding pair.

        Capital = Asset 1 perp margin + Asset 2 perp margin.
        """
        return (asset1_notional + asset2_notional) * self.perp_effective_margin_rate


@dataclass
class ActiveEpisodeCommitment:
    episode_id: str
    strategy_id: str
    entry_ts_ns: int
    exit_ts_ns: int
    committed_capital: Decimal
    gross_notional: Decimal


class PortfolioCapitalGovernor:
    """Canonical multi-strategy capital governor.

    Enforces portfolio equity preservation, explicit capital reservation,
    chronological timeline concurrency, and fail-closed capital exhaustion.
    """

    def __init__(self, policy: Optional[CapitalPolicy] = None) -> None:
        self.policy = policy or CapitalPolicy()
        self.starting_equity: Decimal = self.policy.starting_equity
        self.current_cash: Decimal = self.starting_equity
        self.active_commitments: dict[str, ActiveEpisodeCommitment] = {}
        self.timeline_log: list[dict] = []

    @property
    def total_committed_capital(self) -> Decimal:
        return sum((c.committed_capital for c in self.active_commitments.values()), Decimal("0"))

    @property
    def total_gross_notional(self) -> Decimal:
        return sum((c.gross_notional for c in self.active_commitments.values()), Decimal("0"))

    @property
    def available_capital(self) -> Decimal:
        avail = self.current_cash - self.total_committed_capital - self.policy.reserve_cash_requirement
        return max(Decimal("0"), avail)

    def can_allocate(self, required_capital: Decimal, gross_notional: Decimal, strategy_id: str) -> bool:
        # Check max concurrency
        if len(self.active_commitments) >= self.policy.max_concurrent_episodes:
            return False

        # Check available capital pool
        if required_capital > self.available_capital:
            return False

        # Check max gross exposure
        if (self.total_gross_notional + gross_notional) > (self.current_cash * self.policy.max_gross_exposure_ratio):
            return False

        # Check strategy-level concentration limit
        strat_committed = sum(
            (c.committed_capital for c in self.active_commitments.values() if c.strategy_id == strategy_id),
            Decimal("0"),
        )
        if (strat_committed + required_capital) > (self.current_cash * self.policy.max_strategy_allocation_ratio):
            return False

        return True

    def request_allocation(
        self,
        episode_id: str,
        strategy_id: str,
        entry_ts_ns: int,
        exit_ts_ns: int,
        required_capital: Decimal,
        gross_notional: Decimal,
    ) -> Decimal:
        """Request capital allocation. Fails closed with CapitalExhaustionError if unavailable."""
        if not self.can_allocate(required_capital, gross_notional, strategy_id):
            if not self.policy.scale_down_enabled:
                raise CapitalExhaustionError(
                    f"CAPITAL_EXHAUSTION: Cannot allocate ${required_capital} to {episode_id} ({strategy_id}). "
                    f"Available: ${self.available_capital}, Active Episodes: {len(self.active_commitments)}"
                )
            # If scale-down is authorized by policy, proportionally scale down
            alloc = min(required_capital, self.available_capital)
            if alloc <= Decimal("0"):
                raise CapitalExhaustionError("CAPITAL_EXHAUSTION: Available capital is zero.")
            actual_alloc = alloc
        else:
            actual_alloc = required_capital

        self.active_commitments[episode_id] = ActiveEpisodeCommitment(
            episode_id=episode_id,
            strategy_id=strategy_id,
            entry_ts_ns=entry_ts_ns,
            exit_ts_ns=exit_ts_ns,
            committed_capital=actual_alloc,
            gross_notional=gross_notional,
        )

        self.timeline_log.append({
            "event": "ALLOCATE",
            "ts_ns": entry_ts_ns,
            "episode_id": episode_id,
            "allocated": str(actual_alloc),
            "committed_total": str(self.total_committed_capital),
            "available": str(self.available_capital),
        })
        return actual_alloc

    def close_episode(self, episode_id: str, exit_ts_ns: int, net_pnl: Decimal = Decimal("0")) -> None:
        """Explicitly close an episode, release its committed capital, and credit net P&L."""
        if episode_id in self.active_commitments:
            comm = self.active_commitments.pop(episode_id)
            self.current_cash += net_pnl
            self.timeline_log.append({
                "event": "CLOSE",
                "ts_ns": exit_ts_ns,
                "episode_id": episode_id,
                "released": str(comm.committed_capital),
                "net_pnl": str(net_pnl),
                "new_cash": str(self.current_cash),
                "available": str(self.available_capital),
            })
