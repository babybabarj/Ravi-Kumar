# Strategy Report Card: `STRAT_D2_1_FUNDING_Z20`

**Status**: ❌ REJECTED  
**Family**: `FAMILY_D2_FUNDING_CROWD_CONTRARIAN`  
**Symbol**: `BTCUSDT`  
**Evaluation Timestamp**: `2026-09-20T21:32:49.776899+00:00`  
**Code Commit**: `e0a94eb22b92d823849c041627b87bedaf06e347`  
**Dataset SHA-256**: `59af811657786156...`

---

## 1. Core Hypothesis
> Persistent funding rate dislocation (|z| >= 2.0) precedes directional deleveraging squeeze.

**Parameters**:
```json
{
  "z_thresh": 2.0,
  "strat_id": "STRAT_D2_1_FUNDING_Z20"
}
```

---

## 2. Empirical Performance Summary (Out-of-Sample)

| Metric | Measured Value | Validation Threshold | Status |
| :--- | :--- | :--- | :--- |
| **OOS Trades** | 0 | $\ge 30$ | FAIL |
| **Gross Return** | +0.00% | N/A | INFO |
| **Net Return (Base Costs)** | +0.00% | $> 0.00\%$ | FAIL |
| **Net Return (Stressed Costs)** | +0.00% | $> 0.00\%$ | FAIL |
| **Annualized Sharpe** | 0.00 | $\ge 1.00$ | FAIL |
| **Annualized Sortino** | 0.00 | $\ge 1.30$ | FAIL |
| **Max Drawdown** | 0.00% | $\le 15.00\%$ | PASS |
| **Profit Factor** | 0.00 | $\ge 1.25$ | FAIL |
| **Win Rate** | 0.0% | N/A | INFO |
| **Net Expectancy (bps/trade)**| +0.0 bps | $\ge +2.0$ bps | FAIL |

---

## 3. Statistical Rigor & Overfitting Diagnostics

| Test / Diagnostic | Result | Acceptance Limit | Outcome |
| :--- | :--- | :--- | :--- |
| **Deflated Sharpe Ratio (DSR)** | 0.000 | $\ge 0.95$ ($p < 0.05$) | FAIL |
| **Probability of Backtest Overfit (PBO)** | 0.00 | $\le 0.50$ | PASS |
| **Parameter Neighborhood Stability** | 50.0% | $\ge 60.0\%$ | FAIL |
| **Top 1% Trade Concentration** | 100.0% | $\le 35.0\%$ | FAIL |
| **Bootstrap Expectancy 95% Lower CI** | +0.0 bps | $\ge 0.0$ bps | PASS |

---

## 4. Promotion Gate Findings & Decision

**Final Tier**: `REJECTED`

### Recorded Findings / Deficiencies:
- Insufficient OOS trades (0 < 30)
- Negative net return after base costs (0.0000 <= 0)
- Fails cost stress survival: net return under stressed costs is 0.0000 <= 0
- Sharpe ratio below threshold (0.00 < 1.00)
- Excessive trade profit concentration (top 1 trade is 100.0% > 35.0%)
- Parameter instability (50.0% profitable neighbors < 60.0%)
- Multi-year inconsistency: profitable years 0.0% < 66.0% or max single-year drawdown 0.0% > 12.0%
- Deflated Sharpe Ratio failed multiple testing penalty (DSR=0.000 < 0.95)

---
*Report generated automatically by BTCETH Trading OS Market Brain Research Engine.*
