# Passivbot Phase 1B Source Reuse & Adaptation Map
**Milestone:** Phase 1B.0 Foundation, Provenance & Source Freeze  
**Date:** 2026-09-16  
**Source Archive:** `passivbot-master.zip`  
**Archive SHA-256:** `bad79d36587b3812481e343c4a47c76ca3ce6d527e8ba42e88bfdc1a88e6c468`  
**License:** The Unlicense (Public Domain)  

---

## 1. Executive Summary & Reuse Architecture

Passivbot (`passivbot-master.zip`) contains robust production-grade planning and validation machinery for historical Binance archives (`data.binance.vision`). However, its design was built specifically for 1m OHLCV klines and assumes files can be buffered into memory via `BytesIO(raw)`.

In **BTCETH Trading OS Phase 1B**, we selectively adapt its core mathematical and planning concepts while upgrading its I/O architecture to handle streaming trades, aggTrades, and high-volume derivatives data safely and deterministically.

---

## 2. Component Classification Matrix

| Source File | Component / Function / Class | Classification | Primary Purpose | Planned BTCETH OS Adaptation / Upgrade |
|---|---|---|---|---|
| `src/binance_ohlcv_archive.py` | `monthly_archive_eligible()`, `first_monday_after_month()` | **ADAPT** | Monthly archive availability calculation with buffer | Adapt directly. Ensures requests are never dispatched for unfinalized months before Binance's Monday publishing cycle. |
| `src/binance_ohlcv_archive.py` | `daily_archive_eligible()` | **ADAPT** | Daily archive lag eligibility calculation (2-day lag) | Adapt directly. Prevents premature 404 errors on current/recent days. |
| `src/binance_ohlcv_archive.py` | `_month_bounds()`, `_day_bounds()` | **ADAPT** | Exact UTC millisecond/nanosecond boundary calculation | Adapt and generalize to int64 nanosecond precision. |
| `src/binance_ohlcv_archive.py` | `_parse_checksum()` | **ADAPT** | Parse official Binance `.CHECKSUM` sidecar files | Adapt directly. Enforces 64-character lowercase hexadecimal format and filename matching. |
| `src/binance_ohlcv_archive.py` | `BinanceArchiveRequest`, `BinanceArchiveResult` | **ADAPT** | Request/Result data structures | Generalize beyond 1m klines to support `trades`, `aggTrades`, `markPriceKlines`, `indexPriceKlines`, `premiumIndexKlines`. |
| `src/binance_ohlcv_archive.py` | `plan_binance_archive_requests()` | **ADAPT** | Efficient monthly vs daily partition request planning | Generalize from kline masks to arbitrary historical dataset ranges. |
| `src/binance_ohlcv_archive.py` | `BinanceOhlcvArchiveClient._get()` | **DO_NOT_USE** | In-memory `await response.read()` into RAM | **Replace entirely:** Passivbot buffers multi-hundred-megabyte ZIPs in RAM. Replace with streaming download to `*.part`. |
| `src/binance_ohlcv_archive.py` | `_parse_archive_zip()` | **DO_NOT_USE** | In-memory `pd.read_csv()` using float64 | **Replace entirely:** Binary float is forbidden for canonical truth. Replace with streaming CSV reader and exact Arrow Decimal128 parsing. |
| `src/ohlcv_catalog.py` | Catalog & partition indexing | **REFERENCE** | SQLite partition tracking | Inform our SQLite WAL catalog schema (`artifacts/catalog.sqlite`). |
| `docs/plans/hlcvs_downloader_determinism_handoff.md` | Determinism handoff documentation | **REFERENCE** | Deterministic download and test isolation patterns | Consult for edge cases in testing and rate-limiting. |

---

## 3. Mandatory Engineering Upgrades for BTCETH OS

Our adapted implementation in Wave 1B.2 must enforce the following strict upgrades over Passivbot:

### 1. Streaming I/O with Zero RAM Buffering
- **Passivbot Flaw:** Loads the entire archive response into a memory buffer (`raw = await response.read()`) and creates an in-memory `BytesIO` ZIP object. For large monthly trade archives (which can exceed 1 GB uncompressed), this causes memory pressure and crashes.
- **BTCETH OS Requirement:**
  ```text
  HTTP GET Stream
    │
    ▼
  Write chunks to disk: filename.zip.part
    │
    ├── Simultaneously feed chunks to hashlib.sha256()
    │
  On stream completion:
    ├── Flush & fsync file descriptor
    ├── Compare computed SHA-256 with parsed .CHECKSUM digest
    ├── Perform quick zipfile.ZipFile(filename.zip.part).testzip() validation
    └── Atomic rename: os.replace(filename.zip.part, filename.zip)
  ```

### 2. Incomplete State Isolation
- **Rule:** Never write directly to the canonical `.zip` path.
- **Rule:** Any download abort, cancellation, timeout, or hash mismatch must leave only `.part` files on disk (or unlink them), ensuring no corrupted files are ever indexed into the RAW store.

### 3. Generalization Beyond 1m Klines
- **Passivbot Limitation:** Hardcoded URL builder: `{BASE}/{kind}/klines/{symbol}/1m/{filename}`.
- **BTCETH OS Requirement:** Support all official Binance archive patterns across both Spot and USD-M Perpetuals:
  - Spot Trades: `data/spot/{monthly|daily}/trades/{symbol}/{symbol}-trades-{period}.zip`
  - Spot AggTrades: `data/spot/{monthly|daily}/aggTrades/{symbol}/{symbol}-aggTrades-{period}.zip`
  - Spot 1m Klines: `data/spot/{monthly|daily}/klines/{symbol}/1m/{symbol}-1m-{period}.zip`
  - USD-M Trades: `data/futures/um/{monthly|daily}/trades/{symbol}/{symbol}-trades-{period}.zip`
  - USD-M AggTrades: `data/futures/um/{monthly|daily}/aggTrades/{symbol}/{symbol}-aggTrades-{period}.zip`
  - USD-M 1m Klines: `data/futures/um/{monthly|daily}/klines/{symbol}/1m/{symbol}-1m-{period}.zip`
  - USD-M Mark/Index/Premium Klines: `data/futures/um/{monthly|daily}/{dataset}/{symbol}/1m/...`

### 4. Prohibition of Binary Float
- **Passivbot Flaw:** Uses `frame = pd.read_csv(...)` with `np.float64` for OHLCV prices and volumes.
- **BTCETH OS Requirement:** Values in Silver Parquet must be stored as **Arrow Decimal128** or string representations without floating-point rounding.

---

## 4. Attribution Record for Adapted Modules

When adapting code into `src/btceth_os/sources/binance/`, every module must begin with an explicit attribution header:

```python
# Adapted from Passivbot (https://github.com/enarjord/passivbot)
# Original file: src/binance_ohlcv_archive.py
# Archive: passivbot-master.zip (SHA256: bad79d36587b3812481e343c4a47c76ca3ce6d527e8ba42e88bfdc1a88e6c468)
# License: The Unlicense (Public Domain)
# Modifications: Upgraded to streaming .part download with incremental SHA-256,
# generalized dataset path planning, and exact nanosecond/decimal typing.
```
