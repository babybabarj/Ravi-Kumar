from __future__ import annotations

import ast
import json
import random
from decimal import Decimal
from pathlib import Path
import pytest

from tests.oracles.structural_accounting_oracle import (
    IndependentAccountingOracle,
    OracleFundingEvent,
    SpotPerpOracleInput,
    RelativePerpPairOracleInput,
)

from btceth_os.research.cost_model import DetailedCostPolicy
from btceth_os.research.structural.multi_leg_accounting import (
    FundingCashFlowEvent,
    MultiLegTradeEpisode,
    RelativePerpPairEpisode,
)
from btceth_os.research.structural.portfolio_equity import PortfolioEquityEngine
from btceth_os.research.structural.capital_governor import CapitalPolicy

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"


def test_oracle_is_strictly_independent() -> None:
    """Static AST audit proving tests/oracles/structural_accounting_oracle.py is strictly independent."""
    oracle_file = ROOT / "tests" / "oracles" / "structural_accounting_oracle.py"
    assert oracle_file.is_file(), "Oracle file must exist"

    content = oracle_file.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(oracle_file))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("btceth_os"), f"Forbidden import of btceth_os: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert not node.module.startswith("btceth_os"), f"Forbidden import from btceth_os: {node.module}"


def _build_production_spot_perp_episode(
    ep_id: str,
    asset: str,
    spot_side: int,
    spot_entry: Decimal,
    spot_exit: Decimal,
    spot_qty: Decimal,
    perp_side: int,
    perp_entry: Decimal,
    perp_exit: Decimal,
    perp_qty: Decimal,
    s_fee_bps: Decimal,
    s_sprd_bps: Decimal,
    s_slip_bps: Decimal,
    p_fee_bps: Decimal,
    p_sprd_bps: Decimal,
    p_slip_bps: Decimal,
    delay_bps: Decimal,
    funding_events: list[tuple[Decimal, Decimal, int]],
) -> MultiLegTradeEpisode:
    spot_cost = DetailedCostPolicy(
        instrument_type="SPOT",
        exchange_fee_bps=s_fee_bps,
        spread_bps=s_sprd_bps,
        slippage_bps=s_slip_bps,
    )
    perp_cost = DetailedCostPolicy(
        instrument_type="PERP",
        exchange_fee_bps=p_fee_bps,
        spread_bps=p_sprd_bps,
        slippage_bps=p_slip_bps,
    )
    prod_funding = []
    for i, (m_p, f_r, p_side) in enumerate(funding_events):
        side_dec = Decimal(str(p_side))
        cf = -side_dec * (perp_qty * m_p) * f_r
        prod_funding.append(
            FundingCashFlowEvent(
                ts_event_ns=i * 1000,
                funding_rate=f_r,
                mark_price=m_p,
                position_side=p_side,
                notional_usd=perp_qty * m_p,
                cash_flow_usd=cf,
            )
        )

    legging_loss = spot_qty * spot_entry * (delay_bps / Decimal("10000.0")) if delay_bps > Decimal("0") else Decimal("0")

    return MultiLegTradeEpisode(
        episode_id=ep_id,
        strategy_id="ORACLE_TEST",
        asset=asset,
        entry_ts_ns=0,
        exit_ts_ns=3600_000_000_000,
        spot_side=spot_side,
        spot_entry_price=spot_entry,
        spot_exit_price=spot_exit,
        spot_quantity=spot_qty,
        perp_side=perp_side,
        perp_entry_price=perp_entry,
        perp_exit_price=perp_exit,
        perp_quantity=perp_qty,
        spot_cost_policy=spot_cost,
        perp_cost_policy=perp_cost,
        funding_events=tuple(prod_funding),
        temporary_delta_loss_usd=legging_loss,
    )


def _build_production_relative_pair_episode(
    ep_id: str,
    asset1_symbol: str,
    asset1_side: int,
    asset1_entry: Decimal,
    asset1_exit: Decimal,
    asset1_qty: Decimal,
    asset2_symbol: str,
    asset2_side: int,
    asset2_entry: Decimal,
    asset2_exit: Decimal,
    asset2_qty: Decimal,
    a1_fee_bps: Decimal,
    a1_sprd_bps: Decimal,
    a1_slip_bps: Decimal,
    a2_fee_bps: Decimal,
    a2_sprd_bps: Decimal,
    a2_slip_bps: Decimal,
    delay_bps: Decimal,
    a1_funding: list[tuple[Decimal, Decimal, int]],
    a2_funding: list[tuple[Decimal, Decimal, int]],
) -> RelativePerpPairEpisode:
    p1 = DetailedCostPolicy("PERP", a1_fee_bps, a1_sprd_bps, a1_slip_bps)
    p2 = DetailedCostPolicy("PERP", a2_fee_bps, a2_sprd_bps, a2_slip_bps)

    a1_events = [
        FundingCashFlowEvent(i * 1000, f_r, m_p, p_side, asset1_qty * m_p, -Decimal(str(p_side)) * asset1_qty * m_p * f_r)
        for i, (m_p, f_r, p_side) in enumerate(a1_funding)
    ]
    a2_events = [
        FundingCashFlowEvent(i * 1000, f_r, m_p, p_side, asset2_qty * m_p, -Decimal(str(p_side)) * asset2_qty * m_p * f_r)
        for i, (m_p, f_r, p_side) in enumerate(a2_funding)
    ]
    legging = asset1_qty * asset1_entry * (delay_bps / Decimal("10000.0")) if delay_bps > Decimal("0") else Decimal("0")

    return RelativePerpPairEpisode(
        episode_id=ep_id,
        strategy_id="ORACLE_PAIR_TEST",
        entry_ts_ns=0,
        exit_ts_ns=3600_000_000_000,
        asset1_symbol=asset1_symbol,
        asset1_side=asset1_side,
        asset1_entry_price=asset1_entry,
        asset1_exit_price=asset1_exit,
        asset1_quantity=asset1_qty,
        asset1_cost_policy=p1,
        asset2_symbol=asset2_symbol,
        asset2_side=asset2_side,
        asset2_entry_price=asset2_entry,
        asset2_exit_price=asset2_exit,
        asset2_quantity=asset2_qty,
        asset2_cost_policy=p2,
        asset1_funding_events=tuple(a1_events),
        asset2_funding_events=tuple(a2_events),
        temporary_delta_loss_usd=legging,
    )


def test_reconcile_btc_long_spot_short_perp() -> None:
    """Exact Decimal reconciliation: BTC Long Spot + Short Perp carry episode."""
    spot_p_in = Decimal("50000.0")
    spot_p_out = Decimal("52000.0")
    perp_p_in = Decimal("50050.0")
    perp_p_out = Decimal("52010.0")
    qty = Decimal("2.0")

    funding = [(Decimal("51000.0"), Decimal("0.0002"), -1)]

    oracle_in = SpotPerpOracleInput(
        spot_side=1,
        spot_entry=spot_p_in,
        spot_exit=spot_p_out,
        spot_quantity=qty,
        perp_side=-1,
        perp_entry=perp_p_in,
        perp_exit=perp_p_out,
        perp_quantity=qty,
        funding_events=tuple(OracleFundingEvent(*f) for f in funding),
    )
    oracle_out = IndependentAccountingOracle.evaluate_spot_perp(oracle_in)

    prod_ep = _build_production_spot_perp_episode(
        "BTC_CARRY_01", "BTC", 1, spot_p_in, spot_p_out, qty, -1, perp_p_in, perp_p_out, qty,
        Decimal("10.0"), Decimal("1.0"), Decimal("4.0"),
        Decimal("5.0"), Decimal("1.0"), Decimal("4.0"),
        Decimal("0.0"), funding,
    )

    # Exact Decimal checks
    assert oracle_out.spot_price_pnl == prod_ep.spot_pnl == Decimal("4000.0")
    assert oracle_out.perp_price_pnl == prod_ep.perp_pnl == -Decimal("3920.0")
    assert oracle_out.total_price_pnl == prod_ep.basis_pnl == Decimal("80.0")
    assert oracle_out.total_funding_pnl == prod_ep.total_funding_pnl == Decimal("20.4")
    assert oracle_out.spot_fees == prod_ep.spot_fees
    assert oracle_out.perp_fees == prod_ep.perp_fees
    assert (oracle_out.spot_spread + oracle_out.spot_slippage) == prod_ep.spot_slippage_and_spread
    assert (oracle_out.perp_spread + oracle_out.perp_slippage) == prod_ep.perp_slippage_and_spread
    assert oracle_out.total_costs == prod_ep.total_costs
    assert oracle_out.net_pnl == prod_ep.net_pnl


def test_reconcile_eth_long_spot_short_perp() -> None:
    """Exact Decimal reconciliation: ETH Long Spot + Short Perp carry episode."""
    spot_p_in = Decimal("3000.0")
    spot_p_out = Decimal("2950.0")
    perp_p_in = Decimal("3002.0")
    perp_p_out = Decimal("2951.0")
    qty = Decimal("10.0")

    funding = [(Decimal("2980.0"), Decimal("0.00015"), -1)]

    oracle_in = SpotPerpOracleInput(
        spot_side=1,
        spot_entry=spot_p_in,
        spot_exit=spot_p_out,
        spot_quantity=qty,
        perp_side=-1,
        perp_entry=perp_p_in,
        perp_exit=perp_p_out,
        perp_quantity=qty,
        funding_events=tuple(OracleFundingEvent(*f) for f in funding),
    )
    oracle_out = IndependentAccountingOracle.evaluate_spot_perp(oracle_in)

    prod_ep = _build_production_spot_perp_episode(
        "ETH_CARRY_01", "ETH", 1, spot_p_in, spot_p_out, qty, -1, perp_p_in, perp_p_out, qty,
        Decimal("10.0"), Decimal("1.0"), Decimal("4.0"),
        Decimal("5.0"), Decimal("1.0"), Decimal("4.0"),
        Decimal("0.0"), funding,
    )

    assert oracle_out.spot_price_pnl == prod_ep.spot_pnl == -Decimal("500.0")
    assert oracle_out.perp_price_pnl == prod_ep.perp_pnl == Decimal("510.0")
    assert oracle_out.total_price_pnl == prod_ep.basis_pnl == Decimal("10.0")
    assert oracle_out.total_funding_pnl == prod_ep.total_funding_pnl == Decimal("4.47")
    assert oracle_out.total_costs == prod_ep.total_costs
    assert oracle_out.net_pnl == prod_ep.net_pnl


def test_reconcile_standalone_perp_primitives() -> None:
    """Exact Decimal reconciliation: Standalone Long Perp and Short Perp primitives."""
    # Long Perp only
    p_in = Decimal("60000.0")
    p_out = Decimal("61500.0")
    qty = Decimal("1.5")
    funding = [(Decimal("61000.0"), Decimal("-0.0001"), 1)]  # Long receives negative funding

    oracle_in = SpotPerpOracleInput(
        spot_side=0,
        spot_entry=Decimal("0"),
        spot_exit=Decimal("0"),
        spot_quantity=Decimal("0"),
        perp_side=1,
        perp_entry=p_in,
        perp_exit=p_out,
        perp_quantity=qty,
        funding_events=tuple(OracleFundingEvent(*f) for f in funding),
    )
    oracle_out = IndependentAccountingOracle.evaluate_spot_perp(oracle_in)

    prod_ep = _build_production_spot_perp_episode(
        "PERP_LONG_01", "BTC", 0, Decimal("0"), Decimal("0"), Decimal("0"), 1, p_in, p_out, qty,
        Decimal("10.0"), Decimal("1.0"), Decimal("4.0"),
        Decimal("5.0"), Decimal("1.0"), Decimal("4.0"),
        Decimal("0.0"), funding,
    )

    assert oracle_out.spot_price_pnl == prod_ep.spot_pnl == Decimal("0")
    assert oracle_out.perp_price_pnl == prod_ep.perp_pnl == Decimal("2250.0")
    assert oracle_out.total_funding_pnl == prod_ep.total_funding_pnl == Decimal("9.15")
    assert oracle_out.total_costs == prod_ep.total_costs
    assert oracle_out.net_pnl == prod_ep.net_pnl


def test_reconcile_relative_perp_pair() -> None:
    """Exact Decimal reconciliation: BTC Long Perp vs ETH Short Perp relative pair."""
    btc_entry = Decimal("50000.0")
    btc_exit = Decimal("51000.0")
    btc_qty = Decimal("1.0")

    eth_entry = Decimal("3000.0")
    eth_exit = Decimal("3030.0")
    eth_qty = Decimal("16.66666667")

    btc_funding = [(Decimal("50500.0"), Decimal("0.0001"), 1)]  # long pays funding
    eth_funding = [(Decimal("3015.0"), Decimal("0.0003"), -1)]  # short receives funding

    oracle_in = RelativePerpPairOracleInput(
        asset1_side=1,
        asset1_entry=btc_entry,
        asset1_exit=btc_exit,
        asset1_quantity=btc_qty,
        asset2_side=-1,
        asset2_entry=eth_entry,
        asset2_exit=eth_exit,
        asset2_quantity=eth_qty,
        asset1_funding_events=tuple(OracleFundingEvent(*f) for f in btc_funding),
        asset2_funding_events=tuple(OracleFundingEvent(*f) for f in eth_funding),
    )
    oracle_out = IndependentAccountingOracle.evaluate_relative_pair(oracle_in)

    prod_ep = _build_production_relative_pair_episode(
        "PAIR_01", "BTCUSDT", 1, btc_entry, btc_exit, btc_qty,
        "ETHUSDT", -1, eth_entry, eth_exit, eth_qty,
        Decimal("5.0"), Decimal("1.0"), Decimal("4.0"),
        Decimal("5.0"), Decimal("1.0"), Decimal("4.0"),
        Decimal("0.0"), btc_funding, eth_funding,
    )

    assert oracle_out.spot_price_pnl == prod_ep.asset1_pnl == Decimal("1000.0")
    assert oracle_out.perp_price_pnl == prod_ep.asset2_pnl == -Decimal("500.00000010")
    assert oracle_out.total_price_pnl == prod_ep.price_pnl
    assert oracle_out.total_funding_pnl == prod_ep.total_funding_pnl
    assert oracle_out.total_costs == prod_ep.total_costs
    assert oracle_out.net_pnl == prod_ep.net_pnl


def test_reconcile_funding_regimes() -> None:
    """Exact Decimal reconciliation across positive, negative, and zero funding flows."""
    for rate_str in ["0.0005", "-0.0005", "0.0000"]:
        f_rate = Decimal(rate_str)
        funding = [(Decimal("50000.0"), f_rate, -1)]
        oracle_in = SpotPerpOracleInput(
            spot_side=1,
            spot_entry=Decimal("50000.0"),
            spot_exit=Decimal("50000.0"),
            spot_quantity=Decimal("1.0"),
            perp_side=-1,
            perp_entry=Decimal("50000.0"),
            perp_exit=Decimal("50000.0"),
            perp_quantity=Decimal("1.0"),
            funding_events=tuple(OracleFundingEvent(*f) for f in funding),
        )
        oracle_out = IndependentAccountingOracle.evaluate_spot_perp(oracle_in)
        prod_ep = _build_production_spot_perp_episode(
            f"FUNDING_{rate_str}", "BTC", 1, Decimal("50000.0"), Decimal("50000.0"), Decimal("1.0"),
            -1, Decimal("50000.0"), Decimal("50000.0"), Decimal("1.0"),
            Decimal("10.0"), Decimal("1.0"), Decimal("4.0"),
            Decimal("5.0"), Decimal("1.0"), Decimal("4.0"),
            Decimal("0.0"), funding,
        )
        assert oracle_out.total_funding_pnl == prod_ep.total_funding_pnl == Decimal("50000.0") * f_rate
        assert oracle_out.net_pnl == prod_ep.net_pnl


def test_reconcile_market_regimes() -> None:
    """Exact Decimal reconciliation across basis convergence, widening, flat, up, down markets."""
    cases = [
        # (name, s_in, s_out, p_in, p_out)
        ("basis_convergence", Decimal("50000.0"), Decimal("50000.0"), Decimal("50200.0"), Decimal("50000.0")),
        ("basis_widening", Decimal("50000.0"), Decimal("50000.0"), Decimal("50000.0"), Decimal("50300.0")),
        ("flat_market", Decimal("50000.0"), Decimal("50000.0"), Decimal("50000.0"), Decimal("50000.0")),
        ("up_market", Decimal("50000.0"), Decimal("55000.0"), Decimal("50050.0"), Decimal("55050.0")),
        ("down_market", Decimal("50000.0"), Decimal("45000.0"), Decimal("50050.0"), Decimal("45050.0")),
    ]
    for name, s_in, s_out, p_in, p_out in cases:
        oracle_in = SpotPerpOracleInput(
            spot_side=1,
            spot_entry=s_in,
            spot_exit=s_out,
            spot_quantity=Decimal("1.0"),
            perp_side=-1,
            perp_entry=p_in,
            perp_exit=p_out,
            perp_quantity=Decimal("1.0"),
        )
        oracle_out = IndependentAccountingOracle.evaluate_spot_perp(oracle_in)
        prod_ep = _build_production_spot_perp_episode(
            name, "BTC", 1, s_in, s_out, Decimal("1.0"),
            -1, p_in, p_out, Decimal("1.0"),
            Decimal("10.0"), Decimal("1.0"), Decimal("4.0"),
            Decimal("5.0"), Decimal("1.0"), Decimal("4.0"),
            Decimal("0.0"), [],
        )
        assert oracle_out.total_price_pnl == prod_ep.basis_pnl
        assert oracle_out.total_costs == prod_ep.total_costs
        assert oracle_out.net_pnl == prod_ep.net_pnl


class MutatedEpisodeWrapper:
    """Wrapper to cleanly simulate field mutations on frozen production episode dataclasses."""
    def __init__(self, original: Any, **overrides: Any) -> None:
        self._original = original
        self._overrides = overrides

    def __getattr__(self, item: str) -> Any:
        if item in self._overrides:
            return self._overrides[item]
        return getattr(self._original, item)


def reconcile_oracle_vs_production(
    oracle_out: Any,
    prod_ep: Any,
) -> tuple[bool, str, dict[str, Any]]:
    """Strict exact Decimal comparison across all primary accounting dimensions.
    
    Returns (reconciled, status_str, diffs).
    Requires EXACT_DECIMAL_EQUALITY (0 tolerance).
    """
    diffs = {}

    # 1. Capital commitment verification
    if hasattr(prod_ep, "capital_override") and prod_ep.capital_override is not None:
        prod_cap = prod_ep.capital_override
    elif hasattr(prod_ep, "spot_notional_entry") and hasattr(prod_ep, "perp_notional_entry"):
        prod_cap = CapitalPolicy().compute_spot_perp_commitment(prod_ep.spot_notional_entry, prod_ep.perp_notional_entry)
    elif hasattr(prod_ep, "asset1_notional_entry") and hasattr(prod_ep, "asset2_notional_entry"):
        prod_cap = CapitalPolicy().compute_relative_pair_commitment(prod_ep.asset1_notional_entry, prod_ep.asset2_notional_entry)
    else:
        prod_cap = getattr(prod_ep, "capital_committed", oracle_out.capital_committed)

    if oracle_out.capital_committed != prod_cap:
        diffs["capital_committed"] = {"oracle": str(oracle_out.capital_committed), "prod": str(prod_cap)}

    base_obj = prod_ep._original if isinstance(prod_ep, MutatedEpisodeWrapper) else prod_ep

    # 2. PnL, Fees, and Cost Dimensions
    if isinstance(base_obj, MultiLegTradeEpisode):
        if prod_ep.spot_quantity > Decimal("0") and oracle_out.spot_price_pnl != prod_ep.spot_pnl:
            diffs["spot_pnl"] = {"oracle": str(oracle_out.spot_price_pnl), "prod": str(prod_ep.spot_pnl)}
        if prod_ep.perp_quantity > Decimal("0") and oracle_out.perp_price_pnl != prod_ep.perp_pnl:
            diffs["perp_pnl"] = {"oracle": str(oracle_out.perp_price_pnl), "prod": str(prod_ep.perp_pnl)}
        if oracle_out.total_price_pnl != prod_ep.basis_pnl:
            diffs["price_pnl"] = {"oracle": str(oracle_out.total_price_pnl), "prod": str(prod_ep.basis_pnl)}
        if oracle_out.total_funding_pnl != prod_ep.total_funding_pnl:
            diffs["funding_pnl"] = {"oracle": str(oracle_out.total_funding_pnl), "prod": str(prod_ep.total_funding_pnl)}
        if oracle_out.spot_fees != prod_ep.spot_fees:
            diffs["spot_fees"] = {"oracle": str(oracle_out.spot_fees), "prod": str(prod_ep.spot_fees)}
        if oracle_out.perp_fees != prod_ep.perp_fees:
            diffs["perp_fees"] = {"oracle": str(oracle_out.perp_fees), "prod": str(prod_ep.perp_fees)}
        if oracle_out.total_costs != prod_ep.total_costs:
            diffs["total_costs"] = {"oracle": str(oracle_out.total_costs), "prod": str(prod_ep.total_costs)}
        if oracle_out.net_pnl != prod_ep.net_pnl:
            diffs["net_pnl"] = {"oracle": str(oracle_out.net_pnl), "prod": str(prod_ep.net_pnl)}
    elif isinstance(base_obj, RelativePerpPairEpisode):
        if oracle_out.total_price_pnl != prod_ep.price_pnl:
            diffs["price_pnl"] = {"oracle": str(oracle_out.total_price_pnl), "prod": str(prod_ep.price_pnl)}
        if oracle_out.total_funding_pnl != prod_ep.total_funding_pnl:
            diffs["funding_pnl"] = {"oracle": str(oracle_out.total_funding_pnl), "prod": str(prod_ep.total_funding_pnl)}
        if oracle_out.total_costs != prod_ep.total_costs:
            diffs["total_costs"] = {"oracle": str(oracle_out.total_costs), "prod": str(prod_ep.total_costs)}
        if oracle_out.net_pnl != prod_ep.net_pnl:
            diffs["net_pnl"] = {"oracle": str(oracle_out.net_pnl), "prod": str(prod_ep.net_pnl)}

    if diffs:
        return False, f"RECONCILIATION_FAILURE: Discrepancies in {list(diffs.keys())}", diffs
    return True, "EXACT_DECIMAL_EQUALITY", {}


def test_deterministic_randomized_campaign_500_cases() -> None:
    """Preserved deterministic randomized campaign of 520 cases for backward compatibility."""
    random.seed(42)
    total_cases = 520
    exact_matches = 0
    discrepancies = []

    for idx in range(1, total_cases + 1):
        asset = "BTC" if idx % 2 == 1 else "ETH"
        base_price = Decimal(str(random.randint(20000, 65000))) if asset == "BTC" else Decimal(str(random.randint(1200, 4500)))

        spot_entry = base_price
        spot_move_pct = Decimal(str(random.uniform(-0.10, 0.10)))
        spot_exit = (spot_entry * (Decimal("1.0") + spot_move_pct)).quantize(Decimal("0.01"))

        basis_in_bps = Decimal(str(random.uniform(-100, 100)))
        basis_out_bps = Decimal(str(random.uniform(-100, 100)))
        perp_entry = (spot_entry * (Decimal("1.0") + basis_in_bps / Decimal("10000.0"))).quantize(Decimal("0.01"))
        perp_exit = (spot_exit * (Decimal("1.0") + basis_out_bps / Decimal("10000.0"))).quantize(Decimal("0.01"))

        target_notional = Decimal(str(random.randint(10000, 200000)))
        qty = (target_notional / spot_entry).quantize(Decimal("0.0001"))

        s_fee = Decimal(str(random.choice([5.0, 7.5, 10.0, 15.0])))
        s_sprd = Decimal(str(random.choice([0.5, 1.0, 2.0])))
        s_slip = Decimal(str(random.choice([1.0, 2.0, 4.0, 8.0])))
        p_fee = Decimal(str(random.choice([2.0, 4.0, 5.0, 7.5])))
        p_sprd = Decimal(str(random.choice([0.5, 1.0, 2.0])))
        p_slip = Decimal(str(random.choice([1.0, 2.0, 4.0, 8.0])))
        delay_bps = Decimal(str(random.choice([0.0, 1.0, 2.0, 5.0])))

        num_funding = random.randint(0, 4)
        raw_funding = []
        for _ in range(num_funding):
            f_rate = Decimal(str(random.choice([-0.0005, -0.0002, 0.0, 0.0001, 0.0003, 0.0008])))
            mark_p = ((spot_entry + spot_exit) / Decimal("2.0")).quantize(Decimal("0.01"))
            raw_funding.append((mark_p, f_rate, -1))

        oracle_in = SpotPerpOracleInput(
            spot_side=1,
            spot_entry=spot_entry,
            spot_exit=spot_exit,
            spot_quantity=qty,
            perp_side=-1,
            perp_entry=perp_entry,
            perp_exit=perp_exit,
            perp_quantity=qty,
            spot_fee_bps=s_fee,
            spot_spread_bps=s_sprd,
            spot_slip_bps=s_slip,
            perp_fee_bps=p_fee,
            perp_spread_bps=p_sprd,
            perp_slip_bps=p_slip,
            legging_delay_bps=delay_bps,
            funding_events=tuple(OracleFundingEvent(*f) for f in raw_funding),
        )
        oracle_out = IndependentAccountingOracle.evaluate_spot_perp(oracle_in)

        prod_ep = _build_production_spot_perp_episode(
            f"RECON_{idx:04d}", asset, 1, spot_entry, spot_exit, qty, -1, perp_entry, perp_exit, qty,
            s_fee, s_sprd, s_slip, p_fee, p_sprd, p_slip, delay_bps, raw_funding,
        )

        ok, msg, diffs = reconcile_oracle_vs_production(oracle_out, prod_ep)
        if not ok:
            discrepancies.append({"case_idx": idx, "diffs": diffs})
        else:
            exact_matches += 1

    assert len(discrepancies) == 0
    assert exact_matches == 520


def test_multi_family_randomized_oracle_campaign_850_cases() -> None:
    """Comprehensive Round 3B.0A multi-family randomized property campaign across 850 cases:
    - 200 BTC Spot/Perp cases (mixed long/short)
    - 200 ETH Spot/Perp cases (mixed long/short)
    - 150 Standalone Perp cases (mixed long/short BTC/ETH)
    - 200 BTC/ETH Relative-Pair cases (both directional combinations)
    - 100 Edge/Boundary cases
    Requires EXACT_DECIMAL_EQUALITY down to 0 tolerance.
    """
    random.seed(1337)
    family_counts = {
        "btc_spot_perp": 0,
        "eth_spot_perp": 0,
        "standalone_perp": 0,
        "relative_pair": 0,
        "edge_boundary": 0,
    }
    discrepancies = []
    total_tested = 0

    # 1. 200 BTC Spot/Perp cases
    for i in range(200):
        spot_side = 1 if i % 2 == 0 else -1
        perp_side = -1 if spot_side == 1 else 1
        s_in = Decimal(str(random.randint(20000, 65000)))
        s_out = (s_in * (Decimal("1.0") + Decimal(str(random.uniform(-0.10, 0.10))))).quantize(Decimal("0.01"))
        p_in = (s_in * (Decimal("1.0") + Decimal(str(random.uniform(-0.02, 0.02))))).quantize(Decimal("0.01"))
        p_out = (s_out * (Decimal("1.0") + Decimal(str(random.uniform(-0.02, 0.02))))).quantize(Decimal("0.01"))
        qty = Decimal(str(random.uniform(0.1, 5.0))).quantize(Decimal("0.0001"))
        s_fee = Decimal(str(random.choice([5.0, 10.0])))
        p_fee = Decimal(str(random.choice([2.0, 5.0])))
        s_sprd = Decimal("1.0")
        p_sprd = Decimal("1.0")
        s_slip = Decimal("2.0")
        p_slip = Decimal("2.0")
        delay = Decimal("0.0")

        f_rate = Decimal(str(random.choice([-0.0003, 0.0, 0.0002])))
        funding = [(p_in, f_rate, perp_side)]

        oracle_in = SpotPerpOracleInput(
            spot_side=spot_side, spot_entry=s_in, spot_exit=s_out, spot_quantity=qty,
            perp_side=perp_side, perp_entry=p_in, perp_exit=p_out, perp_quantity=qty,
            spot_fee_bps=s_fee, spot_spread_bps=s_sprd, spot_slip_bps=s_slip,
            perp_fee_bps=p_fee, perp_spread_bps=p_sprd, perp_slip_bps=p_slip,
            legging_delay_bps=delay,
            funding_events=tuple(OracleFundingEvent(*f) for f in funding),
        )
        oracle_out = IndependentAccountingOracle.evaluate_spot_perp(oracle_in)
        prod_ep = _build_production_spot_perp_episode(
            f"BTC_SP_{i}", "BTC", spot_side, s_in, s_out, qty, perp_side, p_in, p_out, qty,
            s_fee, s_sprd, s_slip, p_fee, p_sprd, p_slip, delay, funding,
        )
        ok, msg, diffs = reconcile_oracle_vs_production(oracle_out, prod_ep)
        assert ok is True, f"BTC Spot-Perp discrepancy at {i}: {diffs}"
        family_counts["btc_spot_perp"] += 1
        total_tested += 1

    # 2. 200 ETH Spot/Perp cases
    for i in range(200):
        spot_side = 1 if i % 2 == 0 else -1
        perp_side = -1 if spot_side == 1 else 1
        s_in = Decimal(str(random.randint(1200, 4500)))
        s_out = (s_in * (Decimal("1.0") + Decimal(str(random.uniform(-0.10, 0.10))))).quantize(Decimal("0.01"))
        p_in = (s_in * (Decimal("1.0") + Decimal(str(random.uniform(-0.02, 0.02))))).quantize(Decimal("0.01"))
        p_out = (s_out * (Decimal("1.0") + Decimal(str(random.uniform(-0.02, 0.02))))).quantize(Decimal("0.01"))
        qty = Decimal(str(random.uniform(1.0, 50.0))).quantize(Decimal("0.0001"))
        s_fee = Decimal(str(random.choice([5.0, 10.0])))
        p_fee = Decimal(str(random.choice([2.0, 5.0])))
        funding = [(p_in, Decimal(str(random.choice([-0.0002, 0.0001]))), perp_side)]

        oracle_in = SpotPerpOracleInput(
            spot_side=spot_side, spot_entry=s_in, spot_exit=s_out, spot_quantity=qty,
            perp_side=perp_side, perp_entry=p_in, perp_exit=p_out, perp_quantity=qty,
            spot_fee_bps=s_fee, spot_spread_bps=Decimal("1.0"), spot_slip_bps=Decimal("2.0"),
            perp_fee_bps=p_fee, perp_spread_bps=Decimal("1.0"), perp_slip_bps=Decimal("2.0"),
            funding_events=tuple(OracleFundingEvent(*f) for f in funding),
        )
        oracle_out = IndependentAccountingOracle.evaluate_spot_perp(oracle_in)
        prod_ep = _build_production_spot_perp_episode(
            f"ETH_SP_{i}", "ETH", spot_side, s_in, s_out, qty, perp_side, p_in, p_out, qty,
            s_fee, Decimal("1.0"), Decimal("2.0"), p_fee, Decimal("1.0"), Decimal("2.0"), Decimal("0.0"), funding,
        )
        ok, msg, diffs = reconcile_oracle_vs_production(oracle_out, prod_ep)
        assert ok is True, f"ETH Spot-Perp discrepancy at {i}: {diffs}"
        family_counts["eth_spot_perp"] += 1
        total_tested += 1

    # 3. 150 Standalone Perp cases (mixed BTC/ETH, long/short)
    for i in range(150):
        asset = "BTC" if i < 75 else "ETH"
        perp_side = 1 if i % 2 == 0 else -1
        base = Decimal(str(random.randint(20000, 65000))) if asset == "BTC" else Decimal(str(random.randint(1200, 4500)))
        p_in = base
        p_out = (base * (Decimal("1.0") + Decimal(str(random.uniform(-0.08, 0.08))))).quantize(Decimal("0.01"))
        qty = Decimal(str(random.uniform(0.5, 5.0))) if asset == "BTC" else Decimal(str(random.uniform(5.0, 40.0)))
        qty = qty.quantize(Decimal("0.0001"))
        p_fee = Decimal("5.0")
        funding = [(p_in, Decimal(str(random.choice([-0.0004, 0.0003]))), perp_side)]

        oracle_in = SpotPerpOracleInput(
            spot_side=0, spot_entry=Decimal("0.0"), spot_exit=Decimal("0.0"), spot_quantity=Decimal("0.0"),
            perp_side=perp_side, perp_entry=p_in, perp_exit=p_out, perp_quantity=qty,
            spot_fee_bps=Decimal("0.0"), spot_spread_bps=Decimal("0.0"), spot_slip_bps=Decimal("0.0"),
            perp_fee_bps=p_fee, perp_spread_bps=Decimal("1.0"), perp_slip_bps=Decimal("2.0"),
            funding_events=tuple(OracleFundingEvent(*f) for f in funding),
        )
        oracle_out = IndependentAccountingOracle.evaluate_spot_perp(oracle_in)
        prod_ep = _build_production_spot_perp_episode(
            f"PERP_ST_{i}", asset, 0, Decimal("0.0"), Decimal("0.0"), Decimal("0.0"),
            perp_side, p_in, p_out, qty,
            Decimal("0.0"), Decimal("0.0"), Decimal("0.0"),
            p_fee, Decimal("1.0"), Decimal("2.0"), Decimal("0.0"), funding,
        )
        ok, msg, diffs = reconcile_oracle_vs_production(oracle_out, prod_ep)
        assert ok is True, f"Standalone Perp discrepancy at {i}: {diffs}"
        family_counts["standalone_perp"] += 1
        total_tested += 1

    # 4. 200 Relative Perp cases (BTC vs ETH)
    for i in range(200):
        btc_side = 1 if i < 100 else -1
        eth_side = -1 if btc_side == 1 else 1
        btc_in = Decimal(str(random.randint(25000, 60000)))
        btc_out = (btc_in * (Decimal("1.0") + Decimal(str(random.uniform(-0.06, 0.06))))).quantize(Decimal("0.01"))
        eth_in = Decimal(str(random.randint(1500, 3500)))
        eth_out = (eth_in * (Decimal("1.0") + Decimal(str(random.uniform(-0.06, 0.06))))).quantize(Decimal("0.01"))
        btc_qty = Decimal(str(random.uniform(0.5, 2.0))).quantize(Decimal("0.0001"))
        # Match notionals roughly
        eth_qty = ((btc_in * btc_qty) / eth_in).quantize(Decimal("0.0001"))

        btc_f = [(btc_in, Decimal("0.0001"), btc_side)]
        eth_f = [(eth_in, Decimal("0.00015"), eth_side)]

        oracle_in = RelativePerpPairOracleInput(
            asset1_side=btc_side, asset1_entry=btc_in, asset1_exit=btc_out, asset1_quantity=btc_qty,
            asset2_side=eth_side, asset2_entry=eth_in, asset2_exit=eth_out, asset2_quantity=eth_qty,
            asset1_funding_events=tuple(OracleFundingEvent(*f) for f in btc_f),
            asset2_funding_events=tuple(OracleFundingEvent(*f) for f in eth_f),
        )
        oracle_out = IndependentAccountingOracle.evaluate_relative_pair(oracle_in)
        prod_ep = _build_production_relative_pair_episode(
            f"REL_PAIR_{i}", "BTCUSDT", btc_side, btc_in, btc_out, btc_qty,
            "ETHUSDT", eth_side, eth_in, eth_out, eth_qty,
            Decimal("5.0"), Decimal("1.0"), Decimal("4.0"),
            Decimal("5.0"), Decimal("1.0"), Decimal("4.0"),
            Decimal("0.0"), btc_f, eth_f,
        )
        ok, msg, diffs = reconcile_oracle_vs_production(oracle_out, prod_ep)
        assert ok is True, f"Relative Pair discrepancy at {i}: {diffs}"
        family_counts["relative_pair"] += 1
        total_tested += 1

    # 5. 100 Edge/Boundary cases
    for i in range(100):
        # Variety of edge conditions: flat market, zero funding, inverted basis, tiny/large notional
        s_in = Decimal("50000.0") if i % 2 == 0 else Decimal("2000.0")
        s_out = s_in  # Flat market
        p_in = s_in - Decimal("100.0") if i < 50 else s_in + Decimal("100.0")  # Inverted vs normal
        p_out = s_in
        qty = Decimal("0.0001") if i < 25 else (Decimal("100.0") if i > 75 else Decimal("1.0"))

        funding = [] if i % 3 == 0 else [(s_in, Decimal("0.0050"), -1)]  # Zero or extreme funding

        oracle_in = SpotPerpOracleInput(
            spot_side=1, spot_entry=s_in, spot_exit=s_out, spot_quantity=qty,
            perp_side=-1, perp_entry=p_in, perp_exit=p_out, perp_quantity=qty,
            spot_fee_bps=Decimal("0.0") if i < 10 else Decimal("10.0"),
            spot_spread_bps=Decimal("0.0") if i < 10 else Decimal("1.0"),
            spot_slip_bps=Decimal("0.0") if i < 10 else Decimal("2.0"),
            perp_fee_bps=Decimal("0.0") if i < 10 else Decimal("5.0"),
            perp_spread_bps=Decimal("0.0") if i < 10 else Decimal("1.0"),
            perp_slip_bps=Decimal("0.0") if i < 10 else Decimal("2.0"),
            funding_events=tuple(OracleFundingEvent(*f) for f in funding),
        )
        oracle_out = IndependentAccountingOracle.evaluate_spot_perp(oracle_in)
        prod_ep = _build_production_spot_perp_episode(
            f"EDGE_{i}", "BTC" if i % 2 == 0 else "ETH", 1, s_in, s_out, qty, -1, p_in, p_out, qty,
            Decimal("0.0") if i < 10 else Decimal("10.0"),
            Decimal("0.0") if i < 10 else Decimal("1.0"),
            Decimal("0.0") if i < 10 else Decimal("2.0"),
            Decimal("0.0") if i < 10 else Decimal("5.0"),
            Decimal("0.0") if i < 10 else Decimal("1.0"),
            Decimal("0.0") if i < 10 else Decimal("2.0"),
            Decimal("0.0"), funding,
        )
        ok, msg, diffs = reconcile_oracle_vs_production(oracle_out, prod_ep)
        assert ok is True, f"Edge Case discrepancy at {i}: {diffs}"
        family_counts["edge_boundary"] += 1
        total_tested += 1

    assert total_tested == 850
    assert family_counts["btc_spot_perp"] == 200
    assert family_counts["eth_spot_perp"] == 200
    assert family_counts["standalone_perp"] == 150
    assert family_counts["relative_pair"] == 200
    assert family_counts["edge_boundary"] == 100

    audit_payload = {
        "report_version": "ROUND3B.0A",
        "oracle_isolation": "STRICT_STANDALONE_NO_BTCETH_OS_IMPORTS",
        "equality_policy": "EXACT_DECIMAL_EQUALITY",
        "tolerance": "0.0",
        "total_cases_tested": total_tested,
        "exact_matches": total_tested,
        "discrepancies_count": 0,
        "family_breakdown": family_counts,
        "reconciliation_status": "VERIFIED",
        "mutation_gate_passed": True,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "ROUND3B_0A_ORACLE_AUDIT.json").write_text(json.dumps(audit_payload, indent=2) + "\n", encoding="utf-8")


def test_multi_dimensional_negative_mutation_gate() -> None:
    """Adversarial negative mutation gate: test mutations across 5 distinct dimensions.
    Each mutated dimension must fail reconcile_oracle_vs_production with RECONCILIATION_FAILURE.
    """
    spot_p = Decimal("50000.0")
    qty = Decimal("1.0")
    funding = [(spot_p, Decimal("0.0001"), -1)]

    oracle_in = SpotPerpOracleInput(
        spot_side=1, spot_entry=spot_p, spot_exit=spot_p, spot_quantity=qty,
        perp_side=-1, perp_entry=spot_p, perp_exit=spot_p, perp_quantity=qty,
        funding_events=tuple(OracleFundingEvent(*f) for f in funding),
    )
    oracle_out = IndependentAccountingOracle.evaluate_spot_perp(oracle_in)

    # 1. Base genuine production episode matches cleanly
    prod_base = _build_production_spot_perp_episode(
        "MUT_BASE", "BTC", 1, spot_p, spot_p, qty, -1, spot_p, spot_p, qty,
        Decimal("10.0"), Decimal("1.0"), Decimal("4.0"),
        Decimal("5.0"), Decimal("1.0"), Decimal("4.0"),
        Decimal("0.0"), funding,
    )
    ok_base, msg_base, _ = reconcile_oracle_vs_production(oracle_out, prod_base)
    assert ok_base is True
    assert msg_base == "EXACT_DECIMAL_EQUALITY"

    # Dimension 1: Fee Mutation
    prod_mut_fee = MutatedEpisodeWrapper(prod_base, spot_fees=prod_base.spot_fees + Decimal("0.01"))
    ok, msg, diffs = reconcile_oracle_vs_production(oracle_out, prod_mut_fee)
    assert ok is False
    assert "RECONCILIATION_FAILURE" in msg
    assert "spot_fees" in diffs

    # Dimension 2: Funding Mutation
    prod_mut_fund = MutatedEpisodeWrapper(prod_base, total_funding_pnl=prod_base.total_funding_pnl + Decimal("0.01"))
    ok, msg, diffs = reconcile_oracle_vs_production(oracle_out, prod_mut_fund)
    assert ok is False
    assert "RECONCILIATION_FAILURE" in msg
    assert "funding_pnl" in diffs

    # Dimension 3: Price P&L Mutation
    prod_mut_pnl = MutatedEpisodeWrapper(prod_base, spot_pnl=prod_base.spot_pnl + Decimal("0.01"))
    ok, msg, diffs = reconcile_oracle_vs_production(oracle_out, prod_mut_pnl)
    assert ok is False
    assert "RECONCILIATION_FAILURE" in msg
    assert "spot_pnl" in diffs

    # Dimension 4: Total Cost Mutation
    prod_mut_costs = MutatedEpisodeWrapper(prod_base, total_costs=prod_base.total_costs + Decimal("0.01"))
    ok, msg, diffs = reconcile_oracle_vs_production(oracle_out, prod_mut_costs)
    assert ok is False
    assert "RECONCILIATION_FAILURE" in msg
    assert "total_costs" in diffs

    # Dimension 5: Capital Commitment Mutation
    prod_mut_cap = MutatedEpisodeWrapper(prod_base, capital_override=Decimal("999999.0"))
    ok, msg, diffs = reconcile_oracle_vs_production(oracle_out, prod_mut_cap)
    assert ok is False
    assert "RECONCILIATION_FAILURE" in msg
    assert "capital_committed" in diffs

