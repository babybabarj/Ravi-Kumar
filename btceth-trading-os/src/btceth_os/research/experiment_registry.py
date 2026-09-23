from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Optional

from ..core import canonical_json


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    family: str
    strategy_id: str
    variant_index: int
    hypothesis: str
    parameters: dict[str, Any]
    dataset_logical_sha256: str
    code_commit: str
    train_start_ts: int
    train_end_ts: int
    test_start_ts: int
    test_end_ts: int
    in_sample_net_return: float
    in_sample_sharpe: float
    out_of_sample_net_return: float
    out_of_sample_stressed_return: float
    out_of_sample_trades: int
    out_of_sample_sharpe: float
    max_drawdown: float
    deflated_sharpe_ratio: float
    pbo: float
    status: str  # REJECTED, APPROVED_FOR_SHADOW, APPROVED_FOR_PAPER
    rejection_reasons: list[str]
    created_at_utc: str = ""
    # Structural Strategy Extensions (Round 3)
    research_round: int = 2
    strategy_type: str = "DIRECTIONAL"
    market_neutral_target: bool = False
    gross_exposure: float = 0.0
    net_delta: float = 0.0
    capital_committed: float = 0.0
    funding_pnl: float = 0.0
    basis_pnl: float = 0.0
    execution_cost: float = 0.0
    # Series & Partition Identity Binding (Round 3B.0I)
    instrument_id: str = "BTCUSDT"
    dataset_id: str = ""

    def __post_init__(self) -> None:
        if not self.created_at_utc:
            object.__setattr__(self, "created_at_utc", datetime.now(timezone.utc).isoformat())


def compute_experiment_id(
    family: str,
    strategy_id: str,
    hypothesis: str,
    dataset_sha: str,
    parameters: dict[str, Any],
    instrument_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
) -> str:
    parts = [family, strategy_id, hypothesis, dataset_sha]
    if instrument_id:
        parts.append(instrument_id)
    if dataset_id:
        parts.append(dataset_id)
    parts.append(canonical_json(parameters))
    seed = ":".join(parts)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


class ExperimentRegistry:
    """Persistent SQLite WAL experiment registry tracking all candidate evaluations and variant counts."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    family TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    variant_index INTEGER NOT NULL,
                    hypothesis TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    dataset_logical_sha256 TEXT NOT NULL,
                    code_commit TEXT NOT NULL,
                    train_start_ts INTEGER NOT NULL,
                    train_end_ts INTEGER NOT NULL,
                    test_start_ts INTEGER NOT NULL,
                    test_end_ts INTEGER NOT NULL,
                    in_sample_net_return REAL NOT NULL,
                    in_sample_sharpe REAL NOT NULL,
                    out_of_sample_net_return REAL NOT NULL,
                    out_of_sample_stressed_return REAL NOT NULL,
                    out_of_sample_trades INTEGER NOT NULL,
                    out_of_sample_sharpe REAL NOT NULL,
                    max_drawdown REAL NOT NULL,
                    deflated_sharpe_ratio REAL NOT NULL,
                    pbo REAL NOT NULL,
                    status TEXT NOT NULL,
                    rejection_reasons_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_family ON experiments(family);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON experiments(status);")

            # Migration for Round 3 structural columns and Round 3B.0I identity columns
            extra_cols = [
                ("research_round", "INTEGER DEFAULT 2"),
                ("strategy_type", "TEXT DEFAULT 'DIRECTIONAL'"),
                ("market_neutral_target", "INTEGER DEFAULT 0"),
                ("gross_exposure", "REAL DEFAULT 0.0"),
                ("net_delta", "REAL DEFAULT 0.0"),
                ("capital_committed", "REAL DEFAULT 0.0"),
                ("funding_pnl", "REAL DEFAULT 0.0"),
                ("basis_pnl", "REAL DEFAULT 0.0"),
                ("execution_cost", "REAL DEFAULT 0.0"),
                ("instrument_id", "TEXT DEFAULT 'BTCUSDT'"),
                ("dataset_id", "TEXT DEFAULT ''"),
            ]
            for col_name, col_def in extra_cols:
                try:
                    conn.execute(f"ALTER TABLE experiments ADD COLUMN {col_name} {col_def};")
                except sqlite3.OperationalError:
                    pass

    def record_experiment(self, exp: ExperimentRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiments (
                    experiment_id, family, strategy_id, variant_index, hypothesis,
                    parameters_json, dataset_logical_sha256, code_commit,
                    train_start_ts, train_end_ts, test_start_ts, test_end_ts,
                    in_sample_net_return, in_sample_sharpe,
                    out_of_sample_net_return, out_of_sample_stressed_return,
                    out_of_sample_trades, out_of_sample_sharpe, max_drawdown,
                    deflated_sharpe_ratio, pbo, status,
                    rejection_reasons_json, created_at_utc,
                    research_round, strategy_type, market_neutral_target,
                    gross_exposure, net_delta, capital_committed,
                    funding_pnl, basis_pnl, execution_cost,
                    instrument_id, dataset_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    exp.experiment_id,
                    exp.family,
                    exp.strategy_id,
                    exp.variant_index,
                    exp.hypothesis,
                    json.dumps(exp.parameters),
                    exp.dataset_logical_sha256,
                    exp.code_commit,
                    exp.train_start_ts,
                    exp.train_end_ts,
                    exp.test_start_ts,
                    exp.test_end_ts,
                    exp.in_sample_net_return,
                    exp.in_sample_sharpe,
                    exp.out_of_sample_net_return,
                    exp.out_of_sample_stressed_return,
                    exp.out_of_sample_trades,
                    exp.out_of_sample_sharpe,
                    exp.max_drawdown,
                    exp.deflated_sharpe_ratio,
                    exp.pbo,
                    exp.status,
                    json.dumps(exp.rejection_reasons),
                    exp.created_at_utc,
                    exp.research_round,
                    exp.strategy_type,
                    1 if exp.market_neutral_target else 0,
                    exp.gross_exposure,
                    exp.net_delta,
                    exp.capital_committed,
                    exp.funding_pnl,
                    exp.basis_pnl,
                    exp.execution_cost,
                    exp.instrument_id,
                    exp.dataset_id,
                ),
            )

    def get_variants_tested_count(self, family: str) -> int:
        with self._get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM experiments WHERE family = ?;", (family,)).fetchone()
            return int(row[0]) if row else 0

    def get_total_experiments_count(self) -> int:
        with self._get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM experiments;").fetchone()
            return int(row[0]) if row else 0

    def get_all_experiments(self) -> list[ExperimentRecord]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM experiments ORDER BY rowid ASC;").fetchall()
            records = []
            for r in rows:
                keys = r.keys()
                records.append(
                    ExperimentRecord(
                        experiment_id=r["experiment_id"],
                        family=r["family"],
                        strategy_id=r["strategy_id"],
                        variant_index=r["variant_index"],
                        hypothesis=r["hypothesis"],
                        parameters=json.loads(r["parameters_json"]),
                        dataset_logical_sha256=r["dataset_logical_sha256"],
                        code_commit=r["code_commit"],
                        train_start_ts=r["train_start_ts"],
                        train_end_ts=r["train_end_ts"],
                        test_start_ts=r["test_start_ts"],
                        test_end_ts=r["test_end_ts"],
                        in_sample_net_return=r["in_sample_net_return"],
                        in_sample_sharpe=r["in_sample_sharpe"],
                        out_of_sample_net_return=r["out_of_sample_net_return"],
                        out_of_sample_stressed_return=r["out_of_sample_stressed_return"],
                        out_of_sample_trades=r["out_of_sample_trades"],
                        out_of_sample_sharpe=r["out_of_sample_sharpe"],
                        max_drawdown=r["max_drawdown"],
                        deflated_sharpe_ratio=r["deflated_sharpe_ratio"],
                        pbo=r["pbo"],
                        status=r["status"],
                        rejection_reasons=json.loads(r["rejection_reasons_json"]),
                        created_at_utc=r["created_at_utc"],
                        research_round=r["research_round"] if "research_round" in keys else 2,
                        strategy_type=r["strategy_type"] if "strategy_type" in keys else "DIRECTIONAL",
                        market_neutral_target=bool(r["market_neutral_target"]) if "market_neutral_target" in keys else False,
                        gross_exposure=r["gross_exposure"] if "gross_exposure" in keys else 0.0,
                        net_delta=r["net_delta"] if "net_delta" in keys else 0.0,
                        capital_committed=r["capital_committed"] if "capital_committed" in keys else 0.0,
                        funding_pnl=r["funding_pnl"] if "funding_pnl" in keys else 0.0,
                        basis_pnl=r["basis_pnl"] if "basis_pnl" in keys else 0.0,
                        execution_cost=r["execution_cost"] if "execution_cost" in keys else 0.0,
                        instrument_id=r["instrument_id"] if "instrument_id" in keys else "BTCUSDT",
                        dataset_id=r["dataset_id"] if "dataset_id" in keys else "",
                    )
                )
            return records

    def export_to_json(self, destination: Path | str) -> Path:
        exps = self.get_all_experiments()
        data = {
            "total_experiments": len(exps),
            "experiments": [asdict(e) for e in exps],
        }
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return dest
