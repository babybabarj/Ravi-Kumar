# Structural Strategy Report Card: `STRUCT_B2_BTC_BASIS_Z25`

## Identification & Scope
- **Strategy ID**: `STRUCT_B2_BTC_BASIS_Z25`
- **Family**: `STRUCT_FAMILY_B_BASIS_DISLOCATION`
- **Hypothesis**: Severe basis dislocation (z >= +2.5) provides larger profit margin against transaction fees.
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
| **Trades / Episodes** | 12 | 0 | 0 |
| **Net P&L** | $10,552,974.37 | $0.00 | $0.00 |
| **Return on Capital (RoC)** | 62336.26% | 0.00% | 0.00% |
| **Spot Leg P&L** | $4,477.13 | $0.00 | $0.00 |
| **Perp Leg P&L** | $-2,853.07 | $0.00 | $0.00 |
| **Basis P&L** | $1,624.06 | $0.00 | $0.00 |
| **Funding P&L** | $10,552,932.28 | $0.00 | $0.00 |
| **Friction / Costs** | $1,581.97 | $0.00 | $0.00 |
| **Max Drawdown** | 0.00% | 0.00% | 0.00% |
| **Annualized Sharpe** | 2.74 | 0.00 | 0.00 |
| **Deflated Sharpe Ratio (DSR)** | - | 0.000 | 0.000 |

## Multi-Year Empirical Analysis
- Cash-and-carry funding yields in 2020-2021 bull markets were positive, but entering and exiting frequently resulted in cumulative transaction costs exceeding realized funding.
- In 2022 and 2023, average funding rates declined to ~5-10 bps per 8h, while spot/perp round-trip friction consumed 50 bps base / 120 bps stressed.
- Under strict cost stress, the net expectancy fails to remain reliably positive across both bull and bear regimes.
