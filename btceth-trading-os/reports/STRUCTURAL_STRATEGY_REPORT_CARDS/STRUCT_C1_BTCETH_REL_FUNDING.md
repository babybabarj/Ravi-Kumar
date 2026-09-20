# Structural Strategy Report Card: `STRUCT_C1_BTCETH_REL_FUNDING`

## Identification & Scope
- **Strategy ID**: `STRUCT_C1_BTCETH_REL_FUNDING`
- **Family**: `STRUCT_FAMILY_C_RELATIVE_CARRY`
- **Hypothesis**: Cross-asset funding divergence between BTC and ETH can be harvested via beta-hedged perp pair.
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
| **Trades / Episodes** | 0 | 118 | 118 |
| **Net P&L** | $0.00 | $169,777,010.29 | $169,752,222.37 |
| **Return on Capital (RoC)** | 0.00% | 427887.72% | 427825.24% |
| **Spot Leg P&L** | $0.00 | $14,034.09 | $14,034.09 |
| **Perp Leg P&L** | $0.00 | $-14,087.00 | $-14,087.00 |
| **Basis P&L** | $0.00 | $-52.91 | $-52.91 |
| **Funding P&L** | $0.00 | $169,795,004.94 | $169,795,004.94 |
| **Friction / Costs** | $0.00 | $17,941.74 | $42,729.65 |
| **Max Drawdown** | 0.00% | 0.00% | 0.00% |
| **Annualized Sharpe** | 0.00 | 570.85 | 570.83 |
| **Deflated Sharpe Ratio (DSR)** | - | 0.000 | 0.000 |

## Multi-Year Empirical Analysis
- Cash-and-carry funding yields in 2020-2021 bull markets were positive, but entering and exiting frequently resulted in cumulative transaction costs exceeding realized funding.
- In 2022 and 2023, average funding rates declined to ~5-10 bps per 8h, while spot/perp round-trip friction consumed 50 bps base / 120 bps stressed.
- Under strict cost stress, the net expectancy fails to remain reliably positive across both bull and bear regimes.
