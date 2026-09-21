# Research Round 3B.0: Reliability Acceptance Gate Report

**Acceptance Status**: `VERIFIED`  
**Timestamp**: `2026-09-21T17:21:49.015681+00:00`  
**Code Commit**: `411cb52fd09031d696427fbdd6c2e82feeed11da`  
**Canonical Baseline Commit**: `cfa80f3aabbb75a28969701d8013f6784c35a495`  
**Trading Capability**: `ZERO`  
**2024 Holdout**: `LOCKED`  
**Approved for Shadow**: `0`  
**Approved for Paper**: `0`  

---

## 1. Mechanical Reliability Gates Matrix

| Gate / Invariant | Status | Verification Summary |
| :--- | :--- | :--- |
| **WIP Audit & Classification** | `PASS` | 13/13 WIP files audited independently; 0 `COPY_AS_IS` |
| **Canonical Baseline Ancestry** | `PASS` | Branch descends strictly from canonical post-merge HEAD `cfa80f3` |
| **WIP Safety Branch Untouched** | `PASS` | Preserved `origin/btceth-round3b-wip-safety` intact at `11d6e37` |
| **Canonical Snapshot Untouched**| `PASS` | Preserved `origin/btceth-phase1b-postmerge-snapshot-20260921` intact |
| **Independent Oracle Isolation**| `PASS` | Zero `btceth_os` imports (stdlib + Decimal only) |
| **Oracle 500+ Case Reconciliation** | `PASS` | 520/520 exact matches across all structures; $0.01 mutation detected |
| **Portfolio Capital Governor**  | `PASS` | Derived commitments, chronological timeline overlap, default REJECT on exhaustion |
| **Research Data Access Guard**  | `PASS` | Role enforcement, metadata/timestamp validation, prospective data allowed |
| **Temporal Anti-Leakage**       | `PASS` | Clock hierarchy, bar close, conservative settlement boundary, perturbation invariance |
| **Versioned Cost Policy**       | `PASS` | YAML-backed assumption tiers (`BASE`, `STRESSED`, `ADVERSARIAL`), slippage model |
| **Descriptive Gap Forensics**   | `PASS` | Dynamic hour counts; 0 unsupported causal assertions |
| **2024 Holdout Strict Lock**    | `PASS` | 2024 historical holdout completely unopened and protected |
| **Zero Forced Promotion**       | `PASS` | `APPROVED_FOR_SHADOW = 0`, `APPROVED_FOR_PAPER = 0` |
| **Security Scan Zero**          | `PASS` | 0 AST hits, TRADING CAPABILITY = ZERO |
| **Full Regression Test Suite**  | `PASS` | 100% pytest suite clean pass |

---

## 2. Structural Reliability Conclusions

1. **Independent Oracle Dual-Engine Verification**:
   The independent accounting oracle in `tests/oracles/structural_accounting_oracle.py` was built with zero imports from `btceth_os`. Reconciling against 520 deterministic randomized cases spanning BTC spot-perp, ETH spot-perp, and BTC-ETH relative perp pairs yielded zero discrepancies. The $0.01 fee perturbation test verified fail-closed detection.

2. **Holdout Guard Correctness**:
   Replaced the naive regex firewall with `ResearchDataAccessGuard`. The guard validates metadata, logical hashes, and start/end timestamps, rejecting any access to the 2024 holdout (`2024-01-01` to `2024-11-30`) during research, while correctly permitting prospective forward evaluation (2025/2026).

3. **Causality and Sizing Integrity**:
   Enforced strict clock hierarchy (`source <= available <= decision <= execution <= fill`), bar-close causality, and conservative funding settlement boundary (`entry < settlement < exit`). Replaced magic multipliers with explicit `CapitalPolicy` formulas and default `REJECT` on capital exhaustion.
