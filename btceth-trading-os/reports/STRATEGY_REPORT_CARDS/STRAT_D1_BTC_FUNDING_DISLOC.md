# Strategy Report Card: `STRAT_D1_BTC_FUNDING_DISLOC`

**Status**: ❌ REJECTED  
**Family**: `FAMILY_D_FUNDING_DISLOCATION`  
**Symbol**: `BTCUSDT`  
**Evaluation Timestamp**: `2026-09-20T21:18:28.139752+00:00`  
**Code Commit**: `37d204017586f3d695da12a8c9151f71acce824e`  
**Dataset SHA-256**: `a24103d810c36c44...`

---

## 1. Core Hypothesis
> Extreme crowded perpetual funding rates precede directional unwind as over-leveraged positioning liquidates.

**Parameters**:
```json
{
  "aligned_funding_zscores": "<array_len_43200>",
  "z_threshold": 1.8
}
```

---

## 2. Empirical Performance Summary (Out-of-Sample)

| Metric | Measured Value | Validation Threshold | Status |
| :--- | :--- | :--- | :--- |
| **OOS Trades** | 15 | $\ge 30$ | FAIL |
| **Gross Return** | -7.92% | N/A | INFO |
| **Net Return (Base Costs)** | -10.11% | $> 0.00\%$ | FAIL |
| **Net Return (Stressed Costs)** | -12.95% | $> 0.00\%$ | FAIL |
| **Annualized Sharpe** | -6.87 | $\ge 1.00$ | FAIL |
| **Annualized Sortino** | -9.54 | $\ge 1.30$ | FAIL |
| **Max Drawdown** | 13.92% | $\le 15.00\%$ | PASS |
| **Profit Factor** | 0.12 | $\ge 1.25$ | FAIL |
| **Win Rate** | 37.5% | N/A | INFO |
| **Net Expectancy (bps/trade)**| -128.0 bps | $\ge +2.0$ bps | FAIL |

---

## 3. Statistical Rigor & Overfitting Diagnostics

| Test / Diagnostic | Result | Acceptance Limit | Outcome |
| :--- | :--- | :--- | :--- |
| **Deflated Sharpe Ratio (DSR)** | 0.000 | $\ge 0.95$ ($p < 0.05$) | FAIL |
| **Probability of Backtest Overfit (PBO)** | 0.50 | $\le 0.50$ | PASS |
| **Parameter Neighborhood Stability** | 0.0% | $\ge 60.0\%$ | FAIL |
| **Top 1% Trade Concentration** | 71.6% | $\le 35.0\%$ | FAIL |
| **Bootstrap Expectancy 95% Lower CI** | -247.2 bps | $\ge 0.0$ bps | FAIL |

---

## 4. Promotion Gate Findings & Decision

**Final Tier**: `REJECTED`

### Recorded Findings / Deficiencies:
- Insufficient OOS trades (15 < 30)
- Negative net return after base costs (-0.1011 <= 0)
- Fails cost stress survival: net return under stressed costs is -0.1295 <= 0
- Sharpe ratio below threshold (-6.87 < 1.00)
- Excessive trade profit concentration (top 1 trade is 71.6% > 35.0%)
- Parameter instability (0.0% profitable neighbors < 60.0%)
- Deflated Sharpe Ratio failed multiple testing penalty (DSR=0.000 < 0.95)

---
*Report generated automatically by BTCETH Trading OS Market Brain Research Engine.*
