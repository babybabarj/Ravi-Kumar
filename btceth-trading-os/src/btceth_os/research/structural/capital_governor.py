from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional, Union


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_POLICY_PATH = ROOT / "config" / "research_capital_policy_v1.yaml"
CANONICAL_CAPITAL_POLICY_PATH = DEFAULT_POLICY_PATH


def get_canonical_policy_sha256(path: Union[str, Path, None] = None) -> str:
    """Compute and return the SHA-256 digest of the canonical capital policy YAML."""
    p = Path(path) if path is not None else CANONICAL_CAPITAL_POLICY_PATH
    if not p.is_file():
        raise FileNotFoundError(f"CAPITAL_POLICY_MISSING: Canonical policy file not found at {p}")
    return hashlib.sha256(p.read_bytes()).hexdigest()

MANDATORY_POLICY_FIELDS = (
    "starting_equity",
    "max_gross_exposure_ratio",
    "max_strategy_allocation_ratio",
    "perp_leverage",
    "margin_buffer_ratio",
    "reserve_cash_requirement",
    "max_concurrent_episodes",
    "scale_down_enabled",
)


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

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate all policy bounds; fail closed on invalid or insecure parameters."""
        if not isinstance(self.starting_equity, Decimal) or self.starting_equity.is_nan() or self.starting_equity.is_infinite() or self.starting_equity <= Decimal("0"):
            raise ValueError("CAPITAL_POLICY_INVALID: starting_equity must be a finite positive Decimal")
        if not isinstance(self.max_gross_exposure_ratio, Decimal) or self.max_gross_exposure_ratio <= Decimal("0"):
            raise ValueError("CAPITAL_POLICY_INVALID: max_gross_exposure_ratio must be positive")
        if not isinstance(self.max_strategy_allocation_ratio, Decimal) or not (Decimal("0") < self.max_strategy_allocation_ratio <= Decimal("1.0")):
            raise ValueError("CAPITAL_POLICY_INVALID: max_strategy_allocation_ratio must be in (0.0, 1.0]")
        if not isinstance(self.perp_leverage, Decimal) or self.perp_leverage < Decimal("1.0"):
            raise ValueError("CAPITAL_POLICY_INVALID: perp_leverage must be >= 1.0")
        if not isinstance(self.margin_buffer_ratio, Decimal) or not (Decimal("0") <= self.margin_buffer_ratio < Decimal("1.0")):
            raise ValueError("CAPITAL_POLICY_INVALID: margin_buffer_ratio must be in [0.0, 1.0)")
        if not isinstance(self.reserve_cash_requirement, Decimal) or self.reserve_cash_requirement < Decimal("0"):
            raise ValueError("CAPITAL_POLICY_INVALID: reserve_cash_requirement cannot be negative")
        if self.reserve_cash_requirement >= self.starting_equity:
            raise ValueError("CAPITAL_POLICY_INVALID: reserve_cash_requirement must be strictly less than starting_equity")
        if not isinstance(self.max_concurrent_episodes, int) or self.max_concurrent_episodes < 1:
            raise ValueError("CAPITAL_POLICY_INVALID: max_concurrent_episodes must be an integer >= 1")
        if self.scale_down_enabled is not False:
            raise ValueError("CAPITAL_POLICY_INVALID: scale_down_enabled must be strictly False in research mode")

    @classmethod
    def from_yaml(cls, path: Union[str, Path], scenario: str = "BASE_RESEARCH_POLICY") -> CapitalPolicy:
        """Load capital policy configuration from a YAML policy file with strict schema validation."""
        import yaml
        yaml_path = Path(path)
        if not yaml_path.is_file():
            raise ValueError(f"CAPITAL_POLICY_INVALID: Policy file not found: {yaml_path}")
        
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ValueError(f"CAPITAL_POLICY_INVALID: Failed to parse YAML file: {e}")

        if not isinstance(data, dict):
            raise ValueError("CAPITAL_POLICY_INVALID: Policy file root must be a YAML dictionary")

        if scenario not in data:
            raise ValueError(f"CAPITAL_POLICY_INVALID: Scenario '{scenario}' not found in policy file")

        scen = data[scenario]
        if not isinstance(scen, dict):
            raise ValueError(f"CAPITAL_POLICY_INVALID: Scenario '{scenario}' must be a dictionary")

        for field in MANDATORY_POLICY_FIELDS:
            if field not in scen:
                raise ValueError(f"CAPITAL_POLICY_INVALID: Missing mandatory field '{field}' in policy '{scenario}'")

        return cls(
            policy_name=scen.get("label", scenario),
            starting_equity=Decimal(str(scen["starting_equity"])),
            max_gross_exposure_ratio=Decimal(str(scen["max_gross_exposure_ratio"])),
            max_strategy_allocation_ratio=Decimal(str(scen["max_strategy_allocation_ratio"])),
            perp_leverage=Decimal(str(scen["perp_leverage"])),
            margin_buffer_ratio=Decimal(str(scen["margin_buffer_ratio"])),
            reserve_cash_requirement=Decimal(str(scen["reserve_cash_requirement"])),
            max_concurrent_episodes=int(scen["max_concurrent_episodes"]),
            scale_down_enabled=bool(scen["scale_down_enabled"]),
        )

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
    Defaults to loading config/research_capital_policy_v1.yaml (BASE_RESEARCH_POLICY).
    """

    get_canonical_policy_sha256 = staticmethod(get_canonical_policy_sha256)

    def __init__(self, policy: Optional[CapitalPolicy] = None) -> None:
        if policy is None:
            if not CANONICAL_CAPITAL_POLICY_PATH.is_file():
                raise FileNotFoundError(f"CAPITAL_POLICY_MISSING: Canonical capital policy not found at {CANONICAL_CAPITAL_POLICY_PATH}")
            self.policy = CapitalPolicy.from_yaml(CANONICAL_CAPITAL_POLICY_PATH, scenario="BASE_RESEARCH_POLICY")
        else:
            self.policy = policy
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
        if not episode_id or not isinstance(episode_id, str) or not episode_id.strip():
            raise ValueError("episode_id must be a non-empty string")
        if not strategy_id or not isinstance(strategy_id, str) or not strategy_id.strip():
            raise ValueError("strategy_id must be a non-empty string")
        if entry_ts_ns < 0:
            raise ValueError("entry_ts_ns cannot be negative")
        if exit_ts_ns <= entry_ts_ns:
            raise ValueError(f"exit_ts_ns ({exit_ts_ns}) must be strictly greater than entry_ts_ns ({entry_ts_ns})")
        if not isinstance(required_capital, Decimal) or required_capital.is_nan() or required_capital.is_infinite() or required_capital <= Decimal("0"):
            raise ValueError("required_capital must be a finite positive Decimal")
        if not isinstance(gross_notional, Decimal) or gross_notional.is_nan() or gross_notional.is_infinite() or gross_notional <= Decimal("0"):
            raise ValueError("gross_notional must be a finite positive Decimal")

        if episode_id in self.active_commitments:
            raise CapitalExhaustionError(f"DUPLICATE_EPISODE_ID: Episode ID '{episode_id}' is already active in capital governor")

        if not self.can_allocate(required_capital, gross_notional, strategy_id):
            if self.policy.scale_down_enabled:
                raise NotImplementedError("SCALE_DOWN_UNSUPPORTED: Fractional scale-down is disabled in research mode; reject or accept fully")
            raise CapitalExhaustionError(
                f"CAPITAL_EXHAUSTION: Cannot allocate ${required_capital} to {episode_id} ({strategy_id}). "
                f"Available: ${self.available_capital}, Active Episodes: {len(self.active_commitments)}"
            )

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
        if not episode_id or not isinstance(episode_id, str) or not episode_id.strip():
            raise ValueError("episode_id must be a non-empty string")
        if episode_id not in self.active_commitments:
            raise KeyError(f"UNKNOWN_EPISODE: Cannot release commitment for untracked episode ID '{episode_id}'")
        if not isinstance(net_pnl, Decimal) or net_pnl.is_nan() or net_pnl.is_infinite():
            raise ValueError(f"net_pnl must be a finite Decimal, got {net_pnl} (type: {type(net_pnl).__name__})")

        comm = self.active_commitments[episode_id]
        if exit_ts_ns < comm.entry_ts_ns:
            raise ValueError(f"Chronology violation: exit_ts_ns ({exit_ts_ns}) must be >= entry_ts_ns ({comm.entry_ts_ns})")

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
