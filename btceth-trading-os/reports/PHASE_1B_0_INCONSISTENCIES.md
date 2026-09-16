# Phase 1B.0 Inconsistencies & Provenance Audit Log
**Milestone:** Phase 1B.0 Foundation, Provenance & Source Freeze  
**Date:** 2026-09-16  
**Status:** RECORDED & AUDITED  

This document logs any discovered discrepancies, license observations, and technical divergences between earlier project documentation/intake and the authoritative files in the repository and local archives.

---

## 1. Open-Source Archive License & Size Verification

A direct byte-level inspection of the 8 archives located in `/Users/ravi/Downloads/` was conducted.

| Project | Expected License | Verified In-Archive License | Primary License File | Discrepancy / Notes |
|---|---|---|---|---|
| **Passivbot** | Public Domain (Unlicense) | The Unlicense (Public Domain) | `passivbot-master/LICENSE` | **None.** File begins: *"This is free and unencumbered software released into the public domain."* |
| **Jesse** | MIT License | MIT License | `jesse-master/LICENSE` | **None.** Full standard MIT text verified. |
| **NautilusTrader** | LGPL v3 | GNU Lesser General Public License v3.0 | `nautilus_trader-develop/LICENSE` | **None.** Root license is LGPLv3. Sub-crates contain third-party notices (e.g. Apache-2.0, MIT) which are standard and cleanly isolated. |
| **Hummingbot** | Apache License 2.0 | Apache License 2.0 | `hummingbot-master/LICENSE` | **None.** Full standard Apache 2.0 text verified. |
| **Freqtrade** | GPL v3 | GNU General Public License v3.0 | `freqtrade-develop/LICENSE` | **None.** Strict GPL v3 boundary reaffirmed: no core code copying. |
| **OctoBot** | GPL v3 | GNU General Public License v3.0 | `OctoBot-master/LICENSE` | **None.** Strict GPL v3 boundary reaffirmed: reference only. |
| **CCXT** | MIT License | MIT License | `ccxt-master/LICENSE.txt` | **Minor file resolution:** An automated search initially matched `.agents/skills/binance/LICENSE.md`; authoritative root license is `ccxt-master/LICENSE.txt` (MIT). |
| **LEAN** | Apache License 2.0 | Apache License 2.0 | `Lean-master/LICENSE` | **None.** Full standard Apache 2.0 text verified. |

---

## 2. Archive File Size Precision Audit

In the initial intake summary, approximate sizes were reported using fractional megabytes. The authoritative byte counts have now been pinned:

| Project | Approximate Size Reported | Exact Authoritative Bytes | SHA-256 Digest |
|---|---:|---:|---|
| Passivbot | 5.3 MB | 5,579,317 bytes | `bad79d36587b3812481e343c4a47c76ca3ce6d527e8ba42e88bfdc1a88e6c468` |
| Jesse | 35.7 MB | 37,409,997 bytes | `de72c7803b0f26efd2d0a555285e9e33040de1b72b0cda001665640f566008c0` |
| NautilusTrader | 28.5 MB | 29,896,277 bytes | `7df7feb2c7b8f861b699d317fa4e997b56370ea505c6b40a20219e69eba7e6d3` |
| Hummingbot | 3.7 MB | 3,863,184 bytes | `660c4f5cc2f5f9aa6fb5232b002998f566039cef9568884b9c114b95dd5cb334` |
| Freqtrade | 43.1 MB | 45,180,575 bytes | `196c5ed0651e83db3caa59acf4e5ed63c7c769b761e496d98aa417e59c470e8f` |
| OctoBot | 28.0 MB | 29,364,639 bytes | `a1584b1c78c6f1305c0fbcb7c0be38175fa76b8abad7f0014f5e2bd515dfc5fa` |
| CCXT | 90.7 MB | 95,069,979 bytes | `7f3e419437b6a1632b8cb654102a44e855853f226148b6ed7dfcbcdd61372638` |
| LEAN | 216.4 MB | 226,932,273 bytes | `368754edc40c8bc89589810b1806f817e4245ea2de492b0c6a4d25bb532d1d2b` |

---

## 3. Phase 1A Code Inconsistencies Resolved at Baseline

1. **Binance USD-M WebSocket Stream Routing:**
   - *Observation:* The initial draft routed all USD-M perpetual streams to `BINANCE_USDM_PUBLIC_WS` (`wss://fstream.binance.com/public/ws`). This caused silent `NO_EVENT` timeouts for `@aggTrade` and `@forceOrder`.
   - *Authoritative Finding:* Binance's April 2026 WebSocket architecture routes high-frequency feeds (`@bookTicker`, `@depth@100ms`) through `/public/ws` and regular public market feeds (`@aggTrade`, `@forceOrder`, `@kline`, `@ticker`) through `BINANCE_USDM_MARKET_WS` (`wss://fstream.binance.com/market/ws`).
   - *Status:* Resolved and committed at `e945ed9`.
2. **WebSocket Timeout Margin for WAN Latency:**
   - *Observation:* A hard 2.0s timeout caused intermittent failure on Spot `@aggTrade` when connecting from India due to TLS handshake overhead and inter-trade arrival gaps.
   - *Authoritative Finding:* Increasing timeout to 6.0s for non-sparse feeds (with immediate loop break upon receiving the first message) provides deterministic reliability without slowing down execution.
   - *Status:* Resolved and committed at `1f12435`.
3. **Module Layout Preservation:**
   - *Observation:* P0 blueprint proposed a deeply nested folder structure (`contracts/`, `schemas/`, `sources/binance/`, etc.), whereas the actual Phase 1A codebase is flat in `src/btceth_os/`.
   - *Authoritative Decision:* In accordance with Phase 1B.0 instructions, existing Phase 1A files (`core.py`, `storage.py`, `catalog.py`, `collectors.py`, `orderbook.py`, `live_orderbook.py`, `live_smoke.py`, `security_scan.py`) will **NOT** be moved or refactored during Phase 1B.0. Modular namespaces will be added only for new Phase 1B components.

---

## 4. Phase 1B.0 Dataset Registry & Timestamp Policy Remediations

1. **Spot Historical Timestamp Policy (2025 Microsecond Switch):**
   - *Observation:* Initial registry draft universally assigned `expected_time_unit: "ms"` to all Spot datasets.
   - *Authoritative Finding:* Official Binance public-data documentation establishes that Binance Spot transitioned from millisecond (`ms`) to microsecond (`us`) timestamps on January 1, 2025 (`1735689600000000` us). Assuming fixed milliseconds causes catastrophic timestamp overflow (e.g. `1735689600010866` interpreted as ms evaluates to the year 56976).
   - *Status:* Remediated. Replaced fixed `"ms"` with a date-versioned policy (`before: 2025-01-01 -> ms`, `from: 2025-01-01 -> us`), implemented `resolve_spot_timestamp()` in `contracts.py`, and verified that canonical internal time normalizes to int64 nanoseconds while preserving `source_ts_raw`, `source_ts_unit`, and `source_precision`.
2. **Independence of USD-M Futures Timestamp Policy:**
   - *Observation:* Spot's 2025 microsecond change must not be assumed for USD-M Perpetuals without official verification.
   - *Status:* Kept USD-M timestamp policy completely independent (`type: "unverified"`, `unit: "ms"`) until proven in Wave 1B.1.
3. **Binance Futures Premium Dataset Official Naming:**
   - *Observation:* Early project notes referred to the perpetual premium index candle feed as `premiumIndexKlines`.
   - *Authoritative Finding:* Current official Binance public-data documentation and download tooling name the downloadable futures archive family `premiumPriceKlines`.
   - *Status:* Remediated in `config/historical_datasets.yaml` (`source_dataset_name: "premiumPriceKlines"`). Archive support status remains `UNVERIFIED_SOURCE_PATH` pending Wave 1B.1 discovery.
4. **Pre-Certified Archive Support Flags Replaced with UNVERIFIED:**
   - *Observation:* The initial registry draft prematurely asserted `daily_support: true`, `monthly_support: true`, `checksum_support: true` on datasets whose paths were marked `UNVERIFIED_SOURCE_PATH`.
   - *Status:* Remediated. Replaced premature booleans with explicit `"UNVERIFIED"` state across all unverified datasets.
5. **USD-M Funding History Status:**
   - *Observation:* Funding history was initially described as a downloadable `csv.zip` archive with daily/monthly support.
   - *Authoritative Finding:* Authoritative historical funding truth may be published via public archive, REST history API, or a hybrid.
   - *Status:* Remediated. Marked format and capabilities as `"UNVERIFIED"` until Wave 1B.1 proves the authoritative source interface.

