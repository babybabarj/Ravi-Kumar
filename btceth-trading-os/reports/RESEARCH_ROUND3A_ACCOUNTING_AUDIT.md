# Research Round 3A: Structural P&L & Portfolio Accounting Audit

## 1. Executive Summary
This audit documents the identification, mathematical analysis, defect reproduction, and remediation of the structural P&L accounting defects identified in Research Round 3.

**Known Defective Baseline Commit**: `8d4fbef1fa3da2bba18c0416f8c558bb97e0d727`  
**Evaluation Status**: `REMEDIATED & VERIFIED`

---

## 2. Root Cause Analysis of Mathematical Defects

### Defect 1: Binance Vision Funding Rate CSV Column Offset
- **Symptom**: `STRUCT_A2_BTC_CARRY_24H` reported `+$169,795,000` in funding P&L and `631,031%` RoC.
- **Root Cause**: The Binance Vision monthly fundingRate CSV header is:
  `['calc_time', 'funding_interval_hours', 'last_funding_rate']`
  The parser in `tools/build_round3_dataset.py` read `row[1]` (`funding_interval_hours = 8`) instead of `row[2]` (`last_funding_rate = -0.00012359`). Consequently, every funding settlement applied an $800\%$ funding rate rather than $\approx 0.01\%$, inflating funding cash flows by four orders of magnitude ($80,000\times$).
- **Remediation**: `tools/build_round3a_dataset.py` parses `funding_interval_hours = int(row[1])` and `funding_rate = Decimal(row[2])`. Tested and verified by `tests/test_round3a_defect_reproduction.py::test_reproduce_funding_column_offset_defect`.

### Defect 2: Malformed Return on Capital Normalizer
- **Symptom**: Cumulative P&L over hundreds of sequential trades was divided by the committed capital of only the first trade:
  `overall_roc = sum(all net pnl) / cap_metrics[0]["total_committed_capital"]`
- **Root Cause**: Conflated cumulative portfolio P&L with trade-level return on capital.
- **Remediation**: Built `PortfolioEquityEngine` with explicit `FIXED_NOTIONAL` mode. Tracks time-series portfolio equity curve:
  $$\text{period\_return} = \frac{\text{equity}_{\text{end}} - \text{equity}_{\text{start}}}{\text{equity}_{\text{start}}}$$
  Trade-level episode RoC is calculated separately per trade and averaged as `average_episode_roc`.

### Defect 3: Arbitrary \$2 Legging Delay Loss
- **Symptom**: Legging friction was modeled as a flat \$2 price drop regardless of asset or notional size.
- **Root Cause**: Hardcoded BTC-specific dollar constant into generic execution logic.
- **Remediation**: Replaced with proportional basis-point legging friction model:
  $$\text{loss} = \text{notional} \times \frac{\text{delay\_bps}}{10000}$$
  Scales dynamically with committed notional across both BTC and ETH.

---

## 3. Mathematical Accounting Identities Enforced

For every trade episode:
$$\text{basis\_pnl} = \text{spot\_pnl} + \text{perp\_pnl}$$

$$\text{net\_pnl} = \text{spot\_pnl} + \text{perp\_pnl} + \text{funding\_pnl} - \text{execution\_costs} - \text{legging\_costs}$$

For relative perpetual pairs:
$$\text{price\_pnl} = \text{asset1\_pnl} + \text{asset2\_pnl}$$

$$\text{net\_pnl} = \text{price\_pnl} + \text{funding1\_pnl} + \text{funding2\_pnl} - \text{costs}$$

All 9 mathematical fixtures pass with exact equality in [`tests/test_round3a_accounting_fixtures.py`](file:///Users/ravi/btceth-phase1a-mac/btceth-trading-os/tests/test_round3a_accounting_fixtures.py).

---

## 4. Accounting Sanity Limits
- Flag `ACCOUNTING_SANITY_FAILURE` if $|\text{period\_return}| > 500\%$.
- Flag `SHARPE_SANITY_REVIEW_REQUIRED` if $|\text{Sharpe}| > 20.0$.
- In Round 3A, all 11 structural candidates passed sanity checks with 0 flags raised (max return: $-0.27\%$, max Sharpe: $-13.51$).
