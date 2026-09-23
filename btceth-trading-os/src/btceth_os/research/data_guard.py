from __future__ import annotations

import fcntl
import hashlib
import json
import re
import threading
import types
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = ROOT / "artifacts" / "research" / "holdout_access_ledger.jsonl"
LEDGER_LOCK_PATH = ROOT / "artifacts" / "research" / "holdout_access_ledger.lock"
_LEDGER_LOCK = threading.Lock()

# The Locked Historical Holdout is strictly:
# 2024-01-01 00:00:00 UTC to 2024-11-30 23:59:59.999999999 UTC
HOLDOUT_WINDOW_START_NS = 1704067200_000_000_000  # 2024-01-01T00:00:00Z
HOLDOUT_WINDOW_END_NS   = 1733011199_999_999_999  # 2024-11-30T23:59:59.999999999Z

HOLDOUT_UNLOCK_CAPABILITY = 0  # Invariant: Zero unlock capability in this phase
XAU_HOLDOUT_UNLOCK_CAPABILITY = 0  # Invariant: Zero XAU holdout unlock capability
XAU_PROSPECTIVE_PRISTINE_UNLOCK_CAPABILITY = 0  # Invariant: Zero XAU prospective pristine unlock capability


class DatasetRole(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"                  # 2020 - 2022
    VALIDATION = "VALIDATION"                    # 2023
    LOCKED_HOLDOUT = "LOCKED_HOLDOUT"            # 2024-01-01 to 2024-11-30 / XAU Locked Holdout
    PROSPECTIVE_FORWARD = "PROSPECTIVE_FORWARD"  # 2025 onwards / prospective
    SHADOW = "SHADOW"                            # Live shadow execution
    PAPER = "PAPER"                              # Live paper execution
    COMPOSITE_RESEARCH_DATASET = "COMPOSITE_RESEARCH_DATASET"  # Composite aggregate (not directly readable)
    LOCKED_PROSPECTIVE_PRISTINE = "LOCKED_PROSPECTIVE_PRISTINE"  # Locked pristine holdout (2026-09-15 21:00 UTC onward)


class ResearchOperation(str, Enum):
    HYPOTHESIS_GENERATION = "hypothesis_generation"
    FEATURE_SELECTION = "feature_selection"
    PARAMETER_TUNING = "parameter_tuning"
    STRATEGY_SELECTION = "strategy_family_selection"
    THRESHOLD_TUNING = "threshold_tuning"
    BACKTEST = "backtest"
    PROSPECTIVE_VALIDATION = "prospective_validation"
    SHADOW_EVALUATION = "shadow_evaluation"
    PAPER_EVALUATION = "paper_evaluation"
    FINAL_HOLDOUT_AUDIT = "final_holdout_audit"  # Inaccessible: HOLDOUT_UNLOCK_CAPABILITY is ZERO


class HoldoutAccessDeniedError(PermissionError):
    """Raised when an unauthorized or unverified research operation attempts data access."""
    pass


class RoleBoundaryViolationError(HoldoutAccessDeniedError):
    """Raised when an operation attempts to access rows crossing partition role boundaries."""
    pass


class LedgerIntegrityFailureError(RuntimeError):
    """Raised when the research access ledger hash chain integrity is compromised."""
    pass


@dataclass(frozen=True)
class CanonicalPartitionEntry:
    dataset_id: str
    dataset_version: str
    partition_id: str
    canonical_relative_path: Optional[str]
    physical_sha256: Optional[str]
    dataset_logical_sha256: Optional[str]
    start_ts_ns: Optional[int]
    end_ts_ns: Optional[int]
    role: DatasetRole
    parent_dataset: Optional[str] = None
    status: str = "CANONICAL"
    partition_logical_sha256: Optional[str] = None
    instrument_id: Optional[str] = None
    market_type: Optional[str] = None
    venue: Optional[str] = None

    @property
    def dataset_logical_sha(self) -> Optional[str]:
        return self.dataset_logical_sha256

    @property
    def resolved_instrument_id(self) -> str:
        if self.instrument_id:
            return self.instrument_id
        if "BTC" in self.dataset_id:
            return "BTCUSDT"
        if "ETH" in self.dataset_id:
            return "ETHUSDT"
        if "XAU" in self.dataset_id:
            return "BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT"
        return "UNKNOWN"

    @property
    def resolved_market_type(self) -> str:
        if self.market_type:
            return self.market_type
        if "XAU" in self.dataset_id:
            return "TRADFI_COMMODITY_PERP"
        return "USD_M_PERP"

    @property
    def resolved_venue(self) -> str:
        if self.venue:
            return self.venue
        return "BINANCE"


CanonicalDatasetEntry = CanonicalPartitionEntry



# Authoritative Dataset Registry
_CANONICAL_DATASETS: dict[str, CanonicalPartitionEntry] = {
    # 1. Materialized Physical Development Partitions (2020-01-01 through 2022-12-31)
    "BTCUSDT_DEV_2020_2022": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_DEV_2020_2022",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_DEV_2020_2022",
        canonical_relative_path="artifacts/research/partitions/BTCUSDT_DEV_2020_2022.parquet",
        physical_sha256="4daa270f04c5e5305b7033b745253e862fc72f17a9ff16a9d0e1c6bca5847b47",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1672527600_000_000_000,
        role=DatasetRole.DEVELOPMENT,
        parent_dataset="BTCUSDT-resampled-1h-v3.1.0",
        status="CANONICAL",
        partition_logical_sha256="28c52f2fadd47354fb95dedfbd8fad3e61f70f8bb27c0c02171cbeacd51878ff",
        instrument_id="BTCUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "ETHUSDT_DEV_2020_2022": CanonicalPartitionEntry(
        dataset_id="ETHUSDT_DEV_2020_2022",
        dataset_version="v3.1.0",
        partition_id="ETHUSDT_DEV_2020_2022",
        canonical_relative_path="artifacts/research/partitions/ETHUSDT_DEV_2020_2022.parquet",
        physical_sha256="007cdce2eca501924935090eba141889b8d26d60b941e3fcf37501aa14b50f23",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1672527600_000_000_000,
        role=DatasetRole.DEVELOPMENT,
        parent_dataset="ETHUSDT-resampled-1h-v3.1.0",
        status="CANONICAL",
        partition_logical_sha256="08a2b29a11bca8fe718a0932bd65f9a6fa4f3b2d7c300f408cd38cd9ee8b586f",
        instrument_id="ETHUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "BTCUSDT_FUNDING_DEV_2020_2022": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_FUNDING_DEV_2020_2022",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_FUNDING_DEV_2020_2022",
        canonical_relative_path="artifacts/research/partitions/BTCUSDT_FUNDING_DEV_2020_2022.parquet",
        physical_sha256="2991e597d8c80a4b11181364e95168a46a6bc1cbd0f7a7f44fbf6341c0fcad3d",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1672502400_000_000_000,
        role=DatasetRole.DEVELOPMENT,
        parent_dataset="BTCUSDT-funding-2020-01-2023-12-v3.1",
        status="CANONICAL",
        partition_logical_sha256="373724fcffbcb89b3b886f0622e3deac1c7de3e0cf0a06d4a76dc798827d490b",
        instrument_id="BTCUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "ETHUSDT_FUNDING_DEV_2020_2022": CanonicalPartitionEntry(
        dataset_id="ETHUSDT_FUNDING_DEV_2020_2022",
        dataset_version="v3.1.0",
        partition_id="ETHUSDT_FUNDING_DEV_2020_2022",
        canonical_relative_path="artifacts/research/partitions/ETHUSDT_FUNDING_DEV_2020_2022.parquet",
        physical_sha256="97ab50866782c4c2b99eff0caafbba23cb8522180bf460f23b73f8bd368042f8",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1672502400_000_000_000,
        role=DatasetRole.DEVELOPMENT,
        parent_dataset="ETHUSDT-funding-2020-01-2023-12-v3.1",
        status="CANONICAL",
        partition_logical_sha256="e558a7c6c45f56d10c5dc970afe66f1b2797d965bef2b6ba2bf875564fbe966f",
        instrument_id="ETHUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),

    # 2. Materialized Physical Validation Partitions (2023-01-01 through 2023-12-31)
    "BTCUSDT_VAL_2023": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_VAL_2023",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_VAL_2023",
        canonical_relative_path="artifacts/research/partitions/BTCUSDT_VAL_2023.parquet",
        physical_sha256="2db5dd7bdd758f3ae07420f443feb42b4319f59462b4697d7d72e524e0027c85",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1672531200_000_000_000,
        end_ts_ns=1704063600_000_000_000,
        role=DatasetRole.VALIDATION,
        parent_dataset="BTCUSDT-resampled-1h-v3.1.0",
        status="CANONICAL",
        partition_logical_sha256="3f7974f454d102bc2903161029994f6008a33b1c55238f5bbf382b5045a07220",
        instrument_id="BTCUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "ETHUSDT_VAL_2023": CanonicalPartitionEntry(
        dataset_id="ETHUSDT_VAL_2023",
        dataset_version="v3.1.0",
        partition_id="ETHUSDT_VAL_2023",
        canonical_relative_path="artifacts/research/partitions/ETHUSDT_VAL_2023.parquet",
        physical_sha256="2ce4e724e3e082dac0976e2192304780cc1c0ea4ad977e12da1497e4b0f52ff7",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1672531200_000_000_000,
        end_ts_ns=1704063600_000_000_000,
        role=DatasetRole.VALIDATION,
        parent_dataset="ETHUSDT-resampled-1h-v3.1.0",
        status="CANONICAL",
        partition_logical_sha256="6fb52c9877b80f28dcbb03a9599982e93d5ed72c8b8040ef7c26b3b514caef4a",
        instrument_id="ETHUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "BTCUSDT_FUNDING_VAL_2023": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_FUNDING_VAL_2023",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_FUNDING_VAL_2023",
        canonical_relative_path="artifacts/research/partitions/BTCUSDT_FUNDING_VAL_2023.parquet",
        physical_sha256="5f24907c3cd87c0465cd81356f192143c9f831c671f9a1aeeb9f6a39740614d3",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1672531200_000_000_000,
        end_ts_ns=1704038400_000_000_000,
        role=DatasetRole.VALIDATION,
        parent_dataset="BTCUSDT-funding-2020-01-2023-12-v3.1",
        status="CANONICAL",
        partition_logical_sha256="390a90930d92f2e1e1b92fd7301d12f5f38d46dd33eed512dc6291d8d9a8cc82",
        instrument_id="BTCUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "ETHUSDT_FUNDING_VAL_2023": CanonicalPartitionEntry(
        dataset_id="ETHUSDT_FUNDING_VAL_2023",
        dataset_version="v3.1.0",
        partition_id="ETHUSDT_FUNDING_VAL_2023",
        canonical_relative_path="artifacts/research/partitions/ETHUSDT_FUNDING_VAL_2023.parquet",
        physical_sha256="16d3edbb7b031847bcf0dfb9c75c88dd643683f9d555b0bee4bd1fb6f1977462",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1672531200_000_000_000,
        end_ts_ns=1704038400_000_000_000,
        role=DatasetRole.VALIDATION,
        parent_dataset="ETHUSDT-funding-2020-01-2023-12-v3.1",
        status="CANONICAL",
        partition_logical_sha256="aba4f0b276662f6c79a5643aa8e8a42c64a69493f8f66f63c4deb67095b1cbd8",
        instrument_id="ETHUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),

    # 3. Canonical Aliases (repointed strictly to true physical partitions)
    "BTCUSDT_DEV": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_DEV",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_DEV_2020_2022",
        canonical_relative_path="artifacts/research/partitions/BTCUSDT_DEV_2020_2022.parquet",
        physical_sha256="4daa270f04c5e5305b7033b745253e862fc72f17a9ff16a9d0e1c6bca5847b47",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.DEVELOPMENT,
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1672527600_000_000_000,
        parent_dataset="BTCUSDT_DEV_2020_2022",
        status="CANONICAL",
        partition_logical_sha256="28c52f2fadd47354fb95dedfbd8fad3e61f70f8bb27c0c02171cbeacd51878ff",
        instrument_id="BTCUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "BTCUSDT_VAL": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_VAL",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_VAL_2023",
        canonical_relative_path="artifacts/research/partitions/BTCUSDT_VAL_2023.parquet",
        physical_sha256="2db5dd7bdd758f3ae07420f443feb42b4319f59462b4697d7d72e524e0027c85",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.VALIDATION,
        start_ts_ns=1672531200_000_000_000,
        end_ts_ns=1704063600_000_000_000,
        parent_dataset="BTCUSDT_VAL_2023",
        status="CANONICAL",
        partition_logical_sha256="3f7974f454d102bc2903161029994f6008a33b1c55238f5bbf382b5045a07220",
        instrument_id="BTCUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "ETHUSDT_DEV": CanonicalPartitionEntry(
        dataset_id="ETHUSDT_DEV",
        dataset_version="v3.1.0",
        partition_id="ETHUSDT_DEV_2020_2022",
        canonical_relative_path="artifacts/research/partitions/ETHUSDT_DEV_2020_2022.parquet",
        physical_sha256="007cdce2eca501924935090eba141889b8d26d60b941e3fcf37501aa14b50f23",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.DEVELOPMENT,
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1672527600_000_000_000,
        parent_dataset="ETHUSDT_DEV_2020_2022",
        status="CANONICAL",
        partition_logical_sha256="08a2b29a11bca8fe718a0932bd65f9a6fa4f3b2d7c300f408cd38cd9ee8b586f",
        instrument_id="ETHUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "ETHUSDT_VAL": CanonicalPartitionEntry(
        dataset_id="ETHUSDT_VAL",
        dataset_version="v3.1.0",
        partition_id="ETHUSDT_VAL_2023",
        canonical_relative_path="artifacts/research/partitions/ETHUSDT_VAL_2023.parquet",
        physical_sha256="2ce4e724e3e082dac0976e2192304780cc1c0ea4ad977e12da1497e4b0f52ff7",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.VALIDATION,
        start_ts_ns=1672531200_000_000_000,
        end_ts_ns=1704063600_000_000_000,
        parent_dataset="ETHUSDT_VAL_2023",
        status="CANONICAL",
        partition_logical_sha256="6fb52c9877b80f28dcbb03a9599982e93d5ed72c8b8040ef7c26b3b514caef4a",
        instrument_id="ETHUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),

    # 4. Composite Datasets (Spanning Dev + Val; NOT directly readable)
    "BTCUSDT-resampled-1h-v3.1.0": CanonicalPartitionEntry(
        dataset_id="BTCUSDT-resampled-1h-v3.1.0",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_2020_2023_1H",
        canonical_relative_path="artifacts/research/silver_v3/BTCUSDT-resampled-1h-v3.1.0.parquet",
        physical_sha256="f706dfa1fc637e46fa6604b19fd8dea15edfebaa3478cc859ed1d23111eff70e",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1704063600_000_000_000,
        role=DatasetRole.COMPOSITE_RESEARCH_DATASET,
        parent_dataset="dataset_v3.0.0",
        status="NOT_DIRECTLY_READABLE",
        instrument_id="BTCUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "ETHUSDT-resampled-1h-v3.1.0": CanonicalPartitionEntry(
        dataset_id="ETHUSDT-resampled-1h-v3.1.0",
        dataset_version="v3.1.0",
        partition_id="ETHUSDT_2020_2023_1H",
        canonical_relative_path="artifacts/research/silver_v3/ETHUSDT-resampled-1h-v3.1.0.parquet",
        physical_sha256="64cd9f71654fe6e9791fb379b2fdf7891d3d27fd8f7456b97c0d31e892b8e510",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1704063600_000_000_000,
        role=DatasetRole.COMPOSITE_RESEARCH_DATASET,
        parent_dataset="dataset_v3.0.0",
        status="NOT_DIRECTLY_READABLE",
        instrument_id="ETHUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "BTCUSDT-funding-2020-01-2023-12-v3.1": CanonicalPartitionEntry(
        dataset_id="BTCUSDT-funding-2020-01-2023-12-v3.1",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_FUNDING_2020_2023",
        canonical_relative_path="artifacts/research/silver_v3/BTCUSDT-funding-2020-01-2023-12-v3.1.parquet",
        physical_sha256="a966c54a24d6ab8558221b329c8ba2f024fa981738ca9b368bf6ae1d6668bdf6",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1704038400_000_000_000,
        role=DatasetRole.COMPOSITE_RESEARCH_DATASET,
        parent_dataset="dataset_v3.0.0",
        status="NOT_DIRECTLY_READABLE",
        instrument_id="BTCUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "ETHUSDT-funding-2020-01-2023-12-v3.1": CanonicalPartitionEntry(
        dataset_id="ETHUSDT-funding-2020-01-2023-12-v3.1",
        dataset_version="v3.1.0",
        partition_id="ETHUSDT_FUNDING_2020_2023",
        canonical_relative_path="artifacts/research/silver_v3/ETHUSDT-funding-2020-01-2023-12-v3.1.parquet",
        physical_sha256="89a22768444ebb06b618fd2e30699dc020c46ccb38ae804a8cf164874eb6462b",
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1704038400_000_000_000,
        role=DatasetRole.COMPOSITE_RESEARCH_DATASET,
        parent_dataset="dataset_v3.0.0",
        status="NOT_DIRECTLY_READABLE",
        instrument_id="ETHUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "dataset_v3.1.0": CanonicalPartitionEntry(
        dataset_id="dataset_v3.1.0",
        dataset_version="v3.1.0",
        partition_id="FULL_DEV_2020_2023",
        canonical_relative_path=None,
        physical_sha256=None,
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.COMPOSITE_RESEARCH_DATASET,
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1704067199_000_000_000,
        parent_dataset="dataset_v3.0.0",
        status="NOT_DIRECTLY_READABLE",
    ),
    "BTCUSDT_AGGREGATE_DEV_VAL": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_AGGREGATE_DEV_VAL",
        dataset_version="v3.1.0",
        partition_id="BTCUSDT_AGGREGATE_DEV_VAL",
        canonical_relative_path=None,
        physical_sha256=None,
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.COMPOSITE_RESEARCH_DATASET,
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1704067199_000_000_000,
        parent_dataset="dataset_v3.1.0",
        status="NOT_DIRECTLY_READABLE",
        instrument_id="BTCUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),
    "ETHUSDT_AGGREGATE_DEV_VAL": CanonicalPartitionEntry(
        dataset_id="ETHUSDT_AGGREGATE_DEV_VAL",
        dataset_version="v3.1.0",
        partition_id="ETHUSDT_AGGREGATE_DEV_VAL",
        canonical_relative_path=None,
        physical_sha256=None,
        dataset_logical_sha256="a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930",
        role=DatasetRole.COMPOSITE_RESEARCH_DATASET,
        start_ts_ns=1577836800_000_000_000,
        end_ts_ns=1704067199_000_000_000,
        parent_dataset="dataset_v3.1.0",
        status="NOT_DIRECTLY_READABLE",
        instrument_id="ETHUSDT",
        market_type="USD_M_PERP",
        venue="BINANCE",
    ),

    # 5. Locked 2024 Holdout
    "BTCUSDT_2024_HOLDOUT": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_2024_HOLDOUT",
        dataset_version="v3.1.0",
        partition_id="HOLDOUT_2024",
        canonical_relative_path=None,
        physical_sha256=None,
        dataset_logical_sha256=None,
        role=DatasetRole.LOCKED_HOLDOUT,
        start_ts_ns=HOLDOUT_WINDOW_START_NS,
        end_ts_ns=HOLDOUT_WINDOW_END_NS,
        parent_dataset="dataset_v3.1.0",
        status="LOCKED_UNREGISTERED_FOR_READ",
    ),

    # 6. Prospective (Unmaterialized Snapshot Required)
    "BTCUSDT_2025_PROSPECTIVE": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_2025_PROSPECTIVE",
        dataset_version="v3.2.0_prospective",
        partition_id="PROSPECTIVE_2025",
        canonical_relative_path=None,
        physical_sha256=None,
        dataset_logical_sha256=None,
        role=DatasetRole.PROSPECTIVE_FORWARD,
        start_ts_ns=1735689600_000_000_000,
        end_ts_ns=1767225599_000_000_000,
        parent_dataset=None,
        status="PROSPECTIVE_UNMATERIALIZED",
    ),
    "BTCUSDT_2026_LIVE_FORWARD": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_2026_LIVE_FORWARD",
        dataset_version="v3.3.0_prospective",
        partition_id="PROSPECTIVE_2026",
        canonical_relative_path=None,
        physical_sha256=None,
        dataset_logical_sha256=None,
        role=DatasetRole.PROSPECTIVE_FORWARD,
        start_ts_ns=1767225600_000_000_000,
        end_ts_ns=1798761599_000_000_000,
        parent_dataset=None,
        status="PROSPECTIVE_UNMATERIALIZED",
    ),
    "BTCUSDT_PROSPECTIVE_2025": CanonicalPartitionEntry(
        dataset_id="BTCUSDT_PROSPECTIVE_2025",
        dataset_version="v3.2.0_prospective",
        partition_id="PROSPECTIVE_2025",
        canonical_relative_path=None,
        physical_sha256=None,
        dataset_logical_sha256=None,
        role=DatasetRole.PROSPECTIVE_FORWARD,
        start_ts_ns=1735689600_000_000_000,
        end_ts_ns=1767225599_000_000_000,
        parent_dataset=None,
        status="PROSPECTIVE_UNMATERIALIZED",
    ),
    # -----------------------------------------------------------------
    # XAUUSDT TradFi Commodity Perpetual Partitions (V2 Canonical)
    # -----------------------------------------------------------------
    "XAUUSDT_DEV_2026_01_04_V2": CanonicalPartitionEntry(
        dataset_id="XAUUSDT_DEV_2026_01_04_V2",
        dataset_version="v2.0.0",
        partition_id="XAUUSDT_DEV_2026_01_04_V2",
        canonical_relative_path="artifacts/research/partitions/XAUUSDT_DEV_2026_01_04_V2.parquet",
        physical_sha256="2a3cc4de1155fc126ef5a40d53b97ed4a7e24e51d08ca0c32458788e9bedeaa9",
        dataset_logical_sha256="0c344d982d4611afd284cd56552f848b82b98c894d274410566a9331e67dc52b",
        start_ts_ns=1767657600_000_000_000,
        end_ts_ns=1777593599_999_999_000,
        role=DatasetRole.DEVELOPMENT,
        parent_dataset="XAUUSDT-resampled-1m-silver-v2",
        status="CANONICAL",
        partition_logical_sha256="73a11ad96ba0c40a075c7f43a21bf9c1148adfb72ef7c57a242304585bcdd99f",
        instrument_id="BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
        market_type="TRADFI_COMMODITY_PERP",
        venue="BINANCE",
    ),
    "XAUUSDT_VAL_2026_05_07_V2": CanonicalPartitionEntry(
        dataset_id="XAUUSDT_VAL_2026_05_07_V2",
        dataset_version="v2.0.0",
        partition_id="XAUUSDT_VAL_2026_05_07_V2",
        canonical_relative_path="artifacts/research/partitions/XAUUSDT_VAL_2026_05_07_V2.parquet",
        physical_sha256="67197b555a2ad8beca834c9a8353f0d1cdecdacf019868a9d58e43e809983fc0",
        dataset_logical_sha256="0c344d982d4611afd284cd56552f848b82b98c894d274410566a9331e67dc52b",
        start_ts_ns=1777593600_000_000_000,
        end_ts_ns=1785542399_999_999_000,
        role=DatasetRole.VALIDATION,
        parent_dataset="XAUUSDT-resampled-1m-silver-v2",
        status="CANONICAL",
        partition_logical_sha256="8226a4754ddd9abd5ee848af9fd4c08e010016114c86f4d812f54c9fa19badd8",
        instrument_id="BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
        market_type="TRADFI_COMMODITY_PERP",
        venue="BINANCE",
    ),
    "XAUUSDT_HOLDOUT_2026_08_09_V2": CanonicalPartitionEntry(
        dataset_id="XAUUSDT_HOLDOUT_2026_08_09_V2",
        dataset_version="v2.0.0",
        partition_id="XAUUSDT_HOLDOUT_2026_08_09_V2",
        canonical_relative_path="artifacts/research/partitions/XAUUSDT_HOLDOUT_2026_08_09_V2.parquet",
        physical_sha256="46bc3af674b466c68bd9e421c8fa46e54afa0751dc48952fe1e5e4a712771687",
        dataset_logical_sha256="0c344d982d4611afd284cd56552f848b82b98c894d274410566a9331e67dc52b",
        start_ts_ns=1785542400_000_000_000,
        end_ts_ns=1789505999_999_999_000,
        role=DatasetRole.LOCKED_HOLDOUT,
        parent_dataset="XAUUSDT-resampled-1m-silver-v2",
        status="LOCKED_UNREGISTERED_FOR_READ",
        partition_logical_sha256="62f11d462ddc6a9d2dd4568c5205839c1bb643bc3c49daf3ec8bcc96967da0cd",
        instrument_id="BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
        market_type="TRADFI_COMMODITY_PERP",
        venue="BINANCE",
    ),
    "XAUUSDT_PROSPECTIVE_PRISTINE_V2": CanonicalPartitionEntry(
        dataset_id="XAUUSDT_PROSPECTIVE_PRISTINE_V2",
        dataset_version="v2.0.0",
        partition_id="XAUUSDT_PROSPECTIVE_PRISTINE_V2",
        canonical_relative_path="artifacts/research/partitions/XAUUSDT_PROSPECTIVE_PRISTINE_V2.parquet",
        physical_sha256="cc5a246be21fad4f14b1dc1fb8312c203f29c90fa26da17bf1a917b9fe338ff9",
        dataset_logical_sha256="0c344d982d4611afd284cd56552f848b82b98c894d274410566a9331e67dc52b",
        start_ts_ns=1789506000_000_000_000,
        end_ts_ns=1790121599_999_999_000,
        role=DatasetRole.LOCKED_PROSPECTIVE_PRISTINE,
        parent_dataset="XAUUSDT-resampled-1m-silver-v2",
        status="LOCKED_UNREGISTERED_FOR_READ",
        partition_logical_sha256="eea913f691081f363f0c82c1f5c0f9d20a5c5dbc59db09a87edcb6d339befd27",
        instrument_id="BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
        market_type="TRADFI_COMMODITY_PERP",
        venue="BINANCE",
    ),
    # XAUUSDT V1 Partitions (Preserved for backwards compatibility)
    "XAUUSDT_DEV_2026_01_04": CanonicalPartitionEntry(
        dataset_id="XAUUSDT_DEV_2026_01_04",
        dataset_version="v1.0.0",
        partition_id="XAUUSDT_DEV_2026_01_04",
        canonical_relative_path="artifacts/research/partitions/XAUUSDT_DEV_2026_01_04.parquet",
        physical_sha256="18bf9b2842ca60b87579574390384a27a4c6cacd2405f222833fa07495e4fb09",
        dataset_logical_sha256="a1186570ec816a63aad721c5f8764a47da1d398ec8c4a22a3e970cbcd8ea7bc7",
        start_ts_ns=1767657600_000_000_000,
        end_ts_ns=1777593599_999_000_000,
        role=DatasetRole.DEVELOPMENT,
        parent_dataset="XAUUSDT-resampled-1m-silver",
        status="CANONICAL",
        partition_logical_sha256="7dd83570b44b59e1c494ebd82024c542529425febf8fd16519ab3aab728250ea",
        instrument_id="BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
        market_type="TRADFI_COMMODITY_PERP",
        venue="BINANCE",
    ),
    "XAUUSDT_VAL_2026_05_07": CanonicalPartitionEntry(
        dataset_id="XAUUSDT_VAL_2026_05_07",
        dataset_version="v1.0.0",
        partition_id="XAUUSDT_VAL_2026_05_07",
        canonical_relative_path="artifacts/research/partitions/XAUUSDT_VAL_2026_05_07.parquet",
        physical_sha256="798a40f1fdf43c41cb43e1f70a2aaef9eea7c0587e02dbfb60a18cc46cc4e345",
        dataset_logical_sha256="a1186570ec816a63aad721c5f8764a47da1d398ec8c4a22a3e970cbcd8ea7bc7",
        start_ts_ns=1777593600_000_000_000,
        end_ts_ns=1785542399_999_000_000,
        role=DatasetRole.VALIDATION,
        parent_dataset="XAUUSDT-resampled-1m-silver",
        status="CANONICAL",
        partition_logical_sha256="2c70629ba897d2125e3a701beda358139cd2fadd814d6faa30cff046d257bfa7",
        instrument_id="BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
        market_type="TRADFI_COMMODITY_PERP",
        venue="BINANCE",
    ),
    "XAUUSDT_HOLDOUT_2026_08_09": CanonicalPartitionEntry(
        dataset_id="XAUUSDT_HOLDOUT_2026_08_09",
        dataset_version="v1.0.0",
        partition_id="XAUUSDT_HOLDOUT_2026_08_09",
        canonical_relative_path="artifacts/research/partitions/XAUUSDT_HOLDOUT_2026_08_09.parquet",
        physical_sha256="c9bb1b75a9183ce036091bf83b15613193dc9b84f3535eb65c1daeda63c4aacd",
        dataset_logical_sha256="a1186570ec816a63aad721c5f8764a47da1d398ec8c4a22a3e970cbcd8ea7bc7",
        start_ts_ns=1785542400_000_000_000,
        end_ts_ns=1789505999_999_000_000,
        role=DatasetRole.LOCKED_HOLDOUT,
        parent_dataset="XAUUSDT-resampled-1m-silver",
        status="LOCKED_UNREGISTERED_FOR_READ",
        partition_logical_sha256="93c9d26ea25298cf92c94866f9df526775e5c74eedd141649367e514a44b9fe3",
        instrument_id="BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
        market_type="TRADFI_COMMODITY_PERP",
        venue="BINANCE",
    ),
    "XAUUSDT_PROSPECTIVE_PRISTINE": CanonicalPartitionEntry(
        dataset_id="XAUUSDT_PROSPECTIVE_PRISTINE",
        dataset_version="v1.0.0",
        partition_id="XAUUSDT_PROSPECTIVE_PRISTINE",
        canonical_relative_path="artifacts/research/partitions/XAUUSDT_PROSPECTIVE_PRISTINE.parquet",
        physical_sha256="169fd170a0825f52ef4d8d408056aca0e2ee389b4a56df3e9e2dd18979c24c94",
        dataset_logical_sha256="a1186570ec816a63aad721c5f8764a47da1d398ec8c4a22a3e970cbcd8ea7bc7",
        start_ts_ns=1789506000_000_000_000,
        end_ts_ns=1790121599_999_000_000,
        role=DatasetRole.LOCKED_PROSPECTIVE_PRISTINE,
        parent_dataset="XAUUSDT-resampled-1m-silver",
        status="LOCKED_UNREGISTERED_FOR_READ",
        partition_logical_sha256="acca92932276b18e69acf394a52995918e994add0dc6fdb5a89573c3625a615f",
        instrument_id="BINANCE:TRADFI_COMMODITY_PERP:XAUUSDT",
        market_type="TRADFI_COMMODITY_PERP",
        venue="BINANCE",
    ),
}

CANONICAL_DATASET_REGISTRY: Mapping[str, CanonicalPartitionEntry] = types.MappingProxyType(_CANONICAL_DATASETS)


def resolve_dataset_metadata(dataset_id: str, close_col: Optional[str] = None, *, strict: bool = False) -> dict[str, Optional[str]]:
    """Deterministically resolve instrument_id, market_type, venue, and dataset_id from registry or dataset_id."""
    entry = CANONICAL_DATASET_REGISTRY.get(dataset_id)
    if entry is not None:
        if strict:
            inst = entry.instrument_id
            mkt = entry.market_type
            ven = entry.venue
        else:
            inst = entry.resolved_instrument_id
            mkt = entry.resolved_market_type
            ven = entry.resolved_venue
    else:
        if strict:
            inst = None
            mkt = None
            ven = None
        else:
            inst = "BTCUSDT" if "BTC" in dataset_id else ("ETHUSDT" if "ETH" in dataset_id else "UNKNOWN")
            mkt = "USD_M_PERP"
            ven = "BINANCE"

    # If close_col explicitly indicates SPOT or PERP, prioritize that column semantics
    if close_col:
        c_lower = close_col.lower()
        if "spot" in c_lower:
            mkt = "SPOT"
        elif "perp" in c_lower:
            mkt = "USD_M_PERP"

    return {
        "dataset_id": dataset_id,
        "instrument_id": inst,
        "market_type": mkt,
        "venue": ven,
    }


def register_canonical_dataset(entry: CanonicalPartitionEntry) -> None:
    """Register a new canonical dataset entry in memory (immutable in production)."""
    raise TypeError(
        "CANONICAL_DATASET_REGISTRY is immutable in production. "
        "Use explicit dependency injection via the 'registry' parameter in tests."
    )


def corroborate_parquet_timestamps(p_obj: Path) -> tuple[int, int]:
    """Inspect Parquet row group statistics or ts_event_ns column values.

    Returns (min_ts_ns, max_ts_ns).
    Raises HoldoutAccessDeniedError if file cannot be parsed or if holdout window is violated.
    """
    try:
        meta = pq.read_metadata(p_obj)
    except Exception as e:
        raise HoldoutAccessDeniedError(f"DATASET_METADATA_INVALID: Failed to inspect Parquet metadata on {p_obj.name}: {e}")

    overall_min: Optional[int] = None
    overall_max: Optional[int] = None
    all_stats_set = True

    for i in range(meta.num_row_groups):
        rg = meta.row_group(i)
        ts_col_idx: Optional[int] = None
        for c in range(rg.num_columns):
            col = rg.column(c)
            if col.path_in_schema == "ts_event_ns" or col.path_in_schema.endswith(".ts_event_ns"):
                ts_col_idx = c
                if col.is_stats_set and col.statistics.has_min_max:
                    rg_min = col.statistics.min
                    rg_max = col.statistics.max
                    if overall_min is None or rg_min < overall_min:
                        overall_min = rg_min
                    if overall_max is None or rg_max > overall_max:
                        overall_max = rg_max
                else:
                    all_stats_set = False
                break
        if ts_col_idx is None:
            all_stats_set = False

    if not all_stats_set or overall_min is None or overall_max is None:
        try:
            tbl = pq.read_table(p_obj, columns=["ts_event_ns"])
            ts_series = tbl["ts_event_ns"].to_pylist()
            if not ts_series:
                raise ValueError("Parquet file has no rows in ts_event_ns")
            overall_min = min(ts_series)
            overall_max = max(ts_series)
        except Exception as e:
            raise HoldoutAccessDeniedError(f"DATASET_METADATA_INVALID: Failed to read ts_event_ns from {p_obj.name}: {e}")

    # Corroborate against 2024 holdout firewall
    # Invariant: If ANY row falls in [HOLDOUT_WINDOW_START_NS, HOLDOUT_WINDOW_END_NS], fail closed!
    if (overall_min <= HOLDOUT_WINDOW_END_NS) and (overall_max >= HOLDOUT_WINDOW_START_NS):
        raise HoldoutAccessDeniedError(
            f"HOLDOUT_FIREWALL_VIOLATION: Physical Parquet rows in {p_obj.name} intersect locked 2024 holdout window "
            f"([{overall_min}, {overall_max}] overlaps [{HOLDOUT_WINDOW_START_NS}, {HOLDOUT_WINDOW_END_NS}]). "
            f"HOLDOUT_UNLOCK_CAPABILITY is ZERO."
        )

    return overall_min, overall_max


def sanitize_payload_for_logging(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure no API keys, secrets, tokens, or credential-bearing URLs are logged."""
    sanitized = {}
    secret_patterns = re.compile(r"(key|secret|token|password|auth|credential)", re.IGNORECASE)
    url_creds = re.compile(r"://([^:@]+):([^@]+)@")
    
    for k, v in data.items():
        if secret_patterns.search(str(k)):
            sanitized[k] = "[REDACTED_SECRET]"
        elif isinstance(v, str):
            sanitized[k] = url_creds.sub("://[REDACTED_USER]:[REDACTED_PASS]@", v)
        else:
            sanitized[k] = v
    return sanitized


def compute_canonical_json_sha256(payload: dict[str, Any]) -> str:
    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def _get_last_ledger_chain_state(ledger_path: Optional[Path] = None) -> tuple[int, str]:
    """Read the last sequence number and entry_sha256 from the ledger file."""
    target = ledger_path or LEDGER_PATH
    if not target.is_file():
        return 0, "0" * 64
    
    lines = [line.strip() for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return 0, "0" * 64
    
    try:
        last_entry = json.loads(lines[-1])
        seq = int(last_entry.get("sequence", 0))
        last_sha = str(last_entry.get("entry_sha256", "0" * 64))
        return seq, last_sha
    except Exception:
        return 0, "0" * 64


def _verify_access_ledger_integrity_unlocked(
    ledger_path: Optional[Path] = None,
    require_exists: bool = False,
) -> tuple[bool, int, str, dict[str, Any]]:
    """Cryptographically verify the research access ledger hash chain without locking."""
    target = ledger_path or LEDGER_PATH
    if not target.is_file():
        if require_exists:
            return False, 0, "LEDGER_MISSING", {"total_entries": 0, "allowed_holdout_accesses": 0, "allowed_pristine_accesses": 0}
        return True, 0, "LEDGER_EMPTY", {"total_entries": 0, "allowed_holdout_accesses": 0, "allowed_pristine_accesses": 0}
    
    lines = [line.strip() for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        if require_exists:
            return False, 0, "LEDGER_EMPTY", {"total_entries": 0, "allowed_holdout_accesses": 0, "allowed_pristine_accesses": 0}
        return True, 0, "LEDGER_EMPTY", {"total_entries": 0, "allowed_holdout_accesses": 0, "allowed_pristine_accesses": 0}
    
    expected_prev = "0" * 64
    allowed_holdout_accesses = 0
    blocked_holdout_accesses = 0
    allowed_pristine_accesses = 0
    blocked_pristine_accesses = 0
    
    for idx, raw in enumerate(lines, 1):
        try:
            entry = json.loads(raw)
        except Exception as e:
            return False, idx - 1, f"JSON_CORRUPTION_LINE_{idx}: {e}", {}
            
        seq = entry.get("sequence")
        prev_sha = entry.get("previous_entry_sha256")
        payload_sha = entry.get("entry_payload_sha256")
        entry_sha = entry.get("entry_sha256")
        
        # Sequence check
        if seq != idx:
            return False, idx - 1, f"SEQUENCE_GAP_AT_LINE_{idx}: expected {idx}, got {seq}", {}
            
        # Hash chain continuity
        if prev_sha != expected_prev:
            return False, idx - 1, f"HASH_CHAIN_BROKEN_LINE_{idx}: expected {expected_prev}, got {prev_sha}", {}
            
        # Payload verification
        clean_payload = {
            k: v for k, v in entry.items()
            if k not in ("sequence", "previous_entry_sha256", "entry_payload_sha256", "entry_sha256")
        }
        recomputed_payload_sha = compute_canonical_json_sha256(clean_payload)
        if recomputed_payload_sha != payload_sha:
            return False, idx - 1, f"PAYLOAD_TAMPER_DETECTED_LINE_{idx}", {}
            
        # Entry hash verification
        expected_entry_sha = hashlib.sha256(f"{seq}:{prev_sha}:{payload_sha}".encode("utf-8")).hexdigest()
        if expected_entry_sha != entry_sha:
            return False, idx - 1, f"ENTRY_SHA_TAMPER_DETECTED_LINE_{idx}", {}
            
        # Check holdout access records
        role = entry.get("dataset_role")
        decision = entry.get("decision")
        if role == DatasetRole.LOCKED_HOLDOUT.value:
            if decision == "ALLOWED":
                allowed_holdout_accesses += 1
            else:
                blocked_holdout_accesses += 1
        elif role == DatasetRole.LOCKED_PROSPECTIVE_PRISTINE.value:
            if decision == "ALLOWED":
                allowed_pristine_accesses += 1
            else:
                blocked_pristine_accesses += 1
                
        expected_prev = entry_sha
        
    summary = {
        "total_entries": len(lines),
        "allowed_holdout_accesses": allowed_holdout_accesses,
        "blocked_holdout_accesses": blocked_holdout_accesses,
        "allowed_pristine_accesses": allowed_pristine_accesses,
        "blocked_pristine_accesses": blocked_pristine_accesses,
        "last_entry_sha": expected_prev,
    }
    return True, len(lines), "HASH_CHAIN_VERIFIED", summary


def verify_access_ledger_integrity(
    ledger_path: Optional[Path] = None,
    lock_path: Optional[Path] = None,
    require_exists: bool = False,
) -> tuple[bool, int, str, dict[str, Any]]:
    """Cryptographically verify the research access ledger hash chain with process safety.
    
    Returns (is_valid, total_entries, status_message, audit_summary).
    """
    target_ledger = ledger_path or LEDGER_PATH
    target_lock = lock_path or LEDGER_LOCK_PATH
    with _LEDGER_LOCK:
        if target_lock.parent.exists():
            with open(target_lock, "a") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
                try:
                    return _verify_access_ledger_integrity_unlocked(target_ledger, require_exists=require_exists)
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return _verify_access_ledger_integrity_unlocked(target_ledger, require_exists=require_exists)


def log_guard_event(
    operation: str,
    dataset_id: str,
    dataset_version: str,
    role: str,
    start_ns: Optional[int],
    end_ns: Optional[int],
    decision: str,  # "ALLOWED" or "BLOCKED"
    reason: str,
    research_generation: str = "ROUND3B.0C",
) -> dict[str, Any]:
    """Record an append-only, tamper-evident cryptographic hash-chain entry in the access ledger with process safety."""
    with _LEDGER_LOCK:
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER_LOCK_PATH, "a") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                # Pre-append integrity check: fail closed if chain is corrupt
                is_valid, err_idx, err_msg, _ = _verify_access_ledger_integrity_unlocked()
                if not is_valid:
                    raise LedgerIntegrityFailureError(
                        f"LEDGER_INTEGRITY_FAILURE: Access ledger hash chain is corrupted at line {err_idx}: {err_msg}. Append refused."
                    )
                
                last_seq, prev_sha = _get_last_ledger_chain_state()
                current_seq = last_seq + 1
                
                payload = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "operation": str(operation),
                    "dataset_id": str(dataset_id),
                    "dataset_version": str(dataset_version),
                    "dataset_role": str(role),
                    "requested_start_ns": start_ns,
                    "requested_end_ns": end_ns,
                    "requested_start_utc": datetime.fromtimestamp(start_ns / 1e9, tz=timezone.utc).isoformat() if start_ns else None,
                    "requested_end_utc": datetime.fromtimestamp(end_ns / 1e9, tz=timezone.utc).isoformat() if end_ns else None,
                    "decision": str(decision),
                    "reason": str(reason),
                    "research_generation": str(research_generation),
                }
                sanitized_payload = sanitize_payload_for_logging(payload)
                payload_sha = compute_canonical_json_sha256(sanitized_payload)
                
                entry_commit_str = f"{current_seq}:{prev_sha}:{payload_sha}".encode("utf-8")
                entry_sha = hashlib.sha256(entry_commit_str).hexdigest()
                
                full_entry = {
                    "sequence": current_seq,
                    "previous_entry_sha256": prev_sha,
                    "entry_payload_sha256": payload_sha,
                    "entry_sha256": entry_sha,
                    **sanitized_payload,
                }
                
                with open(LEDGER_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(full_entry) + "\n")
                    f.flush()
                    
                return full_entry
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


class ResearchDataAccessGuard:
    """Hardened research data access guard enforcing trust hierarchy, dataset identity,
    authoritative holdout boundary precedence, and restricted prospective forward operations."""

    PROSPECTIVE_ALLOWED_OPERATIONS = {
        ResearchOperation.PROSPECTIVE_VALIDATION,
        ResearchOperation.SHADOW_EVALUATION,
        ResearchOperation.PAPER_EVALUATION,
    }

    FORBIDDEN_PROSPECTIVE_OPERATIONS = {
        ResearchOperation.HYPOTHESIS_GENERATION,
        ResearchOperation.FEATURE_SELECTION,
        ResearchOperation.PARAMETER_TUNING,
        ResearchOperation.STRATEGY_SELECTION,
        ResearchOperation.THRESHOLD_TUNING,
        ResearchOperation.BACKTEST,
        ResearchOperation.FINAL_HOLDOUT_AUDIT,
    }

    @classmethod
    def check_access(
        cls,
        operation: ResearchOperation | str,
        dataset_id: str,
        dataset_version: str = "v3.1.0",
        dataset_role: Optional[DatasetRole | str] = None,
        start_ts_ns: Optional[int] = None,
        end_ts_ns: Optional[int] = None,
        file_path: Optional[Path | str] = None,
        dataset_logical_sha: Optional[str] = None,
        research_generation: str = "ROUND3B.0C",
    ) -> bool:
        """Evaluate data access request under the strict adversarial trust hierarchy."""
        return cls._check_access_internal(
            operation=operation,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            dataset_role=dataset_role,
            start_ts_ns=start_ts_ns,
            end_ts_ns=end_ts_ns,
            file_path=file_path,
            dataset_logical_sha=dataset_logical_sha,
            research_generation=research_generation,
            registry=CANONICAL_DATASET_REGISTRY,
        )

    @classmethod
    def _check_access_internal(
        cls,
        operation: ResearchOperation | str,
        dataset_id: str,
        dataset_version: str = "v3.1.0",
        dataset_role: Optional[DatasetRole | str] = None,
        start_ts_ns: Optional[int] = None,
        end_ts_ns: Optional[int] = None,
        file_path: Optional[Path | str] = None,
        dataset_logical_sha: Optional[str] = None,
        research_generation: str = "ROUND3B.0C",
        registry: Optional[Mapping[str, CanonicalPartitionEntry]] = None,
    ) -> bool:
        """Internal evaluator supporting explicit test dependency injection."""
        if not dataset_id:
            raise HoldoutAccessDeniedError("DATASET_IDENTITY_REQUIRED: An explicit dataset_id must be provided.")

        try:
            op_enum = ResearchOperation(operation) if isinstance(operation, str) else operation
        except ValueError:
            reason = f"UNKNOWN_RESEARCH_OPERATION: Operation '{operation}' is not recognized."
            log_guard_event(
                operation=str(operation),
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                role="UNKNOWN",
                start_ns=start_ts_ns,
                end_ns=end_ts_ns,
                decision="BLOCKED",
                reason=reason,
                research_generation=research_generation,
            )
            raise HoldoutAccessDeniedError(reason)

        detected_role: Optional[DatasetRole] = None
        if dataset_role:
            try:
                detected_role = DatasetRole(dataset_role)
            except ValueError:
                detected_role = None

        p_obj = Path(file_path) if file_path else None
        active_registry = registry if registry is not None else CANONICAL_DATASET_REGISTRY

        # -------------------------------------------------------------
        # TRUST LEVEL 1: Canonical Registry Verification
        # -------------------------------------------------------------
        registry_entry = active_registry.get(dataset_id)
        is_xau = (
            (registry_entry and "XAU" in str(registry_entry.instrument_id))
            or (dataset_id and "XAU" in dataset_id)
            or (p_obj and "XAU" in p_obj.name)
        )
        if registry_entry:
            # Enforce logical SHA match if caller provided one (supports both parent aggregate and partition logical SHA)
            if dataset_logical_sha is not None:
                valid_shas = {s for s in (registry_entry.dataset_logical_sha256, registry_entry.partition_logical_sha256) if s is not None}
                if valid_shas and dataset_logical_sha not in valid_shas:
                    reason = (
                        f"DATASET_IDENTITY_MISMATCH: Caller provided logical SHA {dataset_logical_sha} "
                        f"does not match canonical registry SHA(s) {valid_shas} for {dataset_id}"
                    )
                    log_guard_event(
                        operation=op_enum.value,
                        dataset_id=dataset_id,
                        dataset_version=dataset_version,
                        role=registry_entry.role.value,
                        start_ns=start_ts_ns,
                        end_ns=end_ts_ns,
                        decision="BLOCKED",
                        reason=reason,
                        research_generation=research_generation,
                    )
                    raise HoldoutAccessDeniedError(reason)

            # Check for locked holdout entries in registry
            if (
                registry_entry.status == "LOCKED_UNREGISTERED_FOR_READ"
                or registry_entry.role in (DatasetRole.LOCKED_HOLDOUT, DatasetRole.LOCKED_PROSPECTIVE_PRISTINE)
            ):
                reason = (
                    f"HOLDOUT_FIREWALL_VIOLATION: Locked dataset '{dataset_id}' (role={registry_entry.role.value}) is inaccessible. "
                    f"Operation '{op_enum.value}' denied. HOLDOUT_UNLOCK_CAPABILITY is ZERO. UNLOCK_CAPABILITY is ZERO."
                )
                log_guard_event(
                    operation=op_enum.value,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    role=registry_entry.role.value,
                    start_ns=start_ts_ns or registry_entry.start_ts_ns,
                    end_ns=end_ts_ns or registry_entry.end_ts_ns,
                    decision="BLOCKED",
                    reason=reason,
                    research_generation=research_generation,
                )
                raise HoldoutAccessDeniedError(reason)

            # Check for aggregate composite datasets (must not be read directly for research)
            if registry_entry.role == DatasetRole.COMPOSITE_RESEARCH_DATASET or registry_entry.status == "NOT_DIRECTLY_READABLE":
                reason = (
                    f"DATASET_NOT_REGISTERED_FOR_PHYSICAL_READ: Aggregate composite dataset '{dataset_id}' "
                    f"cannot be directly read for research. Must use discrete physical research partitions (DEV / VAL)."
                )
                log_guard_event(
                    operation=op_enum.value,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    role=registry_entry.role.value,
                    start_ns=start_ts_ns or registry_entry.start_ts_ns,
                    end_ns=end_ts_ns or registry_entry.end_ts_ns,
                    decision="BLOCKED",
                    reason=reason,
                    research_generation=research_generation,
                )
                raise HoldoutAccessDeniedError(reason)

            # Prospective forward files cannot be read unless they physically exist and have a registered immutable snapshot digest
            if registry_entry.role == DatasetRole.PROSPECTIVE_FORWARD:
                if registry_entry.status == "PROSPECTIVE_UNMATERIALIZED" or registry_entry.canonical_relative_path is None or registry_entry.physical_sha256 is None:
                    if p_obj is not None or op_enum in cls.PROSPECTIVE_ALLOWED_OPERATIONS:
                        if registry_entry.status == "PROSPECTIVE_UNMATERIALIZED" and p_obj is not None:
                            reason = (
                                f"PROSPECTIVE_DATASET_NOT_REGISTERED: Prospective forward dataset '{dataset_id}' "
                                f"has not been physically materialized or registered with an immutable snapshot digest."
                            )
                            log_guard_event(
                                operation=op_enum.value,
                                dataset_id=dataset_id,
                                dataset_version=dataset_version,
                                role=registry_entry.role.value,
                                start_ns=start_ts_ns,
                                end_ns=end_ts_ns,
                                decision="BLOCKED",
                                reason=reason,
                                research_generation=research_generation,
                            )
                            raise HoldoutAccessDeniedError(reason)

            # Adopt registry timestamps and role
            if start_ts_ns is None:
                start_ts_ns = registry_entry.start_ts_ns
            if end_ts_ns is None:
                end_ts_ns = registry_entry.end_ts_ns
            detected_role = registry_entry.role

        # Prospective forward file existence check
        if (detected_role == DatasetRole.PROSPECTIVE_FORWARD or (registry_entry and registry_entry.role == DatasetRole.PROSPECTIVE_FORWARD)):
            if p_obj and not p_obj.is_file():
                reason = f"PROSPECTIVE_DATASET_NOT_REGISTERED: Prospective forward file '{p_obj}' does not exist on disk."
                log_guard_event(
                    operation=op_enum.value,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    role="PROSPECTIVE_FORWARD",
                    start_ns=start_ts_ns,
                    end_ns=end_ts_ns,
                    decision="BLOCKED",
                    reason=reason,
                    research_generation=research_generation,
                )
                raise HoldoutAccessDeniedError(reason)

        # -------------------------------------------------------------
        # TRUST LEVEL 2: Physical / Metadata Verification (Parquet)
        # -------------------------------------------------------------
        if p_obj and p_obj.is_file():
            if p_obj.suffix == ".parquet":
                # 1. Row-level timestamp corroboration (catches stripped/forged metadata and holdout rows)
                actual_min_ts, actual_max_ts = corroborate_parquet_timestamps(p_obj)

                # Role boundary checks on actual row timestamps
                check_role = detected_role or (registry_entry.role if registry_entry else None)
                is_xau = (
                    (registry_entry and "XAU" in str(registry_entry.instrument_id))
                    or (dataset_id and "XAU" in dataset_id)
                    or (p_obj and "XAU" in p_obj.name)
                )

                if is_xau:
                    XAU_DEV_END_NS = 1777593600_000_000_000      # 2026-05-01 00:00:00 UTC
                    XAU_HOLDOUT_START_NS = 1785542400_000_000_000  # 2026-08-01 00:00:00 UTC

                    if check_role in (DatasetRole.DEVELOPMENT, DatasetRole.VALIDATION):
                        if actual_max_ts >= XAU_HOLDOUT_START_NS:
                            reason = (
                                f"HOLDOUT_FIREWALL_VIOLATION: File '{p_obj.name}' assigned role {check_role.value} contains "
                                f"XAU holdout rows (max ts {actual_max_ts} >= {XAU_HOLDOUT_START_NS})."
                            )
                            log_guard_event(
                                operation=op_enum.value,
                                dataset_id=dataset_id,
                                dataset_version=dataset_version,
                                role=check_role.value,
                                start_ns=actual_min_ts,
                                end_ns=actual_max_ts,
                                decision="BLOCKED",
                                reason=reason,
                                research_generation=research_generation,
                            )
                            raise HoldoutAccessDeniedError(reason)

                    if check_role == DatasetRole.DEVELOPMENT:
                        if actual_max_ts >= XAU_DEV_END_NS:
                            reason = (
                                f"ROLE_BOUNDARY_VIOLATION: File '{p_obj.name}' assigned role DEVELOPMENT contains "
                                f"post-DEV rows (max ts {actual_max_ts} >= {XAU_DEV_END_NS})."
                            )
                            log_guard_event(
                                operation=op_enum.value,
                                dataset_id=dataset_id,
                                dataset_version=dataset_version,
                                role=check_role.value,
                                start_ns=actual_min_ts,
                                end_ns=actual_max_ts,
                                decision="BLOCKED",
                                reason=reason,
                                research_generation=research_generation,
                            )
                            raise RoleBoundaryViolationError(reason)

                    if check_role == DatasetRole.VALIDATION:
                        if actual_min_ts < XAU_DEV_END_NS:
                            reason = (
                                f"ROLE_BOUNDARY_VIOLATION: File '{p_obj.name}' assigned role VALIDATION contains "
                                f"pre-VAL rows (min ts {actual_min_ts} < {XAU_DEV_END_NS})."
                            )
                            log_guard_event(
                                operation=op_enum.value,
                                dataset_id=dataset_id,
                                dataset_version=dataset_version,
                                role=check_role.value,
                                start_ns=actual_min_ts,
                                end_ns=actual_max_ts,
                                decision="BLOCKED",
                                reason=reason,
                                research_generation=research_generation,
                            )
                            raise RoleBoundaryViolationError(reason)
                else:
                    if check_role == DatasetRole.DEVELOPMENT:
                        if actual_max_ts >= 1672531200_000_000_000:
                            reason = (
                                f"ROLE_BOUNDARY_VIOLATION: File '{p_obj.name}' assigned role DEVELOPMENT contains "
                                f"post-2022 rows (max ts {actual_max_ts} >= 1672531200000000000 [2023-01-01T00:00:00Z])."
                            )
                            log_guard_event(
                                operation=op_enum.value,
                                dataset_id=dataset_id,
                                dataset_version=dataset_version,
                                role=check_role.value,
                                start_ns=actual_min_ts,
                                end_ns=actual_max_ts,
                                decision="BLOCKED",
                                reason=reason,
                                research_generation=research_generation,
                            )
                            raise RoleBoundaryViolationError(reason)

                    if check_role == DatasetRole.VALIDATION:
                        if actual_min_ts < 1672531200_000_000_000:
                            reason = (
                                f"ROLE_BOUNDARY_VIOLATION: File '{p_obj.name}' assigned role VALIDATION contains "
                                f"pre-2023 rows (min ts {actual_min_ts} < 1672531200000000000 [2023-01-01T00:00:00Z])."
                            )
                            log_guard_event(
                                operation=op_enum.value,
                                dataset_id=dataset_id,
                                dataset_version=dataset_version,
                                role=check_role.value,
                                start_ns=actual_min_ts,
                                end_ns=actual_max_ts,
                                decision="BLOCKED",
                                reason=reason,
                                research_generation=research_generation,
                            )
                            raise RoleBoundaryViolationError(reason)

                        if actual_max_ts >= HOLDOUT_WINDOW_START_NS:
                            reason = (
                                f"HOLDOUT_FIREWALL_VIOLATION: File '{p_obj.name}' assigned role VALIDATION contains "
                                f"2024 holdout rows (max ts {actual_max_ts} >= {HOLDOUT_WINDOW_START_NS})."
                            )
                            log_guard_event(
                                operation=op_enum.value,
                                dataset_id=dataset_id,
                                dataset_version=dataset_version,
                                role=check_role.value,
                                start_ns=actual_min_ts,
                                end_ns=actual_max_ts,
                                decision="BLOCKED",
                                reason=reason,
                                research_generation=research_generation,
                            )
                            raise HoldoutAccessDeniedError(reason)

                # 2. Physical SHA-256 verification
                actual_physical_sha = hashlib.sha256(p_obj.read_bytes()).hexdigest()
                if registry_entry and registry_entry.physical_sha256:
                    if actual_physical_sha != registry_entry.physical_sha256:
                        reason = (
                            f"DATASET_PHYSICAL_IDENTITY_MISMATCH: File '{p_obj.name}' physical SHA {actual_physical_sha} "
                            f"does not match registered physical SHA {registry_entry.physical_sha256} for dataset '{dataset_id}'"
                        )
                        log_guard_event(
                            operation=op_enum.value,
                            dataset_id=dataset_id,
                            dataset_version=dataset_version,
                            role=detected_role.value if detected_role else "UNKNOWN",
                            start_ns=start_ts_ns,
                            end_ns=end_ts_ns,
                            decision="BLOCKED",
                            reason=reason,
                            research_generation=research_generation,
                        )
                        raise HoldoutAccessDeniedError(reason)

                if registry_entry and registry_entry.start_ts_ns is not None and registry_entry.end_ts_ns is not None:
                    if actual_min_ts < registry_entry.start_ts_ns or actual_max_ts > registry_entry.end_ts_ns:
                        reason = (
                            f"ACTUAL_TIMESTAMP_RANGE_MISMATCH: Physical timestamp range [{actual_min_ts}, {actual_max_ts}] "
                            f"outside registered partition range [{registry_entry.start_ts_ns}, {registry_entry.end_ts_ns}] for dataset '{dataset_id}'"
                        )
                        log_guard_event(
                            operation=op_enum.value,
                            dataset_id=dataset_id,
                            dataset_version=dataset_version,
                            role=detected_role.value if detected_role else "UNKNOWN",
                            start_ns=actual_min_ts,
                            end_ns=actual_max_ts,
                            decision="BLOCKED",
                            reason=reason,
                            research_generation=research_generation,
                        )
                        raise HoldoutAccessDeniedError(reason)

                # 3. Custom Parquet metadata verification (Authoritative registry precedence)
                try:
                    meta = pq.read_metadata(p_obj)
                    if meta.schema:
                        custom = meta.schema.to_arrow_schema().metadata or {}
                        if b"dataset_role" in custom:
                            role_str = custom[b"dataset_role"].decode("utf-8")
                            if registry_entry and role_str != registry_entry.role.value:
                                reason = f"METADATA_REGISTRY_MISMATCH: File metadata role '{role_str}' != registered role '{registry_entry.role.value}'"
                                log_guard_event(
                                    operation=op_enum.value,
                                    dataset_id=dataset_id,
                                    dataset_version=dataset_version,
                                    role=role_str,
                                    start_ns=start_ts_ns,
                                    end_ns=end_ts_ns,
                                    decision="BLOCKED",
                                    reason=reason,
                                    research_generation=research_generation,
                                )
                                raise HoldoutAccessDeniedError(reason)
                            if not registry_entry:
                                detected_role = DatasetRole(role_str)
                        if b"start_ts_ns" in custom:
                            meta_start = int(custom[b"start_ts_ns"].decode("utf-8"))
                            if registry_entry and registry_entry.start_ts_ns is not None and meta_start != registry_entry.start_ts_ns:
                                reason = f"METADATA_REGISTRY_MISMATCH: File metadata start_ts_ns {meta_start} != registered start_ts_ns {registry_entry.start_ts_ns}"
                                log_guard_event(
                                    operation=op_enum.value,
                                    dataset_id=dataset_id,
                                    dataset_version=dataset_version,
                                    role=detected_role.value if detected_role else "UNKNOWN",
                                    start_ns=meta_start,
                                    end_ns=end_ts_ns,
                                    decision="BLOCKED",
                                    reason=reason,
                                    research_generation=research_generation,
                                )
                                raise HoldoutAccessDeniedError(reason)
                            if not registry_entry and start_ts_ns is None:
                                start_ts_ns = meta_start
                        if b"end_ts_ns" in custom:
                            meta_end = int(custom[b"end_ts_ns"].decode("utf-8"))
                            if registry_entry and registry_entry.end_ts_ns is not None and meta_end != registry_entry.end_ts_ns:
                                reason = f"METADATA_REGISTRY_MISMATCH: File metadata end_ts_ns {meta_end} != registered end_ts_ns {registry_entry.end_ts_ns}"
                                log_guard_event(
                                    operation=op_enum.value,
                                    dataset_id=dataset_id,
                                    dataset_version=dataset_version,
                                    role=detected_role.value if detected_role else "UNKNOWN",
                                    start_ns=start_ts_ns,
                                    end_ns=meta_end,
                                    decision="BLOCKED",
                                    reason=reason,
                                    research_generation=research_generation,
                                )
                                raise HoldoutAccessDeniedError(reason)
                            if not registry_entry and end_ts_ns is None:
                                end_ts_ns = meta_end
                        if b"dataset_logical_sha" in custom:
                            file_logical_sha = custom[b"dataset_logical_sha"].decode("utf-8")
                            if registry_entry and registry_entry.dataset_logical_sha256 and file_logical_sha != registry_entry.dataset_logical_sha256:
                                reason = f"METADATA_REGISTRY_MISMATCH: File metadata logical SHA '{file_logical_sha}' != registered SHA '{registry_entry.dataset_logical_sha256}'"
                                log_guard_event(
                                    operation=op_enum.value,
                                    dataset_id=dataset_id,
                                    dataset_version=dataset_version,
                                    role=detected_role.value if detected_role else "UNKNOWN",
                                    start_ns=start_ts_ns,
                                    end_ns=end_ts_ns,
                                    decision="BLOCKED",
                                    reason=reason,
                                    research_generation=research_generation,
                                )
                                raise HoldoutAccessDeniedError(reason)
                            if dataset_logical_sha and dataset_logical_sha != file_logical_sha:
                                reason = f"DATASET_IDENTITY_MISMATCH: Metadata SHA {file_logical_sha} != {dataset_logical_sha}"
                                log_guard_event(
                                    operation=op_enum.value,
                                    dataset_id=dataset_id,
                                    dataset_version=dataset_version,
                                    role=detected_role.value if detected_role else "UNKNOWN",
                                    start_ns=start_ts_ns,
                                    end_ns=end_ts_ns,
                                    decision="BLOCKED",
                                    reason=reason,
                                    research_generation=research_generation,
                                )
                                raise HoldoutAccessDeniedError(reason)
                except HoldoutAccessDeniedError:
                    raise
                except Exception as e:
                    reason = f"DATASET_METADATA_INVALID: Failed to inspect Parquet metadata on {p_obj.name}: {e}"
                    log_guard_event(
                        operation=op_enum.value,
                        dataset_id=dataset_id,
                        dataset_version=dataset_version,
                        role="UNKNOWN",
                        start_ns=start_ts_ns,
                        end_ns=end_ts_ns,
                        decision="BLOCKED",
                        reason=reason,
                        research_generation=research_generation,
                    )
                    raise HoldoutAccessDeniedError(reason)

        # -------------------------------------------------------------
        # TRUST LEVEL 3: Authoritative Holdout Boundary Precedence
        # -------------------------------------------------------------
        intersects_holdout = False
        if is_xau:
            XAU_HOLDOUT_WINDOW_START_NS = 1785542400_000_000_000
            XAU_HOLDOUT_WINDOW_END_NS = 1789505999_999_999_000
            if start_ts_ns is not None and end_ts_ns is not None:
                intersects_holdout = (start_ts_ns <= XAU_HOLDOUT_WINDOW_END_NS) and (end_ts_ns >= XAU_HOLDOUT_WINDOW_START_NS)
            elif start_ts_ns is not None:
                intersects_holdout = (start_ts_ns >= XAU_HOLDOUT_WINDOW_START_NS) and (start_ts_ns <= XAU_HOLDOUT_WINDOW_END_NS)
            elif end_ts_ns is not None:
                intersects_holdout = (end_ts_ns >= XAU_HOLDOUT_WINDOW_START_NS) and (end_ts_ns <= XAU_HOLDOUT_WINDOW_END_NS)

            path_indicates_holdout = bool(p_obj and ("holdout" in p_obj.name.lower() or "pristine" in p_obj.name.lower()))
            if intersects_holdout or path_indicates_holdout:
                if p_obj and "pristine" in p_obj.name.lower():
                    effective_role = DatasetRole.LOCKED_PROSPECTIVE_PRISTINE
                else:
                    effective_role = DatasetRole.LOCKED_HOLDOUT
            elif detected_role:
                effective_role = detected_role
            elif start_ts_ns and start_ts_ns >= 1777593600_000_000_000:
                effective_role = DatasetRole.VALIDATION
            elif end_ts_ns and end_ts_ns < 1777593600_000_000_000:
                effective_role = DatasetRole.DEVELOPMENT
            else:
                reason = f"DATASET_PROVENANCE_UNKNOWN: Dataset '{dataset_id}' cannot be proven. Access denied."
                log_guard_event(
                    operation=op_enum.value,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    role="UNKNOWN",
                    start_ns=start_ts_ns,
                    end_ns=end_ts_ns,
                    decision="BLOCKED",
                    reason=reason,
                    research_generation=research_generation,
                )
                raise HoldoutAccessDeniedError(reason)
        else:
            if start_ts_ns is not None and end_ts_ns is not None:
                intersects_holdout = (start_ts_ns <= HOLDOUT_WINDOW_END_NS) and (end_ts_ns >= HOLDOUT_WINDOW_START_NS)
            elif start_ts_ns is not None:
                intersects_holdout = (start_ts_ns >= HOLDOUT_WINDOW_START_NS) and (start_ts_ns <= HOLDOUT_WINDOW_END_NS)
            elif end_ts_ns is not None:
                intersects_holdout = (end_ts_ns >= HOLDOUT_WINDOW_START_NS) and (end_ts_ns <= HOLDOUT_WINDOW_END_NS)

            path_indicates_holdout = bool(p_obj and ("holdout" in p_obj.name.lower() or "2024" in p_obj.name.lower()))

            if intersects_holdout or path_indicates_holdout:
                effective_role = DatasetRole.LOCKED_HOLDOUT
            elif detected_role:
                effective_role = detected_role
            elif start_ts_ns and start_ts_ns > HOLDOUT_WINDOW_END_NS:
                effective_role = DatasetRole.PROSPECTIVE_FORWARD
            elif end_ts_ns and end_ts_ns < HOLDOUT_WINDOW_START_NS:
                effective_role = DatasetRole.DEVELOPMENT
            else:
                reason = f"DATASET_PROVENANCE_UNKNOWN: Dataset '{dataset_id}' cannot be proven. Access denied."
                log_guard_event(
                    operation=op_enum.value,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    role="UNKNOWN",
                    start_ns=start_ts_ns,
                    end_ns=end_ts_ns,
                    decision="BLOCKED",
                    reason=reason,
                    research_generation=research_generation,
                )
                raise HoldoutAccessDeniedError(reason)

        # Role boundary checks on effective role and requested timestamps
        if is_xau:
            XAU_DEV_END_NS = 1777593600_000_000_000
            XAU_HOLDOUT_START_NS = 1785542400_000_000_000

            if effective_role in (DatasetRole.DEVELOPMENT, DatasetRole.VALIDATION):
                if (end_ts_ns is not None and end_ts_ns >= XAU_HOLDOUT_START_NS) or (start_ts_ns is not None and start_ts_ns >= XAU_HOLDOUT_START_NS):
                    reason = (
                        f"HOLDOUT_FIREWALL_VIOLATION: XAU {effective_role.value} dataset '{dataset_id}' requested range "
                        f"[{start_ts_ns}, {end_ts_ns}] intersects locked XAU holdout ({XAU_HOLDOUT_START_NS})."
                    )
                    log_guard_event(
                        operation=op_enum.value,
                        dataset_id=dataset_id,
                        dataset_version=dataset_version,
                        role=effective_role.value,
                        start_ns=start_ts_ns,
                        end_ns=end_ts_ns,
                        decision="BLOCKED",
                        reason=reason,
                        research_generation=research_generation,
                    )
                    raise HoldoutAccessDeniedError(reason)

            if effective_role == DatasetRole.DEVELOPMENT:
                if (start_ts_ns is not None and start_ts_ns >= XAU_DEV_END_NS) or (end_ts_ns is not None and end_ts_ns >= XAU_DEV_END_NS):
                    reason = (
                        f"ROLE_BOUNDARY_VIOLATION: DEVELOPMENT dataset '{dataset_id}' requested range "
                        f"[{start_ts_ns}, {end_ts_ns}] violates XAU DEV cutoff ({XAU_DEV_END_NS})."
                    )
                    log_guard_event(
                        operation=op_enum.value,
                        dataset_id=dataset_id,
                        dataset_version=dataset_version,
                        role=effective_role.value,
                        start_ns=start_ts_ns,
                        end_ns=end_ts_ns,
                        decision="BLOCKED",
                        reason=reason,
                        research_generation=research_generation,
                    )
                    raise RoleBoundaryViolationError(reason)

            if effective_role == DatasetRole.VALIDATION:
                if start_ts_ns is not None and start_ts_ns < XAU_DEV_END_NS:
                    reason = (
                        f"ROLE_BOUNDARY_VIOLATION: VALIDATION dataset '{dataset_id}' requested start "
                        f"{start_ts_ns} violates XAU VAL start boundary ({XAU_DEV_END_NS})."
                    )
                    log_guard_event(
                        operation=op_enum.value,
                        dataset_id=dataset_id,
                        dataset_version=dataset_version,
                        role=effective_role.value,
                        start_ns=start_ts_ns,
                        end_ns=end_ts_ns,
                        decision="BLOCKED",
                        reason=reason,
                        research_generation=research_generation,
                    )
                    raise RoleBoundaryViolationError(reason)
        else:
            if effective_role == DatasetRole.DEVELOPMENT:
                if (start_ts_ns is not None and start_ts_ns >= 1672531200_000_000_000) or (end_ts_ns is not None and end_ts_ns >= 1672531200_000_000_000):
                    reason = (
                        f"ROLE_BOUNDARY_VIOLATION: DEVELOPMENT dataset '{dataset_id}' requested range "
                        f"[{start_ts_ns}, {end_ts_ns}] violates 2022 cutoff (1672531200000000000 [2023-01-01T00:00:00Z])."
                    )
                    log_guard_event(
                        operation=op_enum.value,
                        dataset_id=dataset_id,
                        dataset_version=dataset_version,
                        role=effective_role.value,
                        start_ns=start_ts_ns,
                        end_ns=end_ts_ns,
                        decision="BLOCKED",
                        reason=reason,
                        research_generation=research_generation,
                    )
                    raise RoleBoundaryViolationError(reason)

            if effective_role == DatasetRole.VALIDATION:
                if start_ts_ns is not None and start_ts_ns < 1672531200_000_000_000:
                    reason = (
                        f"ROLE_BOUNDARY_VIOLATION: VALIDATION dataset '{dataset_id}' requested start "
                        f"{start_ts_ns} violates 2023 start boundary (1672531200000000000 [2023-01-01T00:00:00Z])."
                    )
                    log_guard_event(
                        operation=op_enum.value,
                        dataset_id=dataset_id,
                        dataset_version=dataset_version,
                        role=effective_role.value,
                        start_ns=start_ts_ns,
                        end_ns=end_ts_ns,
                        decision="BLOCKED",
                        reason=reason,
                        research_generation=research_generation,
                    )
                    raise RoleBoundaryViolationError(reason)

                if end_ts_ns is not None and end_ts_ns >= HOLDOUT_WINDOW_START_NS:
                    reason = (
                        f"HOLDOUT_FIREWALL_VIOLATION: VALIDATION dataset '{dataset_id}' requested end "
                        f"{end_ts_ns} intersects locked 2024 holdout ({HOLDOUT_WINDOW_START_NS})."
                    )
                    log_guard_event(
                        operation=op_enum.value,
                        dataset_id=dataset_id,
                        dataset_version=dataset_version,
                        role=effective_role.value,
                        start_ns=start_ts_ns,
                        end_ns=end_ts_ns,
                        decision="BLOCKED",
                        reason=reason,
                        research_generation=research_generation,
                    )
                    raise HoldoutAccessDeniedError(reason)

        # -------------------------------------------------------------
        # TRUST LEVEL 4: Policy Enforcement
        # -------------------------------------------------------------
        # 1. LOCKED_HOLDOUT & LOCKED_PROSPECTIVE_PRISTINE Policy (UNLOCK_CAPABILITY = 0)
        if effective_role in (DatasetRole.LOCKED_HOLDOUT, DatasetRole.LOCKED_PROSPECTIVE_PRISTINE):
            reason = (
                f"HOLDOUT_FIREWALL_VIOLATION: Locked dataset '{dataset_id}' (role={effective_role.value}) is inaccessible. "
                f"Operation '{op_enum.value}' denied. HOLDOUT_UNLOCK_CAPABILITY is ZERO. UNLOCK_CAPABILITY is ZERO."
            )
            log_guard_event(
                operation=op_enum.value,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                role=effective_role.value,
                start_ns=start_ts_ns,
                end_ns=end_ts_ns,
                decision="BLOCKED",
                reason=reason,
                research_generation=research_generation,
            )
            raise HoldoutAccessDeniedError(reason)

        # 2. PROSPECTIVE_FORWARD Policy (Whitelist only: PROSPECTIVE_VALIDATION, SHADOW_EVALUATION, PAPER_EVALUATION)
        if effective_role == DatasetRole.PROSPECTIVE_FORWARD:
            if op_enum not in cls.PROSPECTIVE_ALLOWED_OPERATIONS:
                reason = (
                    f"PROSPECTIVE_TUNING_BLOCKED: Operation '{op_enum.value}' cannot access PROSPECTIVE_FORWARD data. "
                    f"Prospective forward data must remain PRISTINE and cannot be contaminated by tuning or optimization."
                )
                log_guard_event(
                    operation=op_enum.value,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    role=effective_role.value,
                    start_ns=start_ts_ns,
                    end_ns=end_ts_ns,
                    decision="BLOCKED",
                    reason=reason,
                    research_generation=research_generation,
                )
                raise HoldoutAccessDeniedError(reason)

            reason = f"PROSPECTIVE_FORWARD permitted for forward evaluation operation '{op_enum.value}'"
            log_guard_event(
                operation=op_enum.value,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                role=effective_role.value,
                start_ns=start_ts_ns,
                end_ns=end_ts_ns,
                decision="ALLOWED",
                reason=reason,
                research_generation=research_generation,
            )
            return True

        # 3. DEVELOPMENT & VALIDATION Policy
        if effective_role in (DatasetRole.DEVELOPMENT, DatasetRole.VALIDATION):
            log_guard_event(
                operation=op_enum.value,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                role=effective_role.value,
                start_ns=start_ts_ns,
                end_ns=end_ts_ns,
                decision="ALLOWED",
                reason=f"Access permitted for verified role {effective_role.value}",
                research_generation=research_generation,
            )
            return True

        # Fallback fail closed
        reason = f"DATASET_ACCESS_DENIED: Unhandled role {effective_role}"
        log_guard_event(
            operation=op_enum.value,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            role=str(effective_role),
            start_ns=start_ts_ns,
            end_ns=end_ts_ns,
            decision="BLOCKED",
            reason=reason,
            research_generation=research_generation,
        )
        raise HoldoutAccessDeniedError(reason)


def load_research_parquet(
    file_path: Path | str,
    dataset_id: str,
    operation: ResearchOperation | str = ResearchOperation.BACKTEST,
    dataset_role: Optional[DatasetRole | str] = None,
    start_ts_ns: Optional[int] = None,
    end_ts_ns: Optional[int] = None,
    dataset_logical_sha: Optional[str] = None,
) -> Any:
    """Safe Parquet loader enforcing the ResearchDataAccessGuard before disk read."""
    if not dataset_id:
        raise HoldoutAccessDeniedError("DATASET_IDENTITY_REQUIRED: Explicit dataset_id must be provided to load research parquet.")
    
    entry = CANONICAL_DATASET_REGISTRY.get(dataset_id)
    if entry:
        if entry.status in ("NOT_DIRECTLY_READABLE", "LOCKED_UNREGISTERED_FOR_READ") or entry.canonical_relative_path is None or entry.physical_sha256 is None:
            if entry.role in (DatasetRole.LOCKED_HOLDOUT, DatasetRole.LOCKED_PROSPECTIVE_PRISTINE) or entry.status == "LOCKED_UNREGISTERED_FOR_READ":
                raise HoldoutAccessDeniedError(
                    f"HOLDOUT_FIREWALL_VIOLATION: Dataset '{dataset_id}' is locked holdout/pristine and cannot be loaded directly."
                )
            if entry.role == DatasetRole.PROSPECTIVE_FORWARD or entry.status == "PROSPECTIVE_UNMATERIALIZED":
                raise HoldoutAccessDeniedError(
                    f"PROSPECTIVE_DATASET_NOT_REGISTERED: Prospective forward dataset '{dataset_id}' is not materialized for physical read."
                )
            raise HoldoutAccessDeniedError(
                f"DATASET_NOT_REGISTERED_FOR_PHYSICAL_READ: Dataset '{dataset_id}' is not registered for physical read (status={entry.status})."
            )

    p = Path(file_path)
    ResearchDataAccessGuard.check_access(
        operation=operation,
        dataset_id=dataset_id,
        dataset_role=dataset_role,
        start_ts_ns=start_ts_ns,
        end_ts_ns=end_ts_ns,
        file_path=p,
        dataset_logical_sha=dataset_logical_sha,
    )
    return pq.read_table(p)
