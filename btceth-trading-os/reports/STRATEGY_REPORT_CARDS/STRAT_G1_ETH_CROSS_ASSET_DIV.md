# Strategy Report Card: `STRAT_G1_ETH_CROSS_ASSET_DIV`

**Status**: ❌ REJECTED  
**Family**: `FAMILY_G_CROSS_ASSET_DIVERGENCE`  
**Symbol**: `ETHUSDT`  
**Evaluation Timestamp**: `2026-09-20T21:18:28.378316+00:00`  
**Code Commit**: `37d204017586f3d695da12a8c9151f71acce824e`  
**Dataset SHA-256**: `a24103d810c36c44...`

---

## 1. Core Hypothesis
> Extreme divergence between ETH and BTC relative performance mean-reverts toward historical equilibrium.

**Parameters**:
```json
{
  "ratio_zscores": "<array_len_43200>",
  "threshold": 1.8
}
```

---

## 2. Empirical Performance Summary (Out-of-Sample)

| Metric | Measured Value | Validation Threshold | Status |
| :--- | :--- | :--- | :--- |
| **OOS Trades** | 38 | $\ge 30$ | PASS |
| **Gross Return** | -6.37% | N/A | INFO |
| **Net Return (Base Costs)** | -11.56% | $> 0.00\%$ | FAIL |
| **Net Return (Stressed Costs)** | -18.05% | $> 0.00\%$ | FAIL |
| **Annualized Sharpe** | -4.65 | $\ge 1.00$ | FAIL |
| **Annualized Sortino** | -6.45 | $\ge 1.30$ | FAIL |
| **Max Drawdown** | 16.17% | $\le 15.00\%$ | FAIL |
| **Profit Factor** | 0.43 | $\ge 1.25$ | FAIL |
| **Win Rate** | 47.4% | N/A | INFO |
| **Net Expectancy (bps/trade)**| -60.3 bps | $\ge +2.0$ bps | FAIL |

---

## 3. Statistical Rigor & Overfitting Diagnostics

| Test / Diagnostic | Result | Acceptance Limit | Outcome |
| :--- | :--- | :--- | :--- |
| **Deflated Sharpe Ratio (DSR)** | 0.000 | $\ge 0.95$ ($p < 0.05$) | FAIL |
| **Probability of Backtest Overfit (PBO)** | 0.50 | $\le 0.50$ | PASS |
| **Parameter Neighborhood Stability** | 0.0% | $\ge 60.0\%$ | FAIL |
| **Top 1% Trade Concentration** | 28.1% | $\le 35.0\%$ | PASS |
| **Bootstrap Expectancy 95% Lower CI** | -122.4 bps | $\ge 0.0$ bps | FAIL |

---

## 4. Promotion Gate Findings & Decision

**Final Tier**: `REJECTED`

### Recorded Findings / Deficiencies:
- Negative net return after base costs (-0.1156 <= 0)
- Fails cost stress survival: net return under stressed costs is -0.1805 <= 0
- Max drawdown exceeded limit (0.162 > 0.150)
- Sharpe ratio below threshold (-4.65 < 1.00)
- Parameter instability (0.0% profitable neighbors < 60.0%)
- Deflated Sharpe Ratio failed multiple testing penalty (DSR=0.000 < 0.95)

---
*Report generated automatically by BTCETH Trading OS Market Brain Research Engine.*
