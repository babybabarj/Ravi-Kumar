# Structural Strategy Report Card: `STRUCT_D1_BTC_PREMIUM_DIVERGENCE`

## Identification & Scope
- **Strategy ID**: `STRUCT_D1_BTC_PREMIUM_DIVERGENCE`
- **Family**: `STRUCT_FAMILY_D_FUNDING_PREMIUM_DIVERGENCE`
- **Hypothesis**: Entering carry when official Premium Index spikes before trailing funding resets captures upcoming funding surge.
- **Research Round**: `3`
- **Market Neutral Target**: `TRUE` (Delta Hedged Spot + Perp)
- **Status**: **`REJECTED`**
- **Rejection Reasons**: `INSUFFICIENT_OUT_OF_SAMPLE_TRADES`

## Capital & Cost Economics
- **Total Committed Capital**: $175,000 (100% Spot Notional + 50% Perp Margin + 25% Safety Buffer)
- **Round-Trip Breakeven Cost**: 50.00 bps (Base: 50 bps round-trip friction)

## Performance Matrix (2020–2022 Dev & 2023 Validation)
| Metric | 2020–2022 Dev (Base Costs) | 2023 Validation (Base Costs) | 2023 Validation (Stressed Costs) |
| :--- | :--- | :--- | :--- |
| **Trades / Episodes** | 137 | 5 | 5 |
| **Net P&L** | $117,380,938.09 | $3,224,881.41 | $3,223,943.81 |
| **Return on Capital (RoC)** | 817852.41% | 8143.88% | 8141.51% |
| **Spot Leg P&L** | $-27,133.98 | $2,286.26 | $2,286.26 |
| **Perp Leg P&L** | $30,078.31 | $-2,209.90 | $-2,209.90 |
| **Basis P&L** | $2,944.33 | $76.36 | $76.36 |
| **Funding P&L** | $117,402,764.67 | $3,225,484.76 | $3,225,484.76 |
| **Friction / Costs** | $24,770.91 | $679.71 | $1,617.31 |
| **Max Drawdown** | 0.00% | 0.00% | 0.00% |
| **Annualized Sharpe** | 192.61 | 71.84 | 71.84 |
| **Deflated Sharpe Ratio (DSR)** | - | 0.000 | 0.000 |

## Multi-Year Empirical Analysis
- Cash-and-carry funding yields in 2020-2021 bull markets were positive, but entering and exiting frequently resulted in cumulative transaction costs exceeding realized funding.
- In 2022 and 2023, average funding rates declined to ~5-10 bps per 8h, while spot/perp round-trip friction consumed 50 bps base / 120 bps stressed.
- Under strict cost stress, the net expectancy fails to remain reliably positive across both bull and bear regimes.
