# Strategy Report Card: `STRAT_B2_1_SQUEEZE_48H`

**Status**: ❌ REJECTED  
**Family**: `FAMILY_B2_SQUEEZE_BREAKOUT`  
**Symbol**: `BTCUSDT`  
**Evaluation Timestamp**: `2026-09-20T21:32:48.434074+00:00`  
**Code Commit**: `e0a94eb22b92d823849c041627b87bedaf06e347`  
**Dataset SHA-256**: `59af811657786156...`

---

## 1. Core Hypothesis
> Extended volatility compression followed by Donchian channel breakout generates directional trend persistence.

**Parameters**:
```json
{
  "channel": 48,
  "exit_ch": 24,
  "strat_id": "STRAT_B2_1_SQUEEZE_48H"
}
```

---

## 2. Empirical Performance Summary (Out-of-Sample)

| Metric | Measured Value | Validation Threshold | Status |
| :--- | :--- | :--- | :--- |
| **OOS Trades** | 502 | $\ge 30$ | PASS |
| **Gross Return** | -1.82% | N/A | INFO |
| **Net Return (Base Costs)** | -52.02% | $> 0.00\%$ | FAIL |
| **Net Return (Stressed Costs)** | -89.39% | $> 0.00\%$ | FAIL |
| **Annualized Sharpe** | -3.12 | $\ge 1.00$ | FAIL |
| **Annualized Sortino** | -5.31 | $\ge 1.30$ | FAIL |
| **Max Drawdown** | 55.80% | $\le 15.00\%$ | FAIL |
| **Profit Factor** | 0.65 | $\ge 1.25$ | FAIL |
| **Win Rate** | 23.1% | N/A | INFO |
| **Net Expectancy (bps/trade)**| -14.0 bps | $\ge +2.0$ bps | FAIL |

---

## 3. Statistical Rigor & Overfitting Diagnostics

| Test / Diagnostic | Result | Acceptance Limit | Outcome |
| :--- | :--- | :--- | :--- |
| **Deflated Sharpe Ratio (DSR)** | 0.000 | $\ge 0.95$ ($p < 0.05$) | FAIL |
| **Probability of Backtest Overfit (PBO)** | 0.00 | $\le 0.50$ | PASS |
| **Parameter Neighborhood Stability** | 50.0% | $\ge 60.0\%$ | FAIL |
| **Top 1% Trade Concentration** | 11.4% | $\le 35.0\%$ | PASS |
| **Bootstrap Expectancy 95% Lower CI** | +0.0 bps | $\ge 0.0$ bps | PASS |

---

## 4. Promotion Gate Findings & Decision

**Final Tier**: `REJECTED`

### Recorded Findings / Deficiencies:
- Negative net return after base costs (-0.5202 <= 0)
- Fails cost stress survival: net return under stressed costs is -0.8939 <= 0
- Max drawdown exceeded limit (0.558 > 0.150)
- Sharpe ratio below threshold (-3.12 < 1.00)
- Parameter instability (50.0% profitable neighbors < 60.0%)
- Multi-year inconsistency: profitable years 0.0% < 66.0% or max single-year drawdown 69.9% > 12.0%
- Deflated Sharpe Ratio failed multiple testing penalty (DSR=0.000 < 0.95)

---
*Report generated automatically by BTCETH Trading OS Market Brain Research Engine.*
