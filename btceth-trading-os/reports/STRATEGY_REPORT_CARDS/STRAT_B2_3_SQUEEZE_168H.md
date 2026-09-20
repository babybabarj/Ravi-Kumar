# Strategy Report Card: `STRAT_B2_3_SQUEEZE_168H`

**Status**: ❌ REJECTED  
**Family**: `FAMILY_B2_SQUEEZE_BREAKOUT`  
**Symbol**: `BTCUSDT`  
**Evaluation Timestamp**: `2026-09-20T21:32:49.556777+00:00`  
**Code Commit**: `e0a94eb22b92d823849c041627b87bedaf06e347`  
**Dataset SHA-256**: `59af811657786156...`

---

## 1. Core Hypothesis
> Extended volatility compression followed by Donchian channel breakout generates directional trend persistence.

**Parameters**:
```json
{
  "channel": 168,
  "exit_ch": 72,
  "strat_id": "STRAT_B2_3_SQUEEZE_168H"
}
```

---

## 2. Empirical Performance Summary (Out-of-Sample)

| Metric | Measured Value | Validation Threshold | Status |
| :--- | :--- | :--- | :--- |
| **OOS Trades** | 229 | $\ge 30$ | PASS |
| **Gross Return** | +7.08% | N/A | INFO |
| **Net Return (Base Costs)** | -15.82% | $> 0.00\%$ | FAIL |
| **Net Return (Stressed Costs)** | -57.70% | $> 0.00\%$ | FAIL |
| **Annualized Sharpe** | -0.86 | $\ge 1.00$ | FAIL |
| **Annualized Sortino** | -1.56 | $\ge 1.30$ | FAIL |
| **Max Drawdown** | 24.77% | $\le 15.00\%$ | FAIL |
| **Profit Factor** | 0.84 | $\ge 1.25$ | FAIL |
| **Win Rate** | 24.9% | N/A | INFO |
| **Net Expectancy (bps/trade)**| -6.7 bps | $\ge +2.0$ bps | FAIL |

---

## 3. Statistical Rigor & Overfitting Diagnostics

| Test / Diagnostic | Result | Acceptance Limit | Outcome |
| :--- | :--- | :--- | :--- |
| **Deflated Sharpe Ratio (DSR)** | 0.000 | $\ge 0.95$ ($p < 0.05$) | FAIL |
| **Probability of Backtest Overfit (PBO)** | 0.00 | $\le 0.50$ | PASS |
| **Parameter Neighborhood Stability** | 50.0% | $\ge 60.0\%$ | FAIL |
| **Top 1% Trade Concentration** | 10.0% | $\le 35.0\%$ | PASS |
| **Bootstrap Expectancy 95% Lower CI** | +0.0 bps | $\ge 0.0$ bps | PASS |

---

## 4. Promotion Gate Findings & Decision

**Final Tier**: `REJECTED`

### Recorded Findings / Deficiencies:
- Negative net return after base costs (-0.1582 <= 0)
- Fails cost stress survival: net return under stressed costs is -0.5770 <= 0
- Max drawdown exceeded limit (0.248 > 0.150)
- Sharpe ratio below threshold (-0.86 < 1.00)
- Parameter instability (50.0% profitable neighbors < 60.0%)
- Multi-year inconsistency: profitable years 0.0% < 66.0% or max single-year drawdown 42.5% > 12.0%
- Deflated Sharpe Ratio failed multiple testing penalty (DSR=0.000 < 0.95)

---
*Report generated automatically by BTCETH Trading OS Market Brain Research Engine.*
