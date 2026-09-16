# Binance Official Archive Discovery Report (Phase 1B.1)

**Generated at (UTC):** `2026-09-16T20:12:41.719065+00:00`  
**Total Probes Executed:** `82`  
**Total Downloaded Data:** `205654` bytes (200.83 KB) (Budget limit: 50 MB)  

## 1. Executive Summary

All 20 canonical datasets in the BTCETH Trading OS scope were resolved with direct bounded probes against `https://data.binance.vision`. Key empirical findings:

1. **Premium Index Archive Path:** The official path on Binance Vision is `premiumIndexKlines` (HTTP 200). `premiumPriceKlines` returns HTTP 404.
2. **Funding Rate Archive Model:** Binance publishes historical funding rate archives exclusively on **monthly** cadence (`data/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{period}.zip`). Daily funding rate archives do not exist (HTTP 404). Real-time / recent funding rates are served by REST `GET /fapi/v1/fundingRate`.
3. **Spot 2025 Microsecond Switch:** Empirical proof confirms Spot timestamps transitioned from milliseconds (13 digits) to microseconds (16 digits) on `2025-01-01 00:00:00 UTC`.
4. **USD-M Millisecond Policy:** Empirical proof confirms USD-M Perpetual timestamps remain in milliseconds (13 digits) across 2024, 2025, and 2026. The 2025 Spot microsecond change does NOT apply to Futures.
5. **CHECKSUM Sidecars:** All 20 datasets support sidecar `.CHECKSUM` files containing a standard 64-character lowercase hexadecimal SHA-256 digest and referenced filename.

## 2. Canonical Datasets Discovery Matrix

| Dataset ID | Market | Source Name | Daily Support | Monthly Support | CHECKSUM Support | Timestamp Policy | Earliest Observed |
|---|---|---|---|---|---|---|---|
| `BINANCE:SPOT:BTCUSDT:TRADES` | SPOT | `trades` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `date_versioned` | `2017-08` |
| `BINANCE:SPOT:BTCUSDT:AGG_TRADES` | SPOT | `aggTrades` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `date_versioned` | `2017-08` |
| `BINANCE:SPOT:BTCUSDT:KLINES_1M` | SPOT | `klines` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `date_versioned` | `2017-08` |
| `BINANCE:SPOT:ETHUSDT:TRADES` | SPOT | `trades` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `date_versioned` | `2017-08` |
| `BINANCE:SPOT:ETHUSDT:AGG_TRADES` | SPOT | `aggTrades` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `date_versioned` | `2017-08` |
| `BINANCE:SPOT:ETHUSDT:KLINES_1M` | SPOT | `klines` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `date_versioned` | `2017-08` |
| `BINANCE:USD_M_PERP:BTCUSDT:TRADES` | USDM | `trades` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2019-09` |
| `BINANCE:USD_M_PERP:BTCUSDT:AGG_TRADES` | USDM | `aggTrades` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2020-01` |
| `BINANCE:USD_M_PERP:BTCUSDT:KLINES_1M` | USDM | `klines` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2020-01` |
| `BINANCE:USD_M_PERP:BTCUSDT:MARK_PRICE_KLINES_1M` | USDM | `markPriceKlines` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2020-01` |
| `BINANCE:USD_M_PERP:BTCUSDT:INDEX_PRICE_KLINES_1M` | USDM | `indexPriceKlines` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2020-01` |
| `BINANCE:USD_M_PERP:BTCUSDT:PREMIUM_PRICE_KLINES_1M` | USDM | `premiumIndexKlines` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2020-01` |
| `BINANCE:USD_M_PERP:BTCUSDT:FUNDING_HISTORY` | USDM | `fundingRate` | VERIFIED_FALSE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2020-01` |
| `BINANCE:USD_M_PERP:ETHUSDT:TRADES` | USDM | `trades` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2019-12` |
| `BINANCE:USD_M_PERP:ETHUSDT:AGG_TRADES` | USDM | `aggTrades` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2020-01` |
| `BINANCE:USD_M_PERP:ETHUSDT:KLINES_1M` | USDM | `klines` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2020-01` |
| `BINANCE:USD_M_PERP:ETHUSDT:MARK_PRICE_KLINES_1M` | USDM | `markPriceKlines` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2020-01` |
| `BINANCE:USD_M_PERP:ETHUSDT:INDEX_PRICE_KLINES_1M` | USDM | `indexPriceKlines` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2020-01` |
| `BINANCE:USD_M_PERP:ETHUSDT:PREMIUM_PRICE_KLINES_1M` | USDM | `premiumIndexKlines` | VERIFIED_TRUE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2020-01` |
| `BINANCE:USD_M_PERP:ETHUSDT:FUNDING_HISTORY` | USDM | `fundingRate` | VERIFIED_FALSE | VERIFIED_TRUE | VERIFIED_TRUE | `fixed_ms` | `2020-01` |

## 3. Spot Timestamp Verification Evidence

- **Pre-2025 (`2024-12-31`):** Raw TS `1735603200000` (13 digits) -> Unit: `ms`
- **Post-2025 (`2025-01-01`):** Raw TS `1735689600000000` (16 digits) -> Unit: `us`
- **Status:** `VERIFIED_TRUE`

## 4. USD-M Timestamp Verification Evidence

- **USD-M Kline 2025-01-01:** Raw TS `1735689600000` (13 digits) -> Unit: `ms`
- **USD-M Funding 2024-11:** Raw TS `1730419200000` (13 digits) -> Unit: `ms`
- **Status:** `VERIFIED_TRUE`

