# Open-Source Source Manifest
**Milestone:** Phase 1B.0 Foundation & Source Freeze  
**Date:** 2026-09-16  
**Status:** FROZEN  

This manifest records the authoritative cryptographic fingerprint, license provenance, and architectural boundaries of the 8 local open-source archives discovered in `/Users/ravi/Downloads/`.

## 1. Cryptographic Fingerprint Summary

| Project | Archive Filename | Size (Bytes) | SHA-256 Digest | License | Reuse Mode |
|---|---|---:|---|---|---|
| **Passivbot** | `passivbot-master.zip` | 5,579,317 | `bad79d36587b3812481e343c4a47c76ca3ce6d527e8ba42e88bfdc1a88e6c468` | Public Domain / Unlicense | `ADAPT` |
| **Jesse** | `jesse-master.zip` | 37,409,997 | `de72c7803b0f26efd2d0a555285e9e33040de1b72b0cda001665640f566008c0` | MIT License | `DEPENDENCY` |
| **NautilusTrader** | `nautilus_trader-develop.zip` | 29,896,277 | `7df7feb2c7b8f861b699d317fa4e997b56370ea505c6b40a20219e69eba7e6d3` | LGPL v3.0 | `DEPENDENCY` |
| **Hummingbot** | `hummingbot-master.zip` | 3,863,184 | `660c4f5cc2f5f9aa6fb5232b002998f566039cef9568884b9c114b95dd5cb334` | Apache License 2.0 | `ADAPT` |
| **Freqtrade** | `freqtrade-develop.zip` | 45,180,575 | `196c5ed0651e83db3caa59acf4e5ed63c7c769b761e496d98aa417e59c470e8f` | GPL v3.0 | `REFERENCE` |
| **OctoBot** | `OctoBot-master.zip` | 29,364,639 | `a1584b1c78c6f1305c0fbcb7c0be38175fa76b8abad7f0014f5e2bd515dfc5fa` | GPL v3.0 | `REFERENCE` |
| **CCXT** | `ccxt-master.zip` | 95,069,979 | `7f3e419437b6a1632b8cb654102a44e855853f226148b6ed7dfcbcdd61372638` | MIT License | `DEPENDENCY` |
| **LEAN (QuantConnect)** | `Lean-master.zip` | 226,932,273 | `368754edc40c8bc89589810b1806f817e4245ea2de492b0c6a4d25bb532d1d2b` | Apache License 2.0 | `REFERENCE` |

## 2. Archive Provenance & Boundary Details

### Passivbot
- **Absolute Source Path:** `/Users/ravi/Downloads/passivbot-master.zip`
- **ZIP SHA-256:** `bad79d36587b3812481e343c4a47c76ca3ce6d527e8ba42e88bfdc1a88e6c468`
- **Size:** 5,579,317 bytes
- **Archive Root Directory:** `passivbot-master`
- **License File in Archive:** `passivbot-master/LICENSE` (The Unlicense (Public Domain))
- **BTCETH Intended Role:** Selective adaptation of archive discovery/downloader/validation machinery
- **Reuse Classification:** `ADAPT`
- **GPL / License Boundary:** None
- **Relevant Files Inspected:**
  - `passivbot-master/docs/plans/hlcvs_downloader_determinism_handoff.md`
  - `passivbot-master/docs/plans/ohlcv_v2_architecture_handoff.md`
  - `passivbot-master/scripts/verify_bitget_ohlcv.py`
  - `passivbot-master/src/binance_ohlcv_archive.py`
  - `passivbot-master/src/ohlcv_catalog.py`
  - `passivbot-master/src/ohlcv_download.py`
  - `passivbot-master/src/ohlcv_legacy_import.py`
  - `passivbot-master/src/ohlcv_planner.py`
  - `passivbot-master/src/ohlcv_store.py`
  - `passivbot-master/src/ohlcv_utils.py`

### Jesse
- **Absolute Source Path:** `/Users/ravi/Downloads/jesse-master.zip`
- **ZIP SHA-256:** `de72c7803b0f26efd2d0a555285e9e33040de1b72b0cda001665640f566008c0`
- **Size:** 37,409,997 bytes
- **Archive Root Directory:** `jesse-master`
- **License File in Archive:** `jesse-master/LICENSE` (MIT License)
- **BTCETH Intended Role:** Primary strategy research laboratory and hypothesis testing platform
- **Reuse Classification:** `DEPENDENCY`
- **GPL / License Boundary:** None
- **Relevant Files Inspected:**
  - `jesse-master/jesse/candle_pipelines/base_candles.py`
  - `jesse-master/jesse/models/Candle.py`
  - `jesse-master/jesse/modes/import_candles_mode/`
  - `jesse-master/jesse/modes/import_candles_mode/__init__.py`
  - `jesse-master/jesse/modes/import_candles_mode/drivers/`
  - `jesse-master/jesse/modes/import_candles_mode/drivers/Apex/`
  - `jesse-master/jesse/modes/import_candles_mode/drivers/Apex/ApexOmniPerpetual.py`
  - `jesse-master/jesse/modes/import_candles_mode/drivers/Apex/ApexOmniPerpetualMain.py`
  - `jesse-master/jesse/modes/import_candles_mode/drivers/Apex/ApexOmniPerpetualTestnet.py`
  - `jesse-master/jesse/modes/import_candles_mode/drivers/Apex/__init__.py`

### NautilusTrader
- **Absolute Source Path:** `/Users/ravi/Downloads/nautilus_trader-develop.zip`
- **ZIP SHA-256:** `7df7feb2c7b8f861b699d317fa4e997b56370ea505c6b40a20219e69eba7e6d3`
- **Size:** 29,896,277 bytes
- **Archive Root Directory:** `nautilus_trader-develop`
- **License File in Archive:** `nautilus_trader-develop/LICENSE` (GNU Lesser General Public License v3.0 (LGPL-3.0))
- **BTCETH Intended Role:** Core event-driven simulation, execution engine and Parquet/Arrow target
- **Reuse Classification:** `DEPENDENCY`
- **GPL / License Boundary:** LGPL v3 boundary: dynamic linking/clean Python API; no core code modification
- **Relevant Files Inspected:**
  - `nautilus_trader-develop/crates/adapters/hyperliquid/tests/integration/catalog.rs`
  - `nautilus_trader-develop/crates/event_store/src/replay/catalog.rs`
  - `nautilus_trader-develop/crates/persistence/benches/persistence.rs`
  - `nautilus_trader-develop/crates/persistence/bin/to_parquet.rs`
  - `nautilus_trader-develop/crates/persistence/src/backend/catalog.rs`
  - `nautilus_trader-develop/crates/persistence/src/python/catalog.rs`
  - `nautilus_trader-develop/crates/persistence/tests/integration/test_catalog.rs`
  - `nautilus_trader-develop/python/nautilus_trader/adapters/binance/instruments.py`
  - `nautilus_trader-develop/python/tests/unit/model/test_instruments.py`

### Hummingbot
- **Absolute Source Path:** `/Users/ravi/Downloads/hummingbot-master.zip`
- **ZIP SHA-256:** `660c4f5cc2f5f9aa6fb5232b002998f566039cef9568884b9c114b95dd5cb334`
- **Size:** 3,863,184 bytes
- **Archive Root Directory:** `hummingbot-master`
- **License File in Archive:** `hummingbot-master/LICENSE` (Apache License 2.0)
- **BTCETH Intended Role:** Specialist order-book diff buffering, gap detection, and resync algorithms
- **Reuse Classification:** `ADAPT`
- **GPL / License Boundary:** None
- **Relevant Files Inspected:**
  - `hummingbot-master/hummingbot/connector/derivative/binance_perpetual/binance_perpetual_api_order_book_data_source.py`
  - `hummingbot-master/hummingbot/connector/exchange/binance/binance_order_book.py`
  - `hummingbot-master/test/hummingbot/connector/derivative/binance_perpetual/test_binance_perpetual_api_order_book_data_source.py`
  - `hummingbot-master/test/hummingbot/connector/exchange/binance/test_binance_order_book.py`

### Freqtrade
- **Absolute Source Path:** `/Users/ravi/Downloads/freqtrade-develop.zip`
- **ZIP SHA-256:** `196c5ed0651e83db3caa59acf4e5ed63c7c769b761e496d98aa417e59c470e8f`
- **Size:** 45,180,575 bytes
- **Archive Root Directory:** `freqtrade-develop`
- **License File in Archive:** `freqtrade-develop/LICENSE` (GNU General Public License v3.0 (GPL-3.0))
- **BTCETH Intended Role:** Independent strategy challenger and backtest comparison reference
- **Reuse Classification:** `REFERENCE`
- **GPL / License Boundary:** Strict GPL boundary: Do NOT copy code into internal core; external challenger only
- **Relevant Files Inspected:**
  - `freqtrade-develop/freqtrade/data/dataprovider.py`
  - `freqtrade-develop/freqtrade/data/history/datahandlers/parquetdatahandler.py`
  - `freqtrade-develop/freqtrade/data/history/history_utils.py`
  - `freqtrade-develop/tests/data/test_dataprovider.py`

### OctoBot
- **Absolute Source Path:** `/Users/ravi/Downloads/OctoBot-master.zip`
- **ZIP SHA-256:** `a1584b1c78c6f1305c0fbcb7c0be38175fa76b8abad7f0014f5e2bd515dfc5fa`
- **Size:** 29,364,639 bytes
- **Archive Root Directory:** `OctoBot-master`
- **License File in Archive:** `OctoBot-master/LICENSE` (GNU General Public License v3.0 (GPL-3.0))
- **BTCETH Intended Role:** Architecture and evaluation pipeline reference
- **Reuse Classification:** `REFERENCE`
- **GPL / License Boundary:** Strict GPL boundary: Do NOT copy code into internal core; reference only
- **Relevant Files Inspected:**
  - `OctoBot-master/octobot/producers/evaluator_producer.py`
  - `OctoBot-master/packages/evaluators/octobot_evaluators/evaluators/TA_evaluator.py`
  - `OctoBot-master/packages/tentacles/Evaluator/TA/momentum_evaluator/tests/test_bollinger_bands_momentum_TA_evaluator.py`
  - `OctoBot-master/packages/tentacles/Evaluator/TA/momentum_evaluator/tests/test_klinger_TA_evaluator.py`
  - `OctoBot-master/packages/tentacles/Evaluator/TA/momentum_evaluator/tests/test_macd_TA_evaluator.py`
  - `OctoBot-master/packages/tentacles/Evaluator/TA/momentum_evaluator/tests/test_rsi_TA_evaluator.py`
  - `OctoBot-master/packages/tentacles/Evaluator/TA/trend_evaluator/tests/test_double_moving_averages_TA_evaluator.py`

### CCXT
- **Absolute Source Path:** `/Users/ravi/Downloads/ccxt-master.zip`
- **ZIP SHA-256:** `7f3e419437b6a1632b8cb654102a44e855853f226148b6ed7dfcbcdd61372638`
- **Size:** 95,069,979 bytes
- **Archive Root Directory:** `ccxt-master`
- **License File in Archive:** `ccxt-master/LICENSE.txt` (MIT License)
- **BTCETH Intended Role:** Exchange abstraction, exact precision handling (Precise), typed errors, secondary truth
- **Reuse Classification:** `DEPENDENCY`
- **GPL / License Boundary:** None
- **Relevant Files Inspected:**
  - `ccxt-master/python/ccxt/async_support/binance.py`
  - `ccxt-master/python/ccxt/base/errors.py`
  - `ccxt-master/python/ccxt/base/precise.py`
  - `ccxt-master/python/ccxt/test/base/test_precise.py`

### LEAN (QuantConnect)
- **Absolute Source Path:** `/Users/ravi/Downloads/Lean-master.zip`
- **ZIP SHA-256:** `368754edc40c8bc89589810b1806f817e4245ea2de492b0c6a4d25bb532d1d2b`
- **Size:** 226,932,273 bytes
- **Archive Root Directory:** `Lean-master`
- **License File in Archive:** `Lean-master/LICENSE` (Apache License 2.0)
- **BTCETH Intended Role:** Architectural reference for Fee, Fill, Slippage, BuyingPower models and Report Card
- **Reuse Classification:** `REFERENCE`
- **GPL / License Boundary:** None
- **Relevant Files Inspected:**
  - `Lean-master/Common/Orders/Fees/BinanceFuturesFeeModel.cs`
  - `Lean-master/Common/Orders/Fills/EquityFillModel.cs`
  - `Lean-master/Common/Orders/Fills/FillModel.cs`
  - `Lean-master/Common/Orders/Fills/FutureFillModel.cs`
  - `Lean-master/Common/Orders/Fills/FutureOptionFillModel.cs`
  - `Lean-master/Common/Orders/Fills/IFillModel.cs`
  - `Lean-master/Common/Orders/Fills/ImmediateFillModel.cs`
  - `Lean-master/Common/Orders/Fills/LatestPriceFillModel.cs`
  - `Lean-master/Common/Orders/Slippage/AlphaStreamsSlippageModel.cs`
  - `Lean-master/Common/Orders/Slippage/ConstantSlippageModel.cs`

