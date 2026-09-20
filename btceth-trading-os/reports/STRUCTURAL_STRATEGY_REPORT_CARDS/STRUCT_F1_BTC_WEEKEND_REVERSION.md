# Structural Strategy Report Card: `STRUCT_F1_BTC_WEEKEND_REVERSION`

## Identification & Scope
- **Strategy ID**: `STRUCT_F1_BTC_WEEKEND_REVERSION`
- **Family**: `STRUCT_FAMILY_F_WEEKEND_SESSION_EFFECTS`
- **Hypothesis**: Exploiting weekend liquidity drain by entering Friday 22:00 UTC and exiting Sunday 22:00 UTC.
- **Research Round**: `3`
- **Market Neutral Target**: `TRUE` (Delta Hedged Spot + Perp)
- **Status**: **`REJECTED`**
- **Rejection Reasons**: NONE

## Capital & Cost Economics
- **Total Committed Capital**: $175,000 (100% Spot Notional + 50% Perp Margin + 25% Safety Buffer)
- **Round-Trip Breakeven Cost**: 50.00 bps (Base: 50 bps round-trip friction)

## Performance Matrix (2020–2022 Dev & 2023 Validation)
| Metric | 2020–2022 Dev (Base Costs) | 2023 Validation (Base Costs) | 2023 Validation (Stressed Costs) |
| :--- | :--- | :--- | :--- |
| **Trades / Episodes** | 156 | 51 | 51 |
| **Net P&L** | $216,453,226.82 | $71,476,317.85 | $71,465,877.22 |
| **Return on Capital (RoC)** | 1528544.33% | 205800.30% | 205770.24% |
| **Spot Leg P&L** | $10,181.80 | $8,344.74 | $8,344.74 |
| **Perp Leg P&L** | $-10,351.42 | $-8,467.50 | $-8,467.50 |
| **Basis P&L** | $-169.62 | $-122.76 | $-122.76 |
| **Funding P&L** | $216,476,284.37 | $71,484,000.24 | $71,484,000.24 |
| **Friction / Costs** | $22,887.93 | $7,559.63 | $18,000.26 |
| **Max Drawdown** | 0.00% | 0.00% | 0.00% |
| **Annualized Sharpe** | 160.39 | 742.51 | 742.48 |
| **Deflated Sharpe Ratio (DSR)** | - | 0.000 | 0.000 |

## Multi-Year Empirical Analysis
- Cash-and-carry funding yields in 2020-2021 bull markets were positive, but entering and exiting frequently resulted in cumulative transaction costs exceeding realized funding.
- In 2022 and 2023, average funding rates declined to ~5-10 bps per 8h, while spot/perp round-trip friction consumed 50 bps base / 120 bps stressed.
- Under strict cost stress, the net expectancy fails to remain reliably positive across both bull and bear regimes.
