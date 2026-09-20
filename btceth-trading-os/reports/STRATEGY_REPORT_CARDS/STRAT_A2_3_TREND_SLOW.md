# Strategy Report Card: `STRAT_A2_3_TREND_SLOW`

**Status**: ❌ REJECTED  
**Family**: `FAMILY_A2_MULTI_TF_TREND`  
**Symbol**: `BTCUSDT`  
**Evaluation Timestamp**: `2026-09-20T21:32:47.378785+00:00`  
**Code Commit**: `e0a94eb22b92d823849c041627b87bedaf06e347`  
**Dataset SHA-256**: `59af811657786156...`

---

## 1. Core Hypothesis
> Multi-day trend continuation on 1h bars when 48h trend slope confirms and funding rate is non-extreme.

**Parameters**:
```json
{
  "fast": 72,
  "slow": 240,
  "slope_thresh": 0.01,
  "strat_id": "STRAT_A2_3_TREND_SLOW"
}
```

---

## 2. Empirical Performance Summary (Out-of-Sample)

| Metric | Measured Value | Validation Threshold | Status |
| :--- | :--- | :--- | :--- |
| **OOS Trades** | 378 | $\ge 30$ | PASS |
| **Gross Return** | +19.09% | N/A | INFO |
| **Net Return (Base Costs)** | -18.71% | $> 0.00\%$ | FAIL |
| **Net Return (Stressed Costs)** | -73.86% | $> 0.00\%$ | FAIL |
| **Annualized Sharpe** | -0.51 | $\ge 1.00$ | FAIL |
| **Annualized Sortino** | -0.81 | $\ge 1.30$ | FAIL |
| **Max Drawdown** | 39.90% | $\le 15.00\%$ | FAIL |
| **Profit Factor** | 0.93 | $\ge 1.25$ | FAIL |
| **Win Rate** | 23.3% | N/A | INFO |
| **Net Expectancy (bps/trade)**| -3.1 bps | $\ge +2.0$ bps | FAIL |

---

## 3. Statistical Rigor & Overfitting Diagnostics

| Test / Diagnostic | Result | Acceptance Limit | Outcome |
| :--- | :--- | :--- | :--- |
| **Deflated Sharpe Ratio (DSR)** | 0.000 | $\ge 0.95$ ($p < 0.05$) | FAIL |
| **Probability of Backtest Overfit (PBO)** | 0.00 | $\le 0.50$ | PASS |
| **Parameter Neighborhood Stability** | 50.0% | $\ge 60.0\%$ | FAIL |
| **Top 1% Trade Concentration** | 12.4% | $\le 35.0\%$ | PASS |
| **Bootstrap Expectancy 95% Lower CI** | +0.0 bps | $\ge 0.0$ bps | PASS |

---

## 4. Promotion Gate Findings & Decision

**Final Tier**: `REJECTED`

### Recorded Findings / Deficiencies:
- Negative net return after base costs (-0.1871 <= 0)
- Fails cost stress survival: net return under stressed costs is -0.7386 <= 0
- Max drawdown exceeded limit (0.399 > 0.150)
- Sharpe ratio below threshold (-0.51 < 1.00)
- Parameter instability (50.0% profitable neighbors < 60.0%)
- Multi-year inconsistency: profitable years 0.0% < 66.0% or max single-year drawdown 65.2% > 12.0%
- Deflated Sharpe Ratio failed multiple testing penalty (DSR=0.000 < 0.95)

---
*Report generated automatically by BTCETH Trading OS Market Brain Research Engine.*
