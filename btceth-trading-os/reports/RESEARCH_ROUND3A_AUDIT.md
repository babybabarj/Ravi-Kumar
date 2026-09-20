# Research Round 3A: Comprehensive Remediation Audit Report

## Authoritative Status
```text
ROUND3_KNOWN_DEFECTIVE_BASELINE = 8d4fbef1fa3da2bba18c0416f8c558bb97e0d727
RESEARCH_ROUND3_ENGINEERING = REMEDIATED
RESEARCH_ROUND3A = VERIFIED
OLD_ROUND3_STATUS = SUPERSEDED_BY_ROUND3A
EDGE_DISCOVERY_STATUS = NO_VALIDATED_EDGE
APPROVED_FOR_SHADOW = 0
APPROVED_FOR_PAPER = 0
2024 HOLDOUT = LOCKED
MAINNET TRADING CAPABILITY = ZERO
```

---

## 1. Audit Scope & 9 Taxonomic Findings

| Finding ID | Classification | Defect Description | Remediation Applied | Status |
| :--- | :--- | :--- | :--- | :--- |
| **AUD-R3A-001** | Structural P&L Normalization | `row[1]=8` parsed as funding rate instead of `row[2]` (`last_funding_rate`), causing \$169M phantom funding. | Corrected column index to `row[2]`, recompiled funding tables for BTC and ETH. | **REMEDIATED** |
| **AUD-R3A-002** | Portfolio Return Accounting | Cumulative P&L divided by capital of first trade only, producing 631,000% RoC. | Implemented `PortfolioEquityEngine` with discrete time-series equity curve, daily Sharpe, and peak-to-trough drawdown. | **REMEDIATED** |
| **AUD-R3A-003** | Candidate Sizing & Semantics | Hardcoded 1.0 BTC sizing, hardcoded `asset="BTC"`, and flat \$2 legging slip. | Implemented dynamic `$50,000` notional sizing per leg, dedicated ETH carry, and proportional bps legging friction. | **REMEDIATED** |
| **AUD-R3A-004** | Cross-Asset Strategy Construction | `STRUCT_C1` referenced `eth_dev[i]` during validation and lacked true 2-perp relative legs. | Implemented `RelativePerpPairEpisode` with strict timestamp joins (`ts_event_ns`) and complete dev/val isolation. | **REMEDIATED** |
| **AUD-R3A-005** | Timestamp Alignment | Perp observations could be assigned from future timestamps. | Enforced strict hour matching (`perp_hour_ts == spot_hour_ts`). | **REMEDIATED** |
| **AUD-R3A-006** | Missing-Data Handling | Silent fallback substitutions of traded close for mark/index/premium prices. | Replaced with `FAIL_CLOSED_NO_FALLBACK` policy, explicit availability booleans, and zero fallback substitution. | **REMEDIATED** |
| **AUD-R3A-007** | Status/Promotion Logic | Strategy status hardcoded to `REJECTED` with empty rejection reasons. | Implemented dynamic policy evaluation; enforced invariant that rejections must contain non-empty reasons. | **REMEDIATED** |
| **AUD-R3A-008** | Acceptance Completeness | Verifier checked only basic file existence without testing mathematical invariants. | Created `tools/verify_research_round3a.py` with 11 strict economic, provenance, and accounting gates. | **REMEDIATED** |
| **AUD-R3A-009** | Official Archive Provenance | Documentation ambiguity on `premiumIndexKlines` vs `premiumPriceKlines`. | Live HEAD probe confirmed `premiumIndexKlines` is `200 OK` on `data.binance.vision` (`premiumPriceKlines` is `404`). | **REMEDIATED** |

---

## 2. Preservation of Research History
In strict compliance with Section 1:
- All original Round 3 files remain intact and untouched in `reports/RESEARCH_ROUND3_*`, `reports/STRUCTURAL_STRATEGY_REPORT_CARDS/`, and `artifacts/research/experiments.sqlite`.
- Round 3A creates a separate, superseding generation of artifacts with Dataset v3.1.0 (`Logical SHA: a085cf7f69d03357...`).

---

## 3. Verified Mechanical Acceptance
- Acceptance Runner: `tools/verify_research_round3a.py`
- Result: `11 / 11 GATES PASSED`
- Full Automated Test Suite: `164 / 164 PASSED`
- Security Boundary: `0 HITS` (`TRADING CAPABILITY = ZERO`)
