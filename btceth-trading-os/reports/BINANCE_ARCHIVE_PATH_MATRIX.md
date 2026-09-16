# Binance Historical Archive Path Matrix (Canonical 20 Datasets)

This document establishes the verified path templates and publication schedules for all 20 canonical datasets in the BTCETH Trading OS.

## Path Templates & Conventions

- **Archive Root:** `https://data.binance.vision`
- **Spot Directory:** `data/spot/{monthly|daily}/{dataset}/{symbol}/[interval/]`
- **USD-M Directory:** `data/futures/um/{monthly|daily}/{dataset}/{symbol}/[interval/]`
- **Checksum Sidecar:** `{archive_url}.CHECKSUM`

## Complete Dataset Resolution Matrix

### BINANCE:SPOT:BTCUSDT:TRADES
- **Market:** `spot`
- **Symbol:** `BTCUSDT`
- **Source Dataset Name:** `trades`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/spot/daily/trades/BTCUSDT/BTCUSDT-trades-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/spot/monthly/trades/BTCUSDT/BTCUSDT-trades-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `7184d33d184a7dfa...`)
- **Timestamp Policy:** `date_versioned`
- **Historical Range:** `2017-08` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Microsecond timestamps from 2025-01-01
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:SPOT:BTCUSDT:AGG_TRADES
- **Market:** `spot`
- **Symbol:** `BTCUSDT`
- **Source Dataset Name:** `aggTrades`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/spot/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `548cb1ae70d1a51f...`)
- **Timestamp Policy:** `date_versioned`
- **Historical Range:** `2017-08` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Microsecond timestamps from 2025-01-01
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:SPOT:BTCUSDT:KLINES_1M
- **Market:** `spot`
- **Symbol:** `BTCUSDT`
- **Source Dataset Name:** `klines`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `c30a63bd0e8a77f2...`)
- **Timestamp Policy:** `date_versioned`
- **Historical Range:** `2017-08` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Microsecond timestamps from 2025-01-01
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:SPOT:ETHUSDT:TRADES
- **Market:** `spot`
- **Symbol:** `ETHUSDT`
- **Source Dataset Name:** `trades`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/spot/daily/trades/ETHUSDT/ETHUSDT-trades-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/spot/monthly/trades/ETHUSDT/ETHUSDT-trades-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `85b0236a053def65...`)
- **Timestamp Policy:** `date_versioned`
- **Historical Range:** `2017-08` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Microsecond timestamps from 2025-01-01
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:SPOT:ETHUSDT:AGG_TRADES
- **Market:** `spot`
- **Symbol:** `ETHUSDT`
- **Source Dataset Name:** `aggTrades`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/spot/daily/aggTrades/ETHUSDT/ETHUSDT-aggTrades-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/spot/monthly/aggTrades/ETHUSDT/ETHUSDT-aggTrades-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `dde4f1777a886d2e...`)
- **Timestamp Policy:** `date_versioned`
- **Historical Range:** `2017-08` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Microsecond timestamps from 2025-01-01
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:SPOT:ETHUSDT:KLINES_1M
- **Market:** `spot`
- **Symbol:** `ETHUSDT`
- **Source Dataset Name:** `klines`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/spot/daily/klines/ETHUSDT/1m/ETHUSDT-1m-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/1m/ETHUSDT-1m-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `2c3e15ae6458707b...`)
- **Timestamp Policy:** `date_versioned`
- **Historical Range:** `2017-08` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Microsecond timestamps from 2025-01-01
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:BTCUSDT:TRADES
- **Market:** `usdm`
- **Symbol:** `BTCUSDT`
- **Source Dataset Name:** `trades`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/trades/BTCUSDT/BTCUSDT-trades-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/trades/BTCUSDT/BTCUSDT-trades-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `7219b2f6a64ea135...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2019-09` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Header row present; milliseconds timestamp
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:BTCUSDT:AGG_TRADES
- **Market:** `usdm`
- **Symbol:** `BTCUSDT`
- **Source Dataset Name:** `aggTrades`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `28a34b83dc97c851...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2020-01` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Header row present; milliseconds timestamp
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:BTCUSDT:KLINES_1M
- **Market:** `usdm`
- **Symbol:** `BTCUSDT`
- **Source Dataset Name:** `klines`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `9c3dad038f4b043e...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2020-01` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Header row present; milliseconds timestamp
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:BTCUSDT:MARK_PRICE_KLINES_1M
- **Market:** `usdm`
- **Symbol:** `BTCUSDT`
- **Source Dataset Name:** `markPriceKlines`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `e7087d29fee56438...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2020-01` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Header row present; milliseconds timestamp
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:BTCUSDT:INDEX_PRICE_KLINES_1M
- **Market:** `usdm`
- **Symbol:** `BTCUSDT`
- **Source Dataset Name:** `indexPriceKlines`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/indexPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/indexPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `1053eb558d282a12...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2020-01` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Header row present; milliseconds timestamp
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:BTCUSDT:PREMIUM_PRICE_KLINES_1M
- **Market:** `usdm`
- **Symbol:** `BTCUSDT`
- **Source Dataset Name:** `premiumIndexKlines`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/premiumIndexKlines/BTCUSDT/1m/BTCUSDT-1m-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/premiumIndexKlines/BTCUSDT/1m/BTCUSDT-1m-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `2a566ddb1b4c9f88...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2020-01` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Header row present; milliseconds timestamp
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:BTCUSDT:FUNDING_HISTORY
- **Market:** `usdm`
- **Symbol:** `BTCUSDT`
- **Source Dataset Name:** `fundingRate`
- **Daily Support:** `VERIFIED_FALSE` (Status: 404)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `e1b19cccfe2cdcba...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2020-01` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `VERIFIED_TRUE`
- **Known Caveats:** Monthly archive only; REST GET /fapi/v1/fundingRate provides recent intervals
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:ETHUSDT:TRADES
- **Market:** `usdm`
- **Symbol:** `ETHUSDT`
- **Source Dataset Name:** `trades`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/trades/ETHUSDT/ETHUSDT-trades-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/trades/ETHUSDT/ETHUSDT-trades-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `ac9599c91e235815...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2019-12` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Header row present; milliseconds timestamp
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:ETHUSDT:AGG_TRADES
- **Market:** `usdm`
- **Symbol:** `ETHUSDT`
- **Source Dataset Name:** `aggTrades`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/aggTrades/ETHUSDT/ETHUSDT-aggTrades-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/aggTrades/ETHUSDT/ETHUSDT-aggTrades-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `924e14e59afc0272...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2020-01` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Header row present; milliseconds timestamp
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:ETHUSDT:KLINES_1M
- **Market:** `usdm`
- **Symbol:** `ETHUSDT`
- **Source Dataset Name:** `klines`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/klines/ETHUSDT/1m/ETHUSDT-1m-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/klines/ETHUSDT/1m/ETHUSDT-1m-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `4170f68dd576e8af...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2020-01` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Header row present; milliseconds timestamp
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:ETHUSDT:MARK_PRICE_KLINES_1M
- **Market:** `usdm`
- **Symbol:** `ETHUSDT`
- **Source Dataset Name:** `markPriceKlines`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/markPriceKlines/ETHUSDT/1m/ETHUSDT-1m-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/markPriceKlines/ETHUSDT/1m/ETHUSDT-1m-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `e60f9df9063cdb54...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2020-01` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Header row present; milliseconds timestamp
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:ETHUSDT:INDEX_PRICE_KLINES_1M
- **Market:** `usdm`
- **Symbol:** `ETHUSDT`
- **Source Dataset Name:** `indexPriceKlines`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/indexPriceKlines/ETHUSDT/1m/ETHUSDT-1m-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/indexPriceKlines/ETHUSDT/1m/ETHUSDT-1m-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `f341153440722d71...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2020-01` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Header row present; milliseconds timestamp
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:ETHUSDT:PREMIUM_PRICE_KLINES_1M
- **Market:** `usdm`
- **Symbol:** `ETHUSDT`
- **Source Dataset Name:** `premiumIndexKlines`
- **Daily Support:** `VERIFIED_TRUE` (Status: 200)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/premiumIndexKlines/ETHUSDT/1m/ETHUSDT-1m-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/premiumIndexKlines/ETHUSDT/1m/ETHUSDT-1m-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `cc76179f8da3848d...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2020-01` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `NOT_APPLICABLE`
- **Known Caveats:** Header row present; milliseconds timestamp
- **Final Classification:** `SUPPORTED_CANONICAL`

### BINANCE:USD_M_PERP:ETHUSDT:FUNDING_HISTORY
- **Market:** `usdm`
- **Symbol:** `ETHUSDT`
- **Source Dataset Name:** `fundingRate`
- **Daily Support:** `VERIFIED_FALSE` (Status: 404)
- **Daily URL Template:** `https://data.binance.vision/data/futures/um/daily/fundingRate/ETHUSDT/ETHUSDT-fundingRate-2024-11-01.zip`
- **Monthly Support:** `VERIFIED_TRUE` (Status: 200)
- **Monthly URL Template:** `https://data.binance.vision/data/futures/um/monthly/fundingRate/ETHUSDT/ETHUSDT-fundingRate-2024-11.zip`
- **CHECKSUM Support:** `VERIFIED_TRUE` (Example: `636a4c7c86445c27...`)
- **Timestamp Policy:** `fixed_ms`
- **Historical Range:** `2020-01` through `2026-08 (monthly) / 2026-09-15 (daily)`
- **REST Fallback:** `VERIFIED_TRUE`
- **Known Caveats:** Monthly archive only; REST GET /fapi/v1/fundingRate provides recent intervals
- **Final Classification:** `SUPPORTED_CANONICAL`

