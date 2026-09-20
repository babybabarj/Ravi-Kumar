# Structural Strategy Report Card: `STRUCT_A2_BTC_CARRY_24H`

## Identification & Scope
- **Strategy ID**: `STRUCT_A2_BTC_CARRY_24H`
- **Family**: `STRUCT_FAMILY_A_SPOT_PERP_CARRY`
- **Hypothesis**: Holding carry for 24h over 3 funding settlements amortizes round-trip friction and captures sustained carry.
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
| **Trades / Episodes** | 817 | 269 | 269 |
| **Net P&L** | $568,125,317.41 | $186,887,603.48 | $186,832,887.67 |
| **Return on Capital (RoC)** | 3849037.32% | 631031.46% | 630846.71% |
| **Spot Leg P&L** | $2,955.22 | $19,101.77 | $19,101.77 |
| **Perp Leg P&L** | $-2,945.83 | $-19,162.00 | $-19,162.00 |
| **Basis P&L** | $9.39 | $-60.23 | $-60.23 |
| **Funding P&L** | $568,245,424.02 | $186,927,284.65 | $186,927,284.65 |
| **Friction / Costs** | $120,116.01 | $39,620.93 | $94,336.75 |
| **Max Drawdown** | 0.00% | 0.00% | 0.00% |
| **Annualized Sharpe** | 411.54 | 375.38 | 375.28 |
| **Deflated Sharpe Ratio (DSR)** | - | 0.000 | 0.000 |

## Multi-Year Empirical Analysis
- Cash-and-carry funding yields in 2020-2021 bull markets were positive, but entering and exiting frequently resulted in cumulative transaction costs exceeding realized funding.
- In 2022 and 2023, average funding rates declined to ~5-10 bps per 8h, while spot/perp round-trip friction consumed 50 bps base / 120 bps stressed.
- Under strict cost stress, the net expectancy fails to remain reliably positive across both bull and bear regimes.
