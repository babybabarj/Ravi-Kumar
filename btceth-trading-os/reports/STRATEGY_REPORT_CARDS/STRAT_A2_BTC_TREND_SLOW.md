# Strategy Report Card: `STRAT_A2_BTC_TREND_SLOW`

**Status**: ❌ REJECTED  
**Family**: `FAMILY_A_TREND_MOMENTUM`  
**Symbol**: `BTCUSDT`  
**Evaluation Timestamp**: `2026-09-20T21:18:25.596286+00:00`  
**Code Commit**: `37d204017586f3d695da12a8c9151f71acce824e`  
**Dataset SHA-256**: `a24103d810c36c44...`

---

## 1. Core Hypothesis
> Directional momentum persists over multi-hour horizons following moving average crossovers in trending regimes.

**Parameters**:
```json
{
  "fast_window": 30,
  "slow_window": 180,
  "threshold_bps": 10.0
}
```

---

## 2. Empirical Performance Summary (Out-of-Sample)

| Metric | Measured Value | Validation Threshold | Status |
| :--- | :--- | :--- | :--- |
| **OOS Trades** | 334 | $\ge 30$ | PASS |
| **Gross Return** | +6.28% | N/A | INFO |
| **Net Return (Base Costs)** | -35.63% | $> 0.00\%$ | FAIL |
| **Net Return (Stressed Costs)** | -67.05% | $> 0.00\%$ | FAIL |
| **Annualized Sharpe** | -22.08 | $\ge 1.00$ | FAIL |
| **Annualized Sortino** | -30.06 | $\ge 1.30$ | FAIL |
| **Max Drawdown** | 35.74% | $\le 15.00\%$ | FAIL |
| **Profit Factor** | 0.28 | $\ge 1.25$ | FAIL |
| **Win Rate** | 18.0% | N/A | INFO |
| **Net Expectancy (bps/trade)**| -26.1 bps | $\ge +2.0$ bps | FAIL |

---

## 3. Statistical Rigor & Overfitting Diagnostics

| Test / Diagnostic | Result | Acceptance Limit | Outcome |
| :--- | :--- | :--- | :--- |
| **Deflated Sharpe Ratio (DSR)** | 0.000 | $\ge 0.95$ ($p < 0.05$) | FAIL |
| **Probability of Backtest Overfit (PBO)** | 0.50 | $\le 0.50$ | PASS |
| **Parameter Neighborhood Stability** | 0.0% | $\ge 60.0\%$ | FAIL |
| **Top 1% Trade Concentration** | 16.5% | $\le 35.0\%$ | PASS |
| **Bootstrap Expectancy 95% Lower CI** | -31.8 bps | $\ge 0.0$ bps | FAIL |

---

## 4. Promotion Gate Findings & Decision

**Final Tier**: `REJECTED`

### Recorded Findings / Deficiencies:
- Negative net return after base costs (-0.3563 <= 0)
- Fails cost stress survival: net return under stressed costs is -0.6705 <= 0
- Max drawdown exceeded limit (0.357 > 0.150)
- Sharpe ratio below threshold (-22.08 < 1.00)
- Parameter instability (0.0% profitable neighbors < 60.0%)
- Deflated Sharpe Ratio failed multiple testing penalty (DSR=0.000 < 0.95)

---
*Report generated automatically by BTCETH Trading OS Market Brain Research Engine.*
