from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import pytest

from btceth_os.research.promotion_state import inspect_promotion_state
from btceth_os.autopilot.strategy_registry import StrategyRegistry, SyntheticTestStrategy, StrategyState

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"


def test_inspect_promotion_state_canonical() -> None:
    """Canonical promotion state inspection confirms strictly zero persistent and runtime promotions."""
    report = inspect_promotion_state()
    assert report.report_version == "ROUND3B.0B"
    assert report.status == "VERIFIED"
    assert report.persistent_db_exists is True
    assert report.persistent_approved_shadow == 0
    assert report.persistent_approved_paper == 0
    assert report.runtime_total_registered == 0
    assert report.runtime_approved_shadow == 0
    assert report.runtime_approved_paper == 0
    assert report.trading_capability == 0
    assert report.all_zero_promotions_verified is True

    # Persist ROUND3B_0B_PROMOTION_STATE_AUDIT.json
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "ROUND3B_0B_PROMOTION_STATE_AUDIT.json").write_text(
        json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8"
    )


def test_inspect_promotion_state_detects_persistent_violation(tmp_path: Path) -> None:
    """If sqlite database has an approved experiment, inspector flags PROMOTION_VIOLATION."""
    db_path = tmp_path / "test_exp.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE experiments (id TEXT, status TEXT)")
    conn.execute("INSERT INTO experiments VALUES ('EXP_1', 'APPROVED_FOR_SHADOW')")
    conn.commit()
    conn.close()

    report = inspect_promotion_state(db_path=db_path)
    assert report.status == "PROMOTION_VIOLATION"
    assert report.persistent_approved_shadow == 1
    assert report.all_zero_promotions_verified is False


def test_inspect_promotion_state_detects_runtime_violation() -> None:
    """If runtime registry has an approved strategy, inspector flags PROMOTION_VIOLATION."""
    reg = StrategyRegistry()
    test_strat = SyntheticTestStrategy(strategy_id="TEST_ACTIVE", state=StrategyState.APPROVED_FOR_PAPER)
    reg.register(test_strat)

    report = inspect_promotion_state(registry=reg)
    assert report.status == "PROMOTION_VIOLATION"
    assert report.runtime_approved_paper == 1
    assert report.all_zero_promotions_verified is False
