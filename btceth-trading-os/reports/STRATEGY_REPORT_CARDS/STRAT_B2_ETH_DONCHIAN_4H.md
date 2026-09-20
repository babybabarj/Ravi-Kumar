# Strategy Report Card: `STRAT_B2_ETH_DONCHIAN_4H`

**Status**: ❌ REJECTED  
**Family**: `FAMILY_B_BREAKOUT_EXPANSION`  
**Symbol**: `ETHUSDT`  
**Evaluation Timestamp**: `2026-09-20T21:18:27.037927+00:00`  
**Code Commit**: `37d204017586f3d695da12a8c9151f71acce824e`  
**Dataset SHA-256**: `a24103d810c36c44...`

---

## 1. Core Hypothesis
> Price breaking out of multi-hour Donchian channels leads to continuation before mean-reverting.

**Parameters**:
```json
{
  "entry_window": 240,
  "exit_window": 120
}
```

---

## 2. Empirical Performance Summary (Out-of-Sample)

| Metric | Measured Value | Validation Threshold | Status |
| :--- | :--- | :--- | :--- |
| **OOS Trades** | 250 | $\ge 30$ | PASS |
| **Gross Return** | -6.74% | N/A | INFO |
| **Net Return (Base Costs)** | -35.92% | $> 0.00\%$ | FAIL |
| **Net Return (Stressed Costs)** | -61.19% | $> 0.00\%$ | FAIL |
| **Annualized Sharpe** | -21.27 | $\ge 1.00$ | FAIL |
| **Annualized Sortino** | -29.51 | $\ge 1.30$ | FAIL |
| **Max Drawdown** | 37.04% | $\le 15.00\%$ | FAIL |
| **Profit Factor** | 0.31 | $\ge 1.25$ | FAIL |
| **Win Rate** | 18.4% | N/A | INFO |
| **Net Expectancy (bps/trade)**| -35.0 bps | $\ge +2.0$ bps | FAIL |

---

## 3. Statistical Rigor & Overfitting Diagnostics

| Test / Diagnostic | Result | Acceptance Limit | Outcome |
| :--- | :--- | :--- | :--- |
| **Deflated Sharpe Ratio (DSR)** | 0.000 | $\ge 0.95$ ($p < 0.05$) | FAIL |
| **Probability of Backtest Overfit (PBO)** | 0.50 | $\le 0.50$ | PASS |
| **Parameter Neighborhood Stability** | 0.0% | $\ge 60.0\%$ | FAIL |
| **Top 1% Trade Concentration** | 26.4% | $\le 35.0\%$ | PASS |
| **Bootstrap Expectancy 95% Lower CI** | -44.4 bps | $\ge 0.0$ bps | FAIL |

---

## 4. Promotion Gate Findings & Decision

**Final Tier**: `REJECTED`

### Recorded Findings / Deficiencies:
- Negative net return after base costs (-0.3592 <= 0)
- Fails cost stress survival: net return under stressed costs is -0.6119 <= 0
- Max drawdown exceeded limit (0.370 > 0.150)
- Sharpe ratio below threshold (-21.27 < 1.00)
- Parameter instability (0.0% profitable neighbors < 60.0%)
- Deflated Sharpe Ratio failed multiple testing penalty (DSR=0.000 < 0.95)

---
*Report generated automatically by BTCETH Trading OS Market Brain Research Engine.*
