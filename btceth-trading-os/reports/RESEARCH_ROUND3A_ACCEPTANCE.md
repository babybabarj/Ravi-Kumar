# Research Round 3A: Mechanical Acceptance Gate Report

**Acceptance Status**: `✅ ALL GATES PASSED`  
**Timestamp**: `2026-09-20T22:01:28.344197+00:00`  
**Code Commit**: `8d4fbef1fa3da2bba18c0416f8c558bb97e0d727`  
**Dataset Version**: `3.1.0`  
**2024 Holdout**: `LOCKED`  

## Acceptance Gate Status Matrix

| Gate / Invariant | Status | Description |
| :--- | :--- | :--- |
| **Defect Reproduction** | PASS | All Round 3 defects reproduced mathematically and fixed |
| **Premium Archive Provenance** | PASS | `premiumIndexKlines` verified as authoritative archive path on Binance Vision |
| **Dataset v3.1.0 Integrity** | PASS | v3.0.0 preserved; v3.1.0 Logical SHA: `a085cf7f69d03357...` |
| **Source Alignment Quality** | PASS | Exact-hour matching, zero fallback substitutions, `FAIL_CLOSED_NO_FALLBACK` |
| **Exact Accounting Fixtures** | PASS | All 9 hand-verifiable multi-leg fixtures passed |
| **Portfolio Equity Sanity** | PASS | Real equity curve, concurrency control, all sanity limits clean |
| **Candidate Semantics & Policy** | PASS | Genuine ETH carry & 2-perp relative pairs, non-empty rejection reasons |
| **Zero Forced Promotion** | PASS | APPROVED_FOR_PAPER = 0, APPROVED_FOR_SHADOW = 0 |
| **2024 Holdout Lock** | PASS | HOLDOUT_LOCKED = TRUE; 2024 dataset completely unopened |
| **Security Invariant** | PASS | TRADING CAPABILITY = ZERO, 0 forbidden mutation hits |
| **Automated Tests** | PASS | 164 passed cleanly |
