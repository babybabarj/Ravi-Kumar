# ANTIGRAVITY PROJECT INTAKE REPORT
**Project:** BTCETH Trading OS  
**Author:** Antigravity (Pair Programmer)  
**Date:** 2026-09-16  
**Milestone:** Phase 1A Closure & Phase 1B Intake  
**Working Clone:** `/Users/ravi/btceth-phase1a-mac`  
**Root Package:** `btceth-trading-os`  

---

## 1. Project Purpose

**BTCETH Trading OS** is a private personal quantitative trading and research system designed specifically for BTC and ETH.

### Core Character:
- It is **NOT** a commercial SaaS, signal-selling service, public trading bot, exchange, or copy-trading platform.
- The fundamental objective is **positive expectancy** after accounting for all real-world transaction frictions:
  - Exchange trading fees (taker/maker)
  - Derivatives funding rates
  - Slippage and market impact
  - WAN and order-processing latency
  - Partial fills and adverse selection
  - Execution errors and desynchronizations
- Risk must be rigorously controlled across:
  - Drawdown limits (daily, weekly, total)
  - Maximum leverage restrictions
  - Correlated portfolio exposure between BTC and ETH
  - Left-tail market risks and liquidation cascades
  - Operational and connectivity risks
  - Strategy alpha degradation over time
- **Statistical Horizon:** After 100, 500, and 1,000 live trades, cumulative net realized profits must exceed total losses + fees + funding + slippage while drawdowns stay strictly within predefined bounds.
- **Decision Philosophy:** Research -> Validation -> Risk -> Execution. There is no direct "chart -> AI opinion -> trade" shortcut. "NO TRADE" is a standard and fully valid output.

---

## 2. Current Architecture

The system operates around three conceptually independent brains:
1. **Market Brain:** Interprets what is happening in the market (trend, momentum, volatility, order flow, liquidity, derivatives positioning, basis, funding, options IV, regimes, event risk).
2. **Strategy Brain:** Evaluates whether there is a statistically validated, non-spurious opportunity.
3. **Risk Brain:** Independent gatekeeper deciding whether capital should be risked given current exposure, correlations, volatility, stop distance, drawdowns, and degradation limits.

### Frozen Processing Pipeline:
```text
BTC & ETH Market (Binance & Deribit)
  │
  ▼
Market Data OS (Passivbot ideas + Binance official + CCXT)
  │
  ▼
RAW Immutable Evidence (gzip JSONL)
  │
  ▼
SILVER Canonical Dataset (Parquet / Decimal)
  │
  ▼
Jesse Lab (Hypothesis & Research Iteration)
  │
  ▼
Validation Engine (Freqtrade challenger + Stat tests)
  │
  ▼
Strategy Registry (Validated Strategies)
  │
  ▼
Market Brain
  │
  ▼
Portfolio Governor (LEAN concepts)
  │
  ▼
Risk Governor
  │
  ▼
Instrument Selector (Spot / USD-M Perp / No Trade)
  │
  ▼
Nautilus Core (Event-Driven Simulation & Execution)
  │
  ▼
Order Manager (Native Binance API primary + CCXT secondary)
  │
  ▼
Binance Exchange
  │
  ▼
Order Truth Engine & Internal Ledger
  │
  ▼
Live Position Tracking
  │
  ▼
Exit / Stop / TP Execution
  │
  ▼
Real P&L & Performance Engine
  │
  ▼
Research Feedback Loop
```

### Storage Tiers:
- **RAW:** Exact, immutable, append-only upstream payloads (`.jsonl.gz`) preserving raw unknown fields and source timestamps.
- **BRONZE:** Parsed source-oriented structures without lossy transformations.
- **SILVER:** Canonical observed facts in Parquet format using exact numeric representations (Arrow Decimal128, Python Decimal, exact string) with canonical three-clock timestamps.
- **GOLD:** Deterministically derived, reproducible research features (CVD, OFI, realized volatility, funding context, regimes).

---

## 3. Frozen Decisions

The following architectural and operational rules are frozen:
1. **Strictly Narrow Universe:** BTC and ETH only. No altcoins, no arbitrary leverage.
2. **Initial Venues:**
   - **Binance:**
     - `BINANCE:SPOT:BTCUSDT`
     - `BINANCE:SPOT:ETHUSDT`
     - `BINANCE:USD_M_PERP:BTCUSDT`
     - `BINANCE:USD_M_PERP:ETHUSDT`
   - **Deribit:** BTC and ETH options market state (DATA ONLY; live options trading is out of scope).
3. **Timestamp Invariant:**
   - Three required clocks on every record: `ts_event_ns`, `ts_recv_ns`, `ts_ingest_ns`.
   - Preserve original source timestamps (`source_ts_raw`, `source_ts_unit`, `source_precision`). Never manufacture artificial precision.
   - Strict point-in-time rule: available_ts <= decision_ts.
4. **Financial Precision:** Binary float is forbidden as a canonical source of truth for prices, quantities, balances, and cash flows. Exact decimal/fixed-point representations must be used.
5. **Data Integrity:** Never silently interpolate, synthesize, or overwrite missing data. Missing means missing. Conflicting records must be explicitly classified (`DUPLICATE_IDENTICAL`, `SOURCE_CONFLICT`, `SEQUENCE_GAP`, `QUARANTINED`).
6. **Dual Identity:** Every dataset has a `physical_sha256` (exact file bytes) and a `logical_sha256` (canonical schema/content identity).
7. **Zero Trading in Phase 1:** All execution modules and trading credentials remain disabled. Phase 1 is read-only.

---

## 4. Current Phase

- **Phase 0 (Foundation / Integration Blueprint):** `CLOSED_PASS`
- **Phase 1A (Perishable Live Market Data):** `VERIFIED` (Closed authoritatively on this Mac in India).
- **Phase 1B (Historical Canonical Data):** **ACTIVE CURRENT MILESTONE**.
  - Target: `CANONICAL_DATA_V1.1 = VERIFIED`.

---

## 5. Phase 1A Verification Evidence

Authoritative verification was conducted directly on this Mac, fulfilling all strict acceptance criteria:

| Acceptance Criterion | Result | Evidence File / Location |
|---|---|---|
| Automated + failure simulation tests | **PASS (27/27, 100%)** | `reports/TEST_RESULTS.txt` |
| Zero-trading security scan | **PASS (Capability = ZERO)** | `reports/SECURITY_SCAN.md` |
| All REST collectors observed | **PASS (20/20 observed)** | `reports/COLLECTOR_HEALTH.md` |
| Required WebSocket streams observed | **PASS (12/12 received)** | `reports/PHASE_1A_ACCEPTANCE.json` |
| Liquidation streams reachable | **PASS (2/2 connected)** | `reports/PHASE_1A_ACCEPTANCE.md` |
| Order books synchronized | **PASS (4/4 synced)** | Spot BTC/ETH & USD-M BTC/ETH order books verified |
| Source errors / conflicts | **0 errors, 0 conflicts** | Full clean live capture recorded |
| Raw append-only evidence | **28 gzip files created** | `artifacts/phase1a/raw/` |
| Silver Parquet readback | **32 rows verified** | `artifacts/phase1a/silver/live_smoke.parquet` |
| SQLite WAL catalog | **34 heartbeats, WAL mode** | `artifacts/phase1a/catalog.sqlite` |
| Acceptance summary report | **`PHASE_1A = VERIFIED`** | `reports/PHASE_1A_ACCEPTANCE.md` |

Reference archive for Phase 1A evidence:
- Path: `/Users/ravi/btceth-phase1a-mac.zip` (79 MB, verified present).

---

## 6. Existing Repository State

- **Clone Location:** `/Users/ravi/btceth-phase1a-mac`
- **Git Remote:** `origin https://github.com/babybabarj/Ravi-Kumar.git`
- **Active Branch:** `btceth-phase1a`
- **HEAD Commit:** `1f1243581d0a4d1882d4acd2cc4d49f967265ee6`
- **Commit History (Last 5 commits):**
  - `1f12435`: phase1a: commit verified resilient live smoke timeout
  - `e945ed9`: phase1a: commit verified USD-M market stream routing
  - `3d87a08`: phase1a: replace aggregate WebSocket threshold with per-stream acceptance
  - `fe32eee`: phase1a: validate WebSocket capabilities per stream instead of aggregate count
  - `9f8a34e`: phase1a: regress USD-M pu continuity semantics
- **Working Tree:** Completely clean on tracked files; local HEAD matches `origin/btceth-phase1a`. Untracked build artifacts and virtualenv are properly isolated.

---

## 7. Open-Source Archives Discovered

All 8 requested open-source archives were discovered locally in `/Users/ravi/Downloads/`:

| Project | ZIP Path | Size | License | Key Inspected Files |
|---|---|---|---|---|
| **Passivbot** | `/Users/ravi/Downloads/passivbot-master.zip` | 5.3 MB | Public Domain (Unlicense) | `src/binance_ohlcv_archive.py`, `docs/plans/hlcvs_downloader_determinism_handoff.md` |
| **Jesse** | `/Users/ravi/Downloads/jesse-master.zip` | 35.7 MB | MIT | `jesse/models/Candle.py`, `jesse/modes/import_candles_mode/` |
| **NautilusTrader** | `/Users/ravi/Downloads/nautilus_trader-develop.zip` | 28.5 MB | LGPL v3 | `crates/persistence/src/backend/catalog.rs`, `crates/persistence/bin/to_parquet.rs` |
| **Hummingbot** | `/Users/ravi/Downloads/hummingbot-master.zip` | 3.7 MB | Apache 2.0 | `hummingbot/connector/derivative/binance_perpetual/binance_perpetual_api_order_book_data_source.py` |
| **Freqtrade** | `/Users/ravi/Downloads/freqtrade-develop.zip` | 43.1 MB | GPL v3 | `freqtrade/data/history/datahandlers/parquetdatahandler.py`, `history_utils.py` |
| **OctoBot** | `/Users/ravi/Downloads/OctoBot-master.zip` | 28.0 MB | GPL v3 | `packages/evaluators/octobot_evaluators/evaluators/TA_evaluator.py` |
| **CCXT** | `/Users/ravi/Downloads/ccxt-master.zip` | 90.7 MB | MIT | `python/ccxt/base/precise.py`, `python/ccxt/base/errors.py`, `python/ccxt/async_support/binance.py` |
| **LEAN** | `/Users/ravi/Downloads/Lean-master.zip` | 216.4 MB | Apache 2.0 | `Common/Orders/Fees/BinanceFuturesFeeModel.cs`, `FillModel.cs`, `SlippageModel.cs` |

---

## 8. Reuse & License Matrix

| Framework | Intended Role in BTCETH OS | License | Permitted Reuse Mode | Restrictions & Guardrails |
|---|---|---|---|---|
| **Passivbot** | Archive planning, discovery, checksum parsing, month/day boundaries | Public Domain | Selective adaptation with attribution | Must upgrade in-memory downloads to streaming `.part` + incremental SHA256; generalize beyond 1m klines. |
| **Jesse** | Primary strategy research laboratory | MIT | External dependency / export target | Does NOT own canonical dataset. Canonical Silver/Gold data will be exported to Jesse's schema. |
| **NautilusTrader** | Production event-driven simulation & execution engine | LGPL v3 | External dependency / export target | Arrow/Parquet interoperability target. Must not modify core LGPL code inside proprietary source tree. |
| **Hummingbot** | Specialist order-book synchronization logic | Apache 2.0 | Selective algorithmic adaptation with attribution | Adapt pure algorithms (diff buffering, sequence-gap detection, resync). Do not import entire massive dependency. |
| **Freqtrade** | Independent challenger & validation reference | GPL v3 | External challenger only | **Strict GPL boundary:** Do NOT copy code into internal core engine. Use only as an external CLI/validation runner. |
| **OctoBot** | Architectural & UX reference | GPL v3 | Reference only | **Strict GPL boundary:** Do not copy code. Consult for reference concepts only. |
| **CCXT** | Exchange abstraction, metadata, error types, fallback | MIT | External Python dependency | Use for precision (`Precise`), typed errors, and secondary venue reconciliation. Never sole Binance truth. |
| **LEAN** | Execution and risk model architecture | Apache 2.0 | Architectural reference | Guide separation of FeeModel, FillModel, SlippageModel, BuyingPowerModel, and Strategy Report Card metrics. |

---

## 9. Current Technical Debt

1. **Flat Module Layout in `btceth_os`:**
   - Currently, all 8 implementation files reside at the top of `src/btceth_os/` (`core.py`, `storage.py`, `catalog.py`, `collectors.py`, `orderbook.py`, `live_orderbook.py`, `live_smoke.py`, `security_scan.py`).
   - Phase 1B will require clean modular packages (`sources/binance`, `storage`, `quality`, `canonical`, `catalog`, `identity`) without introducing bloated empty directories.
2. **Missing `THIRD_PARTY_NOTICES.md`:**
   - Must be initialized in repository root before adding any adapted code from Passivbot or Hummingbot.
3. **In-Memory Buffer in Smoke Test:**
   - `live_smoke.py` wrote in-memory rows to Parquet at the end of execution. Historical backfill must stream partitioned Parquet datasets directly to disk.
4. **Historical Archive Downloader Not Yet Built:**
   - Phase 1A implemented public live REST and WebSockets. The official Binance Vision archive client (`data.binance.vision`) is not yet implemented.

---

## 10. Phase 1B Objective

**Phase 1B Milestone:** `CANONICAL_DATA_V1.1 = VERIFIED`

### Deliverables:
- Official Binance Vision historical archive downloader for Spot and USD-M.
- Streaming `.part` download with on-the-fly incremental SHA256 checksum verification and atomic rename.
- Complete RAW preservation (immutable ZIP and raw CSV/data objects).
- Strict Bronze parsing and Silver Parquet normalization (Arrow Decimal128, nanosecond clocks).
- Dual hashing (`physical_sha256` and `logical_sha256`) and dataset manifests.
- Automated quality validation (continuity checks, timestamp alignment, price sanity, duplicate/conflict classification).
- SQLite WAL catalog indexing all historical partitions.
- Full reproducibility verification on clean rebuilds.

---

## 11. Phase 1B Dependencies

- **Python Runtime:** Python 3.12+ (existing `.venv-phase1a`)
- **Core Libraries:** `aiohttp`, `pyarrow`, `websockets`, `pytest`, `sqlite3`
- **Optional Analysis Utilities:** `duckdb` (for zero-copy analytical verification), `ccxt` (for precision metadata)
- **Forbidden Technologies:** Kafka, ClickHouse, PostgreSQL clusters, Spark, microservice frameworks. Keep the stack auditable, deterministic, and local.

---

## 12. Risks & Mitigations

1. **Binance Vision Rate Limits / Bandwidth Throttling:**
   - *Mitigation:* Implement bounded concurrency (`asyncio.Semaphore(4)`), exponential backoff with jitter, and resume capability using `.part` files.
2. **File Corruption / Incomplete Downloads over WAN:**
   - *Mitigation:* Never stream directly to the target filename. Download to `filename.part`, compute SHA256 incrementally, compare against the official `.CHECKSUM` file, and perform an atomic `os.replace`.
3. **Historical Schema Drift in Binance Archives:**
   - *Mitigation:* Historical files from 2019–2021 occasionally have missing headers or alternate column counts. Implement strict schema detection and validate row lengths against explicit expected variants.
4. **Perishable Positioning Data Gap:**
   - *Mitigation:* Historical open interest and taker volumes have limited retention on REST and are only partially published in archives. Clearly document historical coverage boundaries in catalog manifests.
5. **Trade Timestamp Collisions:**
   - *Mitigation:* Multiple trades legitimately occur within the same millisecond. Deduplication must be keyed on exchange trade ID (`aggTradeId` / `tradeId`), never on timestamp alone.

---

## 13. Proposed Phase 1B Implementation Waves

```text
Wave 1B.0: Third-Party Notices & Architecture Setup
  - Initialize THIRD_PARTY_NOTICES.md
  - Establish modular structure (sources/binance, storage, quality, canonical)

Wave 1B.1: Binance Archive Discovery & Planner
  - Adapt Passivbot month/day planning for Spot and USD-M
  - Support trades, aggTrades, 1m klines, mark-price klines, index-price klines, premium-index klines

Wave 1B.2: Streaming Downloader & Integrity Engine
  - Streaming aiohttp to *.part + incremental SHA256
  - Checksum sidecar parsing and atomic rename
  - Graceful 404 and rate-limit handling

Wave 1B.3: RAW Object Storage & Cataloging
  - Immutable raw archive storage under artifacts/historical/raw/
  - Indexing physical files, sizes, and physical_sha256 in SQLite WAL catalog

Wave 1B.4: Streaming ZIP Parser & Bronze Layer
  - Memory-bounded streaming decompression
  - Strict CSV parsing without float conversion

Wave 1B.5: Silver Canonical Parquet Normalization
  - PyArrow Decimal128 schema definitions
  - Nanosecond timestamp assignment with source unit metadata
  - Monthly/daily partitioned Parquet dataset generation

Wave 1B.6: Quality & Integrity Engine
  - Monotonicity and continuity checks
  - Trade ID gap detection and conflict classification
  - Anomaly registry logging

Wave 1B.7: Historical BTC Spot Backfill
  - Execute bounded canonical backfill for BINANCE:SPOT:BTCUSDT

Wave 1B.8: Historical ETH Spot Backfill
  - Execute bounded canonical backfill for BINANCE:SPOT:ETHUSDT

Wave 1B.9: Historical BTC USD-M Perp Backfill
  - Execute bounded canonical backfill for BINANCE:USD_M_PERP:BTCUSDT

Wave 1B.10: Historical ETH USD-M Perp Backfill
  - Execute bounded canonical backfill for BINANCE:USD_M_PERP:ETHUSDT

Wave 1B.11: Manifests, Logical Hashing & Cross-Dataset Reconciliation
  - Calculate dataset logical_sha256
  - Generate canonical manifests and export compatibility checks (Jesse / Nautilus)

Wave 1B.12: Reproducibility Suite & Phase 1B Acceptance
  - End-to-end acceptance script: tools/mac_phase1b_verify.sh
  - Verification reports and gate sign-off: CANONICAL_DATA_V1.1 = VERIFIED
```

---

## 14. Inconsistencies Discovered & Documented

1. **Binance USD-M WebSocket Routing in Phase 1A:**
   - *Inconsistency:* The earlier implementation routed USD-M `aggtrade` and `forceOrder` to `BINANCE_USDM_PUBLIC_WS` (`/public/ws`), which resulted in `NO_EVENT` timeouts because Binance exclusively pushes regular market data (`aggTrade`, `forceOrder`, `kline`, `ticker`) over `BINANCE_USDM_MARKET_WS` (`/market/ws`).
   - *Resolution:* Fixed and authoritatively committed to remote `btceth-phase1a` at commit `e945ed9`.
2. **WebSocket Timeout Sensitivity on WAN:**
   - *Inconsistency:* The initial 2.0-second acceptance timeout in `live_smoke.py` caused intermittent false-negative `NO_EVENT` reports on Spot `aggTrade` due to WAN TLS handshake latency and inter-trade arrival intervals from India.
   - *Resolution:* Adjusted to 6.0 seconds for non-sparse feeds, allowing immediate break on first arrival while eliminating flaky timeouts. Committed at `1f12435`.
3. **Repository Directory Layout vs P0 Proposal:**
   - *Inconsistency:* The P0 blueprint proposed a deep folder tree (`contracts/`, `schemas/`, `sources/binance/`, etc.). The actual Phase 1A repository intentionally used a compact, direct module structure inside `src/btceth_os/`.
   - *Resolution:* This was a pragmatic and sound engineering choice for Phase 1A. As Phase 1B begins, we will modularize cleanly without creating empty dummy directories.
