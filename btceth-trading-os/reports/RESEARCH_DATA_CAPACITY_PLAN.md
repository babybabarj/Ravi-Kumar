# Research Data Capacity Plan: Historical Scale vs. System Constraints

## 1. System Storage & Resource Baseline
- **Audit Date**: 2026-09-21
- **Operating Environment**: macOS (Darwin arm64)
- **Local Available Disk Space**: **8.4 GiB** (Total volume: 228 GiB, Used: 192 GiB, Available: 8.4 GiB)
- **Network Bandwidth to Binance Vision**: ~1.7 MB/sec sustained throughput

---

## 2. Capacity Analysis: Tick/AggTrade vs. Kline Granularity

| Granularity | Target Period | Total Objects (Monthly Files) | Compressed Archive Size | Expanded In-Memory / Disk | Verdict / Decision |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tick Data (`trades`)** | 2021–2024 (4 years) | 96 archives (BTC+ETH) | ~35–45 GiB | ~180–250 GiB | ❌ **REJECTED**: Exceeds available disk space (8.4 GiB) by $> 400\%$. Would exhaust disk and crash system. |
| **Aggregated Trades (`aggTrades`)** | 2021–2024 (4 years) | 96 archives (BTC+ETH) | ~18–25 GiB | ~90–120 GiB | ❌ **REJECTED**: Exceeds available disk space. |
| **1-Minute Klines (`klines/1m`)** | 2021–2024 (4 years) | 94 archives (BTC+ETH Perp) | ~90–110 MiB | ~220–260 MiB (Parquet) | ✅ **APPROVED**: Highly efficient, exact OHLCV + trade counts, perfectly fits within available disk space (< 3% of available storage). |
| **Spot 1m Klines (`spot/klines/1m`)** | 2021–2024 (4 years) | 94 archives (BTC+ETH Spot) | ~110–130 MiB | ~250–280 MiB (Parquet) | ✅ **APPROVED**: Enables Spot-Perp basis and divergence modeling. |
| **8h Funding History (`fundingRate`)**| 2021–2024 (4 years) | 94 archives (BTC+ETH) | ~0.15 MiB | ~0.40 MiB (Parquet) | ✅ **APPROVED**: Exact historical cash-flow settlement. |
| **Mark / Index / Premium Price** | 2021–2024 (4 years) | 282 archives | ~180 MiB | ~350 MiB (Parquet) | ✅ **SELECTIVE**: Download and compile for basis & premium index analysis. |

---

## 3. Selected Research Universe Strategy

### Research Universe A: `CORE_LONG_HISTORY`
- **Period**: **January 1, 2021 to November 30, 2024** (47 completed months = 1,430 days = ~2,050,000 1-minute bars per symbol).
- **Market Cycles Spanned**:
  1. **2021 Bull Expansion & Blowoff Peak**: BTC \$30k $\rightarrow$ \$69k, extreme positive funding rates, high volatility.
  2. **2022 Macro Bear Market & Structural Deleveraging**: Terra/Luna collapse (May 2022), 3AC liquidation, FTX collapse (Nov 2022), BTC \$69k $\rightarrow$ \$15.5k, extreme negative funding, volatility spikes.
  3. **2023 Low-Volatility Range & Recovery**: Extended range compression, low-volatility grinding, recovery from \$16k to \$42k.
  4. **2024 Institutional ETF & All-Time High Run**: Spot ETF approval, multi-month consolidation, breakout above \$73k to \$99k.
- **Datasets**:
  - `BINANCE:USD_M_PERP:BTCUSDT:KLINES_1M` (2021–2024)
  - `BINANCE:USD_M_PERP:ETHUSDT:KLINES_1M` (2021–2024)
  - `BINANCE:USD_M_PERP:BTCUSDT:FUNDING_HISTORY` (2021–2024)
  - `BINANCE:USD_M_PERP:ETHUSDT:FUNDING_HISTORY` (2021–2024)
  - `BINANCE:SPOT:BTCUSDT:KLINES_1M` (2021–2024)
  - `BINANCE:SPOT:ETHUSDT:KLINES_1M` (2021–2024)
- **Total Storage Impact**: ~600 MiB (Compressed Silver Parquet with exact `Decimal128(38,18)` precision). Leaves > 7.5 GiB free on disk.

### Research Universe B: `DERIVATIVES_RICH_HISTORY`
- **Period**: 2024-01 to 2024-11 (11 months).
- **Datasets**: Forward open interest, top-trader long/short positioning, taker buy/sell volume ratios.
- **Handling**: When evaluating strategies across the 2021–2024 universe, `oi_state` is explicitly marked `UNAVAILABLE` for periods lacking verified OI data. Strategies conditioned on OI are evaluated specifically on Universe B.

---

## 4. Processing & Compilation Performance Estimate
- **Download Time**: 47 months $\times$ 4 streams $\approx$ 188 files $\times$ ~1 sec/file $\approx$ **3 to 4 minutes**.
- **Parquet Compilation Time**: PyArrow vectorized decompression & casting $\approx$ **2 to 3 minutes**.
- **Total Pipeline Execution**: $\approx$ **5 to 7 minutes** with verified SHA-256 sidecar checksums.
