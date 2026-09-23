"""Tests for XAU historical contract rule epoch replay and registry."""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest

from btceth_os.contract_rule_epochs import ContractRuleEpochRegistry

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "xau_contract_rule_epochs.yaml"


def test_epoch_registry_loads_all_proven_epochs() -> None:
    reg = ContractRuleEpochRegistry.from_yaml(CONFIG_PATH)
    assert len(reg.epochs) == 7
    ids = [e.epoch_id for e in reg.epochs]
    assert ids == [
        "XAU_EPOCH_0_PRE_LAUNCH_QUARANTINE",
        "XAU_EPOCH_1_LAUNCH_DISCOVERY",
        "XAU_EPOCH_2_ZERO_INTEREST_COMPONENT",
        "XAU_EPOCH_3_INDEX_WEIGHT_REBALANCE",
        "XAU_EPOCH_4_8H_FUNDING_AND_CAP_FLOOR",
        "XAU_EPOCH_5_ORDERBOOK_EWMA_INDEX_MODE",
        "XAU_EPOCH_6_ET_SESSION_CALENDAR_REGIME",
    ]


def test_epoch_0_quarantine_enforced() -> None:
    reg = ContractRuleEpochRegistry.from_yaml(CONFIG_PATH)
    ep0 = reg.epochs[0]
    assert ep0.confidence == "QUARANTINED"
    assert ep0.effective_from_utc == "2025-12-11T00:00:00+00:00"
    assert ep0.effective_to_utc == "2026-01-06T00:00:00+00:00"
    assert len(ep0.unknown_fields) >= 5
    assert ep0.tick_size is None
    assert ep0.funding_interval_seconds is None


def test_funding_epoch_replay() -> None:
    reg = ContractRuleEpochRegistry.from_yaml(CONFIG_PATH)

    # Epoch 1: 4h interval, ±0.375% cap
    ep1 = reg.get_epoch_for_timestamp("2026-01-15T12:00:00Z")
    assert ep1.epoch_id == "XAU_EPOCH_1_LAUNCH_DISCOVERY"
    assert ep1.funding_interval_seconds == 14400
    assert ep1.funding_cap_floor == Decimal("0.00375")

    # Epoch 2: 4h interval, 0.0% interest component
    ep2 = reg.get_epoch_for_timestamp("2026-01-25T12:00:00Z")
    assert ep2.epoch_id == "XAU_EPOCH_2_ZERO_INTEREST_COMPONENT"
    assert ep2.funding_interval_seconds == 14400
    assert ep2.funding_interest_component == Decimal("0.0")

    # Epoch 4: 8h interval, ±0.05% cap
    ep4 = reg.get_epoch_for_timestamp("2026-02-15T12:00:00Z")
    assert ep4.epoch_id == "XAU_EPOCH_4_8H_FUNDING_AND_CAP_FLOOR"
    assert ep4.funding_interval_seconds == 28800
    assert ep4.funding_cap_floor == Decimal("0.0005")


def test_index_method_epoch_replay() -> None:
    reg = ContractRuleEpochRegistry.from_yaml(CONFIG_PATH)

    # Epoch 1: fixed off-hours
    ep1 = reg.get_epoch_for_timestamp("2026-01-10T12:00:00Z")
    assert ep1.price_index_method == "MULTI_VENDOR_FIXED_OFF_HOURS"

    # Epoch 3: constituent rebalance
    ep3 = reg.get_epoch_for_timestamp("2026-01-29T12:00:00Z")
    assert ep3.price_index_method == "REBALANCED_CONSTITUENTS_33PCT_EACH_PAXG_1PCT_FIXED_OFF_HOURS"

    # Epoch 5: orderbook EWMA mode replaces fixed mode
    ep5 = reg.get_epoch_for_timestamp("2026-06-01T12:00:00Z")
    assert ep5.price_index_method == "ORDERBOOK_EWMA_OFF_HOURS_REPLACING_FIXED"

    # Epoch 6: US Eastern session alignment
    ep6 = reg.get_epoch_for_timestamp("2026-09-20T12:00:00Z")
    assert ep6.price_index_method == "STANDARD_REGULAR_AND_ORDERBOOK_EWMA_WEEKENDS_HOLIDAYS"
    assert ep6.tick_size == Decimal("0.01")
    assert ep6.step_size == Decimal("0.001")


def test_unknown_fields_not_backfilled() -> None:
    reg = ContractRuleEpochRegistry.from_yaml(CONFIG_PATH)
    # Early epochs must not backfill current tick/step/margin values
    for e in reg.epochs[:6]:
        assert e.tick_size is None, f"Epoch {e.epoch_id} improperly backfilled tick_size"
        assert e.step_size is None, f"Epoch {e.epoch_id} improperly backfilled step_size"
        assert e.margin_rules is None, f"Epoch {e.epoch_id} improperly backfilled margin_rules"
        assert len(e.unknown_fields) > 0
