# Research Round 3: Historical Data Extension & Tiering Plan

## 1. Background & Empirical Probe Results
To avoid overfitting and ensure multi-year structural stability, Research Round 3 investigated expanding the development dataset backward into 2020 and 2021 rather than opening the locked 2024 holdout.

An automated probe across Binance Vision archives produced the following earliest common coverage matrix:

| Series | BTCUSDT Earliest | ETHUSDT Earliest | Status |
| :--- | :--- | :--- | :--- |
| **Spot 1m Klines** | 2019-01 | 2019-01 | AVAILABLE |
| **USD-M Perp 1m Klines** | 2020-01 | 2020-01 | AVAILABLE |
| **Funding Rate Events** | 2020-01 | 2020-01 | AVAILABLE |
| **Mark Price 1m Klines** | 2020-01 | 2020-01 | AVAILABLE |
| **Index Price 1m Klines** | 2020-01 | 2020-01 | AVAILABLE |
| **Premium Index 1m Klines** | 2020-01 | 2020-01 | AVAILABLE |

**Conclusion**: The earliest common timestamp where all six canonical series exist across both BTC and ETH is **`2020-01-01 00:00:00 UTC`**.

---

## 2. Chronological Dataset Partitioning

```text
2020-01-01                                     2022-12-31       2023-12-31       2024-11-30
├─── DEVELOPMENT DATASET (36 Months) ───────────────┼── VALID ────┼── HOLDOUT ─────┤
│    • 2020: Post-halving & early DeFi summer       │  12 Months  │  11 Months     │
│    • 2021: Bull peak, leverage extremes           │  (2023)     │  (2024)        │
│    • 2022: Terra/Luna, 3AC, FTX cascades          │  Recovery   │  LOCKED        │
└───────────────────────────────────────────────────┴─────────────┴────────────────┘
```

### Partition Definitions:
1. **Development Set (2020-01-01 to 2022-12-31, 36 Months)**:
   - Spans diverse market regimes: extreme bull runs, excessive positive funding crowding, sudden liquidation cascades, and the prolonged 2022 bear market with deep negative funding.
   - Used for structural hypothesis testing, basis feature generation, and parameter calibration.
2. **Validation Set (2023-01-01 to 2023-12-31, 12 Months)**:
   - Sideways consolidation and gradual recovery. Used for out-of-sample confirmation, cost stress testing, and multiple testing adjustments.
3. **Final Holdout Set (2024-01-01 to 2024-11-30, 11 Months)**:
   - `HOLDOUT_LOCKED = TRUE`.
   - Never accessed during strategy design, parameter search, or hypothesis rejection.
   - Only unlocked if a true structural finalist passes all development and validation criteria under frozen parameters.

---

## 3. Tiered Dataset Architecture

To maintain modularity and high execution efficiency, data is organized into three explicit tiers:

### Tier 1: `CORE_PRICE_HISTORY`
- **Contents**: Traded Spot 1m klines + Traded USD-M Perp 1m klines.
- **Coverage**: 2020-01 to 2024-11 (59 months).
- **Columns**: `instrument_id`, `ts_event_ns`, `open`, `high`, `low`, `close`, `volume`, `quote_volume`, `trade_count`.
- **Purpose**: Order execution simulation, fill prices, slippage evaluation.

### Tier 2: `CARRY_HISTORY`
- **Contents**: Official 8-hour funding rate settlement events.
- **Coverage**: 2020-01 to 2024-11 (approx. 5,385 settlement events per asset).
- **Columns**: `instrument_id`, `ts_event_ns`, `funding_interval_hours`, `funding_rate`.
- **Purpose**: Point-in-time funding cash flow calculation.

### Tier 3: `REFERENCE_PRICE_HISTORY`
- **Contents**: Official Binance `markPriceKlines`, `indexPriceKlines`, and `premiumIndexKlines`.
- **Coverage**: 2020-01 to 2023-12 (48 months for Dev/Validation).
- **Columns**: `instrument_id`, `ts_event_ns`, `open`, `high`, `low`, `close`.
- **Purpose**: Liquidation proximity evaluation, maintenance margin tracking, rolling 8h premium TWAP, and true basis dislocation analysis.
