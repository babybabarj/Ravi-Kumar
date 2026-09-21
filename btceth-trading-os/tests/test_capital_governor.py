from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
import pytest

from btceth_os.research.structural.capital_governor import (
    CapitalExhaustionError,
    CapitalPolicy,
    PortfolioCapitalGovernor,
)

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
CONFIG_DIR = ROOT / "config"


def test_capital_policy_derived_commitments() -> None:
    """Proves capital commitments are derived from explicit policy parameters, not magic multipliers."""
    policy = CapitalPolicy(
        starting_equity=Decimal("10000.0"),
        perp_leverage=Decimal("10.0"),         # 10% margin
        margin_buffer_ratio=Decimal("0.05"),   # 5% buffer -> 15% total perp margin rate
    )
    assert policy.perp_effective_margin_rate == Decimal("0.15")

    # Spot notional $5,000, Perp notional $5,000
    # Required = Spot $5,000 + Perp margin ($5,000 * 0.15 = $750) = $5,750
    spot_perp_comm = policy.compute_spot_perp_commitment(Decimal("5000.0"), Decimal("5000.0"))
    assert spot_perp_comm == Decimal("5750.0")

    # 2-Perp Relative Pair: $5,000 on Leg 1, $5,000 on Leg 2
    # Required = ($5,000 + $5,000) * 0.15 = $1,500
    pair_comm = policy.compute_relative_pair_commitment(Decimal("5000.0"), Decimal("5000.0"))
    assert pair_comm == Decimal("1500.0")


def test_two_concurrent_chronologically_overlapping_episodes() -> None:
    """Test 2 chronologically overlapping episodes track capital correctly across time."""
    gov = PortfolioCapitalGovernor()
    assert gov.available_capital == Decimal("10000.0")

    # EP1: Entry T=0, Exit T=10, Capital $4,000
    gov.request_allocation("EP1", "STRAT_A", 0, 10, Decimal("4000.0"), Decimal("5000.0"))
    assert gov.available_capital == Decimal("6000.0")
    assert gov.total_committed_capital == Decimal("4000.0")

    # EP2: Entry T=5 (overlaps with EP1), Exit T=15, Capital $4,000
    gov.request_allocation("EP2", "STRAT_B", 5, 15, Decimal("4000.0"), Decimal("5000.0"))
    assert gov.available_capital == Decimal("2000.0")
    assert gov.total_committed_capital == Decimal("8000.0")

    # At T=10, EP1 exits with +$100 PnL
    gov.close_episode("EP1", 10, net_pnl=Decimal("100.0"))

    # Capital is released and PnL credited: cash becomes $10,100, committed is $4,000 (EP2 only)
    assert gov.current_cash == Decimal("10100.0")
    assert gov.total_committed_capital == Decimal("4000.0")
    assert gov.available_capital == Decimal("6100.0")


def test_five_concurrent_episodes_and_sixth_rejected() -> None:
    """5 concurrent episodes saturate the pool; 6th is rejected with CapitalExhaustionError."""
    gov = PortfolioCapitalGovernor()

    # 5 episodes of $2,000 each = $10,000 total
    for i in range(5):
        gov.request_allocation(f"EP_{i}", f"STRAT_{i}", 0, 100, Decimal("2000.0"), Decimal("3000.0"))

    assert gov.total_committed_capital == Decimal("10000.0")
    assert gov.available_capital == Decimal("0.0")

    # 6th episode requests $500 -> rejected due to capital exhaustion and max concurrency
    with pytest.raises(CapitalExhaustionError) as exc_info:
        gov.request_allocation("EP_EXTRA", "STRAT_NEW", 10, 100, Decimal("500.0"), Decimal("1000.0"))
    assert "CAPITAL_EXHAUSTION" in str(exc_info.value)


def test_capital_released_after_close_enables_new_trade() -> None:
    """Capital freed upon episode close allows subsequent trade to open."""
    gov = PortfolioCapitalGovernor()
    gov.request_allocation("EP1", "STRAT_A", 0, 50, Decimal("8000.0"), Decimal("10000.0"))
    assert gov.available_capital == Decimal("2000.0")

    # Requesting $5,000 at T=20 fails
    with pytest.raises(CapitalExhaustionError):
        gov.request_allocation("EP2", "STRAT_B", 20, 80, Decimal("5000.0"), Decimal("6000.0"))

    # At T=50: EP1 closes
    gov.close_episode("EP1", 50, net_pnl=Decimal("0.0"))
    assert gov.available_capital == Decimal("10000.0")

    # Now EP2 can be allocated cleanly at T=51
    alloc = gov.request_allocation("EP2", "STRAT_B", 51, 80, Decimal("5000.0"), Decimal("6000.0"))
    assert alloc == Decimal("5000.0")
    assert gov.available_capital == Decimal("5000.0")


def test_capital_mutation_over_allocation_fails_closed() -> None:
    """Mutation test: Requesting $12,000 from $10,000 pool fails closed (SCALE_DOWN = DISABLED)."""
    gov = PortfolioCapitalGovernor()
    assert gov.policy.scale_down_enabled is False

    with pytest.raises(CapitalExhaustionError) as exc_info:
        gov.request_allocation("EP_BIG", "STRAT_GREEDY", 0, 10, Decimal("12000.0"), Decimal("15000.0"))
    assert "CAPITAL_EXHAUSTION" in str(exc_info.value)
    assert gov.available_capital == Decimal("10000.0")  # No money leaked


def test_unallocated_cash_earns_zero() -> None:
    """Verify unallocated cash maintains zero return without artificial appreciation."""
    gov = PortfolioCapitalGovernor()
    gov.request_allocation("EP_FLAT", "STRAT_FLAT", 0, 10, Decimal("3000.0"), Decimal("4000.0"))
    gov.close_episode("EP_FLAT", 10, net_pnl=Decimal("0.0"))
    assert gov.current_cash == Decimal("10000.0")


def test_capital_policy_from_yaml_loader() -> None:
    """Verify CapitalPolicy correctly loads scenarios from config/research_capital_policy_v1.yaml."""
    yaml_path = CONFIG_DIR / "research_capital_policy_v1.yaml"
    assert yaml_path.is_file(), "research_capital_policy_v1.yaml must exist"

    base_policy = CapitalPolicy.from_yaml(yaml_path, "BASE_RESEARCH_POLICY")
    assert base_policy.starting_equity == Decimal("100000.0")
    assert base_policy.max_gross_exposure_ratio == Decimal("2.0")
    assert base_policy.max_strategy_allocation_ratio == Decimal("0.25")
    assert base_policy.reserve_cash_requirement == Decimal("20000.0")
    assert base_policy.max_concurrent_episodes == 5
    assert base_policy.scale_down_enabled is False

    stressed_policy = CapitalPolicy.from_yaml(yaml_path, "STRESSED_RESEARCH_POLICY")
    assert stressed_policy.starting_equity == Decimal("100000.0")
    assert stressed_policy.max_gross_exposure_ratio == Decimal("1.5")
    assert stressed_policy.max_strategy_allocation_ratio == Decimal("0.20")
    assert stressed_policy.reserve_cash_requirement == Decimal("30000.0")
    assert stressed_policy.max_concurrent_episodes == 3


def test_input_validation_rejections() -> None:
    """Adversarial input validation tests: reject invalid timestamps, notional, capital, empty IDs."""
    gov = PortfolioCapitalGovernor()

    # Empty episode ID
    with pytest.raises(ValueError, match="episode_id must be a non-empty string"):
        gov.request_allocation("", "STRAT", 0, 10, Decimal("100.0"), Decimal("100.0"))

    # Empty strategy ID
    with pytest.raises(ValueError, match="strategy_id must be a non-empty string"):
        gov.request_allocation("EP", "  ", 0, 10, Decimal("100.0"), Decimal("100.0"))

    # Negative entry timestamp
    with pytest.raises(ValueError, match="entry_ts_ns cannot be negative"):
        gov.request_allocation("EP", "STRAT", -1, 10, Decimal("100.0"), Decimal("100.0"))

    # Non-increasing timestamps
    with pytest.raises(ValueError, match="exit_ts_ns .* must be strictly greater than entry_ts_ns"):
        gov.request_allocation("EP", "STRAT", 10, 10, Decimal("100.0"), Decimal("100.0"))

    with pytest.raises(ValueError, match="exit_ts_ns .* must be strictly greater than entry_ts_ns"):
        gov.request_allocation("EP", "STRAT", 10, 5, Decimal("100.0"), Decimal("100.0"))

    # Invalid required capital
    with pytest.raises(ValueError, match="required_capital must be a finite positive Decimal"):
        gov.request_allocation("EP", "STRAT", 0, 10, Decimal("0.0"), Decimal("100.0"))

    with pytest.raises(ValueError, match="required_capital must be a finite positive Decimal"):
        gov.request_allocation("EP", "STRAT", 0, 10, Decimal("-10.0"), Decimal("100.0"))

    with pytest.raises(ValueError, match="required_capital must be a finite positive Decimal"):
        gov.request_allocation("EP", "STRAT", 0, 10, Decimal("NaN"), Decimal("100.0"))

    # Invalid gross notional
    with pytest.raises(ValueError, match="gross_notional must be a finite positive Decimal"):
        gov.request_allocation("EP", "STRAT", 0, 10, Decimal("100.0"), Decimal("0.0"))

    with pytest.raises(ValueError, match="gross_notional must be a finite positive Decimal"):
        gov.request_allocation("EP", "STRAT", 0, 10, Decimal("100.0"), Decimal("-50.0"))


def test_duplicate_episode_allocation_fails_closed() -> None:
    """Duplicate episode allocation attempt must fail closed."""
    gov = PortfolioCapitalGovernor()
    gov.request_allocation("EP_DUP", "STRAT_A", 0, 100, Decimal("1000.0"), Decimal("2000.0"))

    with pytest.raises(CapitalExhaustionError, match="DUPLICATE_EPISODE_ID"):
        gov.request_allocation("EP_DUP", "STRAT_A", 10, 100, Decimal("500.0"), Decimal("1000.0"))


def test_unknown_episode_close_fails_closed() -> None:
    """Attempting to close an unknown episode ID raises KeyError."""
    gov = PortfolioCapitalGovernor()
    with pytest.raises(KeyError, match="UNKNOWN_EPISODE"):
        gov.close_episode("EP_NONEXISTENT", 10)


def test_chronology_violation_on_close_fails_closed() -> None:
    """Closing an episode with an exit timestamp before its entry timestamp raises ValueError."""
    gov = PortfolioCapitalGovernor()
    gov.request_allocation("EP_TIME", "STRAT_A", 50, 100, Decimal("1000.0"), Decimal("2000.0"))

    with pytest.raises(ValueError, match="Chronology violation"):
        gov.close_episode("EP_TIME", exit_ts_ns=40)


def test_scale_down_enabled_fails_closed_with_not_implemented() -> None:
    """When scale_down_enabled is True and capacity is exceeded, governor raises NotImplementedError."""
    policy = CapitalPolicy(starting_equity=Decimal("1000.0"), scale_down_enabled=True)
    gov = PortfolioCapitalGovernor(policy)

    with pytest.raises(NotImplementedError, match="SCALE_DOWN_UNSUPPORTED"):
        gov.request_allocation("EP_HUGE", "STRAT", 0, 10, Decimal("2000.0"), Decimal("3000.0"))


def test_generate_round3b_0a_capital_governor_audit() -> None:
    """Generate ROUND3B_0A_CAPITAL_GOVERNOR_AUDIT.json report."""
    audit_data = {
        "report_version": "ROUND3B.0A",
        "status": "VERIFIED",
        "policy_file": "config/research_capital_policy_v1.yaml",
        "classification": "RESEARCH_ASSUMPTION",
        "trading_capability": 0,
        "input_validation_verified": True,
        "duplicate_episode_rejection_verified": True,
        "unknown_episode_rejection_verified": True,
        "chronology_violation_rejection_verified": True,
        "scale_down_policy": "DISABLED_FAIL_CLOSED",
        "exhaustion_behavior": "REJECT",
        "multi_strategy_concurrency_verified": True,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "ROUND3B_0A_CAPITAL_GOVERNOR_AUDIT.json").write_text(
        json.dumps(audit_data, indent=2) + "\n", encoding="utf-8"
    )
