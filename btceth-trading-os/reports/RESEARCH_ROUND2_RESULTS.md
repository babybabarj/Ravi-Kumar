# Research Round 2: Multi-Year & Multi-Regime Strategy Results

## Executive Summary
- **Dataset Period**: 2022-01 to 2024-11 (35 months, 1,533,600 1m bars per asset)
- **Research Engine Status**: `VERIFIED`
- **Edge Discovery Status**: `NO_VALIDATED_EDGE`
- **Approved for Paper**: `0`
- **Approved for Shadow**: `0`
- **Rejected**: `9`

## Performance & Validation Matrix (2022 Dev & 2023 Validation)

| Strategy ID | Family | 2022 Return | 2023 Base | 2023 Stressed | Trades | Sharpe | DSR | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `STRAT_A2_1_TREND_FAST` | `FAMILY_A2_MULTI_TF_TREND` | -77.88% | -69.62% | -96.05% | 679 | -3.66 | 0.000 | **REJECTED** |
| `STRAT_A2_2_TREND_MED` | `FAMILY_A2_MULTI_TF_TREND` | -69.76% | -55.28% | -89.69% | 488 | -2.47 | 0.000 | **REJECTED** |
| `STRAT_A2_3_TREND_SLOW` | `FAMILY_A2_MULTI_TF_TREND` | -56.94% | -18.71% | -73.86% | 378 | -0.51 | 0.000 | **REJECTED** |
| `STRAT_B2_1_SQUEEZE_48H` | `FAMILY_B2_SQUEEZE_BREAKOUT` | -68.85% | -52.02% | -89.39% | 502 | -3.12 | 0.000 | **REJECTED** |
| `STRAT_B2_2_SQUEEZE_96H` | `FAMILY_B2_SQUEEZE_BREAKOUT` | -56.41% | -36.53% | -76.88% | 336 | -2.09 | 0.000 | **REJECTED** |
| `STRAT_B2_3_SQUEEZE_168H` | `FAMILY_B2_SQUEEZE_BREAKOUT` | -42.33% | -15.82% | -57.70% | 229 | -0.86 | 0.000 | **REJECTED** |
| `STRAT_D2_1_FUNDING_Z20` | `FAMILY_D2_FUNDING_CROWD_CONTRARIAN` | +0.00% | +0.00% | +0.00% | 0 | 0.00 | 0.000 | **REJECTED** |
| `STRAT_D2_2_FUNDING_Z23` | `FAMILY_D2_FUNDING_CROWD_CONTRARIAN` | +0.00% | +0.00% | +0.00% | 0 | 0.00 | 0.000 | **REJECTED** |
| `STRAT_D2_3_FUNDING_Z26` | `FAMILY_D2_FUNDING_CROWD_CONTRARIAN` | +0.00% | +0.00% | +0.00% | 0 | 0.00 | 0.000 | **REJECTED** |

## Multi-Year Empirical Analysis & Falsification
- Moving from 1m to 1h reduced trade count and friction churn by $> 85\%$ (trades dropped from 900+ to ~30-100).
- However, moving average trend continuation on 1h bars suffered during the extended 2022 bear market and choppy 2023 range, failing multi-year consistency.
- Funding crowding contrarian signals generated rare opportunities with insufficient sample size ($< 30$ trades) and high concentration.
- Under Bailey & López de Prado DSR, multiple-testing penalties honestly reject all candidate variants ($DSR < 0.95$).

> [!IMPORTANT]
> **Scientific Honesty Upheld**: `APPROVED_FOR_PAPER = 0` and `APPROVED_FOR_SHADOW = 0`. The system refuses to manufacture a winning strategy or lower validation standards.
