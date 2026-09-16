from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


DDL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS collector_runs (
  collector_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  source TEXT NOT NULL,
  dataset TEXT NOT NULL,
  instrument TEXT NOT NULL,
  started_at_ns INTEGER NOT NULL,
  ended_at_ns INTEGER,
  status TEXT NOT NULL,
  PRIMARY KEY (collector_id, run_id)
);
CREATE TABLE IF NOT EXISTS collector_heartbeats (
  collector_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  heartbeat_ns INTEGER NOT NULL,
  messages_received INTEGER NOT NULL DEFAULT 0,
  records_written INTEGER NOT NULL DEFAULT 0,
  duplicates_seen INTEGER NOT NULL DEFAULT 0,
  gaps_detected INTEGER NOT NULL DEFAULT 0,
  reconnect_count INTEGER NOT NULL DEFAULT 0,
  parse_errors INTEGER NOT NULL DEFAULT 0,
  source_errors INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS connection_runs (
  connection_id TEXT PRIMARY KEY,
  collector_id TEXT NOT NULL,
  started_at_ns INTEGER NOT NULL,
  ended_at_ns INTEGER,
  close_reason TEXT
);
CREATE TABLE IF NOT EXISTS raw_live_objects (
  object_id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  source TEXT NOT NULL,
  dataset TEXT NOT NULL,
  instrument TEXT NOT NULL,
  created_at_ns INTEGER NOT NULL,
  sha256 TEXT
);
CREATE TABLE IF NOT EXISTS live_gaps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  collector_id TEXT NOT NULL,
  instrument TEXT NOT NULL,
  detected_at_ns INTEGER NOT NULL,
  gap_type TEXT NOT NULL,
  expected_value TEXT,
  observed_value TEXT,
  status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscription_state (
  collector_id TEXT NOT NULL,
  subscription_id TEXT NOT NULL,
  connection_id TEXT,
  status TEXT NOT NULL,
  updated_at_ns INTEGER NOT NULL,
  PRIMARY KEY (collector_id, subscription_id)
);
CREATE TABLE IF NOT EXISTS collector_errors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  collector_id TEXT NOT NULL,
  occurred_at_ns INTEGER NOT NULL,
  error_type TEXT NOT NULL,
  message TEXT NOT NULL
);
"""


class Catalog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(DDL)
        self.db.commit()

    def start_run(self, collector_id: str, run_id: str, source: str, dataset: str, instrument: str, started_at_ns: int) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO collector_runs VALUES (?,?,?,?,?,?,?,?)",
            (collector_id, run_id, source, dataset, instrument, started_at_ns, None, "STARTING"),
        )
        self.db.commit()

    def heartbeat(self, collector_id: str, run_id: str, heartbeat_ns: int, *, status: str = "HEALTHY", **counters: Any) -> None:
        names = ["messages_received", "records_written", "duplicates_seen", "gaps_detected", "reconnect_count", "parse_errors", "source_errors"]
        vals = [int(counters.get(n, 0)) for n in names]
        self.db.execute(
            "INSERT INTO collector_heartbeats VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (collector_id, run_id, heartbeat_ns, *vals, status),
        )
        self.db.execute("UPDATE collector_runs SET status=? WHERE collector_id=? AND run_id=?", (status, collector_id, run_id))
        self.db.commit()

    def gap(self, collector_id: str, instrument: str, detected_at_ns: int, gap_type: str, expected: str, observed: str, status: str = "OPEN") -> None:
        self.db.execute(
            "INSERT INTO live_gaps(collector_id,instrument,detected_at_ns,gap_type,expected_value,observed_value,status) VALUES (?,?,?,?,?,?,?)",
            (collector_id, instrument, detected_at_ns, gap_type, expected, observed, status),
        )
        self.db.commit()

    def error(self, collector_id: str, occurred_at_ns: int, error_type: str, message: str) -> None:
        self.db.execute(
            "INSERT INTO collector_errors(collector_id,occurred_at_ns,error_type,message) VALUES (?,?,?,?)",
            (collector_id, occurred_at_ns, error_type, message),
        )
        self.db.commit()

    def count(self, table: str) -> int:
        allowed = {"collector_runs", "collector_heartbeats", "connection_runs", "raw_live_objects", "live_gaps", "subscription_state", "collector_errors"}
        if table not in allowed:
            raise ValueError(table)
        return int(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def close(self) -> None:
        self.db.close()
