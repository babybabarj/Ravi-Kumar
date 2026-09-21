from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence, Tuple

# ZERO btceth_os imports permitted in this oracle.
# Standard library + Decimal only.


@dataclass(frozen=True)
class OracleFundingEvent:
    mark_price: Decimal
    funding_rate: Decimal
    position_side: int  # 1 for Long, -1 for Short


@dataclass(frozen=True)
class SpotPerpOracleInput:
    spot_side: int  # 1 for Long, -1 for Short, 0 for None
    spot_entry: Decimal
    spot_exit: Decimal
    spot_quantity: Decimal

    perp_side: int  # -1 for Short, 1 for Long, 0 for None
    perp_entry: Decimal
    perp_exit: Decimal
    perp_quantity: Decimal

    spot_fee_bps: Decimal = Decimal("10.0")
    spot_spread_bps: Decimal = Decimal("1.0")
    spot_slip_bps: Decimal = Decimal("4.0")

    perp_fee_bps: Decimal = Decimal("5.0")
    perp_spread_bps: Decimal = Decimal("1.0")
    perp_slip_bps: Decimal = Decimal("4.0")

    legging_delay_bps: Decimal = Decimal("0.0")
    funding_events: Tuple[OracleFundingEvent, ...] = ()

    # Explicit capital policy inputs
    perp_initial_margin_rate: Decimal = Decimal("0.10")  # e.g., 10x leverage = 10%
    perp_maintenance_buffer_rate: Decimal = Decimal("0.05")  # 5% buffer


@dataclass(frozen=True)
class RelativePerpPairOracleInput:
    asset1_side: int  # 1 for Long, -1 for Short
    asset1_entry: Decimal
    asset1_exit: Decimal
    asset1_quantity: Decimal

    asset2_side: int  # -1 for Short, 1 for Long
    asset2_entry: Decimal
    asset2_exit: Decimal
    asset2_quantity: Decimal

    asset1_fee_bps: Decimal = Decimal("5.0")
    asset1_spread_bps: Decimal = Decimal("1.0")
    asset1_slip_bps: Decimal = Decimal("4.0")

    asset2_fee_bps: Decimal = Decimal("5.0")
    asset2_spread_bps: Decimal = Decimal("1.0")
    asset2_slip_bps: Decimal = Decimal("4.0")

    legging_delay_bps: Decimal = Decimal("0.0")
    asset1_funding_events: Tuple[OracleFundingEvent, ...] = ()
    asset2_funding_events: Tuple[OracleFundingEvent, ...] = ()

    perp_initial_margin_rate: Decimal = Decimal("0.10")
    perp_maintenance_buffer_rate: Decimal = Decimal("0.05")


@dataclass(frozen=True)
class OracleAccountingOutput:
    spot_price_pnl: Decimal
    perp_price_pnl: Decimal
    total_price_pnl: Decimal

    total_funding_pnl: Decimal

    spot_fees: Decimal
    spot_spread: Decimal
    spot_slippage: Decimal

    perp_fees: Decimal
    perp_spread: Decimal
    perp_slippage: Decimal

    legging_cost: Decimal
    total_costs: Decimal

    gross_pnl: Decimal
    net_pnl: Decimal

    gross_exposure: Decimal
    capital_committed: Decimal
    nav_change: Decimal


class IndependentAccountingOracle:
    """Independent first-principles structural accounting oracle.

    Implements pure first-principles financial accounting rules:
    - Long PnL  = Quantity * (ExitPrice - EntryPrice)
    - Short PnL = -Quantity * (ExitPrice - EntryPrice)
    - Funding Cash Flow = -PositionSide * (Quantity * MarkPrice) * FundingRate
    - Taker Fees = TradedNotional * (FeeBps / 10000)
    - Spread Cost = TradedNotional * (SpreadBps / 10000)
    - Slippage Cost = TradedNotional * (SlippageBps / 10000)
    - Net PnL = PricePnL + FundingPnL - TotalCosts
    - NAV Change = Net PnL
    """

    BPS_DIVISOR = Decimal("10000.0")

    @classmethod
    def evaluate_spot_perp(cls, inp: SpotPerpOracleInput) -> OracleAccountingOutput:
        # Spot Leg
        if inp.spot_side != 0 and inp.spot_quantity > Decimal("0"):
            spot_dir = Decimal(str(inp.spot_side))
            s_pnl = spot_dir * inp.spot_quantity * (inp.spot_exit - inp.spot_entry)
            s_entry_notional = inp.spot_entry * inp.spot_quantity
            s_exit_notional = inp.spot_exit * inp.spot_quantity
            s_vol = s_entry_notional + s_exit_notional

            s_fees = s_vol * (inp.spot_fee_bps / cls.BPS_DIVISOR)
            s_spread = s_vol * (inp.spot_spread_bps / cls.BPS_DIVISOR)
            s_slip = s_vol * (inp.spot_slip_bps / cls.BPS_DIVISOR)
        else:
            s_pnl = Decimal("0")
            s_entry_notional = Decimal("0")
            s_fees = Decimal("0")
            s_spread = Decimal("0")
            s_slip = Decimal("0")

        # Perp Leg
        if inp.perp_side != 0 and inp.perp_quantity > Decimal("0"):
            perp_dir = Decimal(str(inp.perp_side))
            p_pnl = perp_dir * inp.perp_quantity * (inp.perp_exit - inp.perp_entry)
            p_entry_notional = inp.perp_entry * inp.perp_quantity
            p_exit_notional = inp.perp_exit * inp.perp_quantity
            p_vol = p_entry_notional + p_exit_notional

            p_fees = p_vol * (inp.perp_fee_bps / cls.BPS_DIVISOR)
            p_spread = p_vol * (inp.perp_spread_bps / cls.BPS_DIVISOR)
            p_slip = p_vol * (inp.perp_slip_bps / cls.BPS_DIVISOR)
        else:
            p_pnl = Decimal("0")
            p_entry_notional = Decimal("0")
            p_fees = Decimal("0")
            p_spread = Decimal("0")
            p_slip = Decimal("0")

        # Legging friction on entry notional
        if inp.spot_side != 0 and inp.perp_side != 0 and inp.legging_delay_bps > Decimal("0"):
            legging = s_entry_notional * (inp.legging_delay_bps / cls.BPS_DIVISOR)
        else:
            legging = Decimal("0")

        # Funding cash flows
        funding_pnl = Decimal("0")
        for ev in inp.funding_events:
            side_dec = Decimal(str(ev.position_side))
            # Cash flow from holding position: Long pays if rate > 0 (-1 * 1 * notional * rate)
            # Short receives if rate > 0 (-1 * -1 * notional * rate = + notional * rate)
            cf = -side_dec * (inp.perp_quantity * ev.mark_price) * ev.funding_rate
            funding_pnl += cf

        total_price_pnl = s_pnl + p_pnl
        total_costs = s_fees + s_spread + s_slip + p_fees + p_spread + p_slip + legging

        gross_pnl = total_price_pnl + funding_pnl - legging
        net_pnl = total_price_pnl + funding_pnl - total_costs

        gross_exposure = s_entry_notional + p_entry_notional

        # Capital committed: Spot cash required + Perp margin + Perp buffer
        perp_margin_req = p_entry_notional * (inp.perp_initial_margin_rate + inp.perp_maintenance_buffer_rate)
        capital_committed = s_entry_notional + perp_margin_req

        return OracleAccountingOutput(
            spot_price_pnl=s_pnl,
            perp_price_pnl=p_pnl,
            total_price_pnl=total_price_pnl,
            total_funding_pnl=funding_pnl,
            spot_fees=s_fees,
            spot_spread=s_spread,
            spot_slippage=s_slip,
            perp_fees=p_fees,
            perp_spread=p_spread,
            perp_slippage=p_slip,
            legging_cost=legging,
            total_costs=total_costs,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            gross_exposure=gross_exposure,
            capital_committed=capital_committed,
            nav_change=net_pnl,
        )

    @classmethod
    def evaluate_relative_pair(cls, inp: RelativePerpPairOracleInput) -> OracleAccountingOutput:
        # Asset 1 (e.g. BTC Perp)
        a1_dir = Decimal(str(inp.asset1_side))
        a1_pnl = a1_dir * inp.asset1_quantity * (inp.asset1_exit - inp.asset1_entry)
        a1_entry_notional = inp.asset1_entry * inp.asset1_quantity
        a1_exit_notional = inp.asset1_exit * inp.asset1_quantity
        a1_vol = a1_entry_notional + a1_exit_notional

        a1_fees = a1_vol * (inp.asset1_fee_bps / cls.BPS_DIVISOR)
        a1_spread = a1_vol * (inp.asset1_spread_bps / cls.BPS_DIVISOR)
        a1_slip = a1_vol * (inp.asset1_slip_bps / cls.BPS_DIVISOR)

        # Asset 2 (e.g. ETH Perp)
        a2_dir = Decimal(str(inp.asset2_side))
        a2_pnl = a2_dir * inp.asset2_quantity * (inp.asset2_exit - inp.asset2_entry)
        a2_entry_notional = inp.asset2_entry * inp.asset2_quantity
        a2_exit_notional = inp.asset2_exit * inp.asset2_quantity
        a2_vol = a2_entry_notional + a2_exit_notional

        a2_fees = a2_vol * (inp.asset2_fee_bps / cls.BPS_DIVISOR)
        a2_spread = a2_vol * (inp.asset2_spread_bps / cls.BPS_DIVISOR)
        a2_slip = a2_vol * (inp.asset2_slip_bps / cls.BPS_DIVISOR)

        # Legging friction
        if inp.legging_delay_bps > Decimal("0"):
            legging = a1_entry_notional * (inp.legging_delay_bps / cls.BPS_DIVISOR)
        else:
            legging = Decimal("0")

        # Funding cash flows across both legs
        total_funding = Decimal("0")
        for ev in inp.asset1_funding_events:
            side_dec = Decimal(str(ev.position_side))
            total_funding += -side_dec * (inp.asset1_quantity * ev.mark_price) * ev.funding_rate

        for ev in inp.asset2_funding_events:
            side_dec = Decimal(str(ev.position_side))
            total_funding += -side_dec * (inp.asset2_quantity * ev.mark_price) * ev.funding_rate

        total_price_pnl = a1_pnl + a2_pnl
        total_costs = a1_fees + a1_spread + a1_slip + a2_fees + a2_spread + a2_slip + legging

        gross_pnl = total_price_pnl + total_funding - legging
        net_pnl = total_price_pnl + total_funding - total_costs

        gross_exposure = a1_entry_notional + a2_entry_notional

        # Capital committed: Margin requirements on both perps
        total_margin_rate = inp.perp_initial_margin_rate + inp.perp_maintenance_buffer_rate
        capital_committed = (a1_entry_notional + a2_entry_notional) * total_margin_rate

        return OracleAccountingOutput(
            spot_price_pnl=a1_pnl,
            perp_price_pnl=a2_pnl,
            total_price_pnl=total_price_pnl,
            total_funding_pnl=total_funding,
            spot_fees=a1_fees,
            spot_spread=a1_spread,
            spot_slippage=a1_slip,
            perp_fees=a2_fees,
            perp_spread=a2_spread,
            perp_slippage=a2_slip,
            legging_cost=legging,
            total_costs=total_costs,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            gross_exposure=gross_exposure,
            capital_committed=capital_committed,
            nav_change=net_pnl,
        )
