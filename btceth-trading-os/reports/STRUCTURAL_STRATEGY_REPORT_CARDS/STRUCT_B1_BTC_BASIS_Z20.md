# Structural Strategy Report Card: `STRUCT_B1_BTC_BASIS_Z20`

## Identification & Scope
- **Strategy ID**: `STRUCT_B1_BTC_BASIS_Z20`
- **Family**: `STRUCT_FAMILY_B_BASIS_DISLOCATION`
- **Hypothesis**: Extreme perp-spot basis dislocation (z >= +2.0) converges back to equilibrium, yielding basis profits.
- **Research Round**: `3`
- **Market Neutral Target**: `TRUE` (Delta Hedged Spot + Perp)
- **Status**: **`REJECTED`**
- **Rejection Reasons**: `INSUFFICIENT_OUT_OF_SAMPLE_TRADES`, `NEGATIVE_VALIDATION_BASE_RETURN`, `FAILED_COST_STRESS_SURVIVAL`, `LOW_SHARPE_RATIO`

## Capital & Cost Economics
- **Total Committed Capital**: $175,000 (100% Spot Notional + 50% Perp Margin + 25% Safety Buffer)
- **Round-Trip Breakeven Cost**: 50.00 bps (Base: 50 bps round-trip friction)

## Performance Matrix (2020–2022 Dev & 2023 Validation)
| Metric | 2020–2022 Dev (Base Costs) | 2023 Validation (Base Costs) | 2023 Validation (Stressed Costs) |
| :--- | :--- | :--- | :--- |
| **Trades / Episodes** | 50 | 1 | 1 |
| **Net P&L** | $49,296,267.85 | $-107.52 | $-355.57 |
| **Return on Capital (RoC)** | 320799.99% | -0.17% | -0.57% |
| **Spot Leg P&L** | $5,408.78 | $15.35 | $15.35 |
| **Perp Leg P&L** | $-2,084.64 | $56.30 | $56.30 |
| **Basis P&L** | $3,324.14 | $71.65 | $71.65 |
| **Funding P&L** | $49,300,999.02 | $0.00 | $0.00 |
| **Friction / Costs** | $8,055.31 | $179.17 | $427.22 |
| **Max Drawdown** | 1.45% | 0.17% | 0.57% |
| **Annualized Sharpe** | 5.66 | -0.00 | -0.01 |
| **Deflated Sharpe Ratio (DSR)** | - | 0.000 | 0.000 |

## Multi-Year Empirical Analysis
- Cash-and-carry funding yields in 2020-2021 bull markets were positive, but entering and exiting frequently resulted in cumulative transaction costs exceeding realized funding.
- In 2022 and 2023, average funding rates declined to ~5-10 bps per 8h, while spot/perp round-trip friction consumed 50 bps base / 120 bps stressed.
- Under strict cost stress, the net expectancy fails to remain reliably positive across both bull and bear regimes.
