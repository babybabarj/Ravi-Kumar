# Strategy Report Card: `STRAT_C1_BTC_MEAN_REV_1H`

**Status**: ❌ REJECTED  
**Family**: `FAMILY_C_MEAN_REVERSION`  
**Symbol**: `BTCUSDT`  
**Evaluation Timestamp**: `2026-09-20T21:18:27.909454+00:00`  
**Code Commit**: `37d204017586f3d695da12a8c9151f71acce824e`  
**Dataset SHA-256**: `a24103d810c36c44...`

---

## 1. Core Hypothesis
> Extreme short-term deviations from the rolling moving average mean-revert toward the equilibrium center.

**Parameters**:
```json
{
  "window": 60,
  "entry_z": 2.2,
  "exit_z": 0.5
}
```

---

## 2. Empirical Performance Summary (Out-of-Sample)

| Metric | Measured Value | Validation Threshold | Status |
| :--- | :--- | :--- | :--- |
| **OOS Trades** | 606 | $\ge 30$ | PASS |
| **Gross Return** | +8.89% | N/A | INFO |
| **Net Return (Base Costs)** | -56.29% | $> 0.00\%$ | FAIL |
| **Net Return (Stressed Costs)** | -87.08% | $> 0.00\%$ | FAIL |
| **Annualized Sharpe** | -52.75 | $\ge 1.00$ | FAIL |
| **Annualized Sortino** | -66.56 | $\ge 1.30$ | FAIL |
| **Max Drawdown** | 56.32% | $\le 15.00\%$ | FAIL |
| **Profit Factor** | 0.04 | $\ge 1.25$ | FAIL |
| **Win Rate** | 9.9% | N/A | INFO |
| **Net Expectancy (bps/trade)**| -27.1 bps | $\ge +2.0$ bps | FAIL |

---

## 3. Statistical Rigor & Overfitting Diagnostics

| Test / Diagnostic | Result | Acceptance Limit | Outcome |
| :--- | :--- | :--- | :--- |
| **Deflated Sharpe Ratio (DSR)** | 0.000 | $\ge 0.95$ ($p < 0.05$) | FAIL |
| **Probability of Backtest Overfit (PBO)** | 0.50 | $\le 0.50$ | PASS |
| **Parameter Neighborhood Stability** | 0.0% | $\ge 60.0\%$ | FAIL |
| **Top 1% Trade Concentration** | 25.8% | $\le 35.0\%$ | PASS |
| **Bootstrap Expectancy 95% Lower CI** | -30.1 bps | $\ge 0.0$ bps | FAIL |

---

## 4. Promotion Gate Findings & Decision

**Final Tier**: `REJECTED`

### Recorded Findings / Deficiencies:
- Negative net return after base costs (-0.5629 <= 0)
- Fails cost stress survival: net return under stressed costs is -0.8708 <= 0
- Max drawdown exceeded limit (0.563 > 0.150)
- Sharpe ratio below threshold (-52.75 < 1.00)
- Parameter instability (0.0% profitable neighbors < 60.0%)
- Deflated Sharpe Ratio failed multiple testing penalty (DSR=0.000 < 0.95)

---
*Report generated automatically by BTCETH Trading OS Market Brain Research Engine.*
