from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from ..autopilot.strategy_registry import StrategyRegistry

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = ROOT / "artifacts" / "research" / "experiments.sqlite"


@dataclass(frozen=True)
class PromotionStateReport:
    report_version: str
    status: str
    persistent_db_path: str
    persistent_db_exists: bool
    persistent_total_experiments: int
    persistent_approved_shadow: int
    persistent_approved_paper: int
    runtime_registry_initialized: bool
    runtime_total_registered: int
    runtime_approved_shadow: int
    runtime_approved_paper: int
    trading_capability: int
    all_zero_promotions_verified: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_promotion_state(
    db_path: Optional[Path | str] = None,
    registry: Optional[StrategyRegistry] = None,
) -> PromotionStateReport:
    """Mechanically derive strategy promotion state from persistent storage and runtime registry."""
    actual_db = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    db_exists = actual_db.is_file()

    total_experiments = 0
    approved_shadow_db = 0
    approved_paper_db = 0

    if db_exists:
        conn = sqlite3.connect(str(actual_db))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='experiments'")
            if cursor.fetchone():
                cursor.execute("SELECT count(*) FROM experiments")
                row = cursor.fetchone()
                total_experiments = int(row[0]) if row else 0

                cursor.execute("SELECT count(*) FROM experiments WHERE status = 'APPROVED_FOR_SHADOW'")
                row = cursor.fetchone()
                approved_shadow_db = int(row[0]) if row else 0

                cursor.execute("SELECT count(*) FROM experiments WHERE status = 'APPROVED_FOR_PAPER'")
                row = cursor.fetchone()
                approved_paper_db = int(row[0]) if row else 0
        finally:
            conn.close()

    active_reg = registry if registry is not None else StrategyRegistry()
    all_metas = active_reg.all_metadata()
    runtime_total = len(all_metas)
    runtime_shadow = len(active_reg.get_approved_for_shadow())
    runtime_paper = len(active_reg.get_approved_for_paper())

    all_zero = (
        approved_shadow_db == 0
        and approved_paper_db == 0
        and runtime_shadow == 0
        and runtime_paper == 0
    )

    status = "VERIFIED" if all_zero else "PROMOTION_VIOLATION"

    try:
        rel_path = str(actual_db.relative_to(ROOT))
    except ValueError:
        rel_path = str(actual_db)

    return PromotionStateReport(
        report_version="ROUND3B.0B",
        status=status,
        persistent_db_path=rel_path,
        persistent_db_exists=db_exists,
        persistent_total_experiments=total_experiments,
        persistent_approved_shadow=approved_shadow_db,
        persistent_approved_paper=approved_paper_db,
        runtime_registry_initialized=True,
        runtime_total_registered=runtime_total,
        runtime_approved_shadow=runtime_shadow,
        runtime_approved_paper=runtime_paper,
        trading_capability=0,
        all_zero_promotions_verified=all_zero,
    )
