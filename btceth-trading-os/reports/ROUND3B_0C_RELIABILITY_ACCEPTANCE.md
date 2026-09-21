# Research Round 3B.0C: Research-Split Integrity & Executable-Price Causality Acceptance Report

**Acceptance Status**: `ROUND3B_0C_RELIABILITY = VERIFIED`  
**Timestamp**: `2026-09-21T19:37:22.861843+00:00`  
**Tested Code Commit**: `29a3ebd2c99aff7b91ec63f6a9d167b489ad1174`  
**Tested Tree**: `be2b3463d6a4f18098cc976dab7fcd3d97876b5e`  
**Canonical Baseline Commit**: `cfa80f3aabbb75a28969701d8013f6784c35a495`  
**Acceptance Payload SHA-256**: `29ddaf0862a9ab6cdceb4fe95a85060adb96f12f98c51eab8b8af79192e6d16a`  
**Trading Capability**: `ZERO`  
**2024 Holdout**: `LOCKED`  
**Approved for Shadow**: `0`  
**Approved for Paper**: `0`  
**Canonical Merge**: `NOT AUTHORIZED`  
**Strategy Discovery**: `NOT AUTHORIZED`  

---

## 1. Mechanical Reliability Gates Matrix (29 Gates + Closure Gates)

| Gate / Invariant | Status | Verification Detail |
| :--- | :--- | :--- |
| **WIP Audit & Classification** | `PASS` | 13/13 audited independently; 0 `COPY_AS_IS` |
| **Canonical Baseline Ancestry** | `PASS` | Descends strictly from canonical HEAD `cfa80f3` |
| **WIP Safety Branch Untouched** | `PASS` | Remote `origin/btceth-round3b-wip-safety` intact at `11d6e37` |
| **Canonical Remote Untouched** | `PASS` | Remote `origin/btceth-phase1b` intact at `cfa80f3` |
| **Independent Oracle Isolation** | `PASS` | AST audit: zero `btceth_os` imports (stdlib + Decimal only) |
| **Oracle Multi-Family Campaign** | `PASS` | 850/850 exact decimal matches across 5 families |
| **Physical Dataset Binding** | `PASS` | All 8 physical partitions bound to registry with verified physical SHA-256 |
| **Dev / Val Physical Separation** | `PASS` | DEV (2020-2022) and VAL (2023) physically separated with distinct SHA-256 digests |
| **Dev Max Timestamp Pre-2023** | `PASS` | All DEV partitions strictly precede 2023-01-01T00:00:00Z |
| **Val Min Timestamp 2023** | `PASS` | All VAL partitions strictly on or after 2023-01-01T00:00:00Z |
| **Val Max Timestamp Pre-2024** | `PASS` | All VAL partitions strictly precede 2024-01-01T00:00:00Z |
| **No Aggregate Direct Read** | `PASS` | Composite datasets marked `NOT_DIRECTLY_READABLE`; direct load fails closed |
| **Role Boundary Contamination Guard** | `PASS` | Cross-role data access raises `ROLE_BOUNDARY_VIOLATION` |
| **Registry Immutability** | `PASS` | `CANONICAL_DATASET_REGISTRY` wrapped in `MappingProxyType`; mutation raises `TypeError` |
| **No Public Registry Override** | `PASS` | Public signatures do not accept caller-injected `registry` parameter |
| **No Placeholder Hashes** | `PASS` | No mock or placeholder digests in canonical registry |
| **Holdout Unregistered for Read** | `PASS` | 2024 holdout status strictly `LOCKED_UNREGISTERED_FOR_READ` |
| **Dataset Identity Required** | `PASS` | Missing dataset ID raises `DATASET_IDENTITY_REQUIRED` |
| **Row-Level Timestamp Corroboration** | `PASS` | Parquet row group stats / values verified; 2024 rows blocked |
| **Tamper-Evident Hash Chain** | `PASS` | Pre-append integrity active; 0 holdout accesses; hash chain intact |
| **Ledger Process Safety** | `PASS` | Multi-process concurrent logging protected by `fcntl.flock` file locking |
| **Executable Price Causality** | `PASS` | `run_causal_backtest` verifies `fill_price_observation_ts_ns >= decision_ts_ns` |
| **Next Observation Fill Clock** | `PASS` | Execution occurs at bar N+1 open; return clock begins strictly after execution |
| **Strict Causal Walk Forward** | `PASS` | Walk-forward engines route strictly through `run_causal_backtest` |
| **Capital Policy Canonical Default** | `PASS` | `PortfolioCapitalGovernor` defaults to `config/research_capital_policy_v1.yaml` |
| **Capital Policy Config Hash** | `PASS` | Canonical YAML SHA-256 cryptographically verified |
| **Promotion DB Continuity** | `PASS` | `experiments.sqlite` verified (>= 26 experiments), missing DB fails closed |
| **Zero Promotions Verified** | `PASS` | Persistent shadow=0, paper=0; runtime loading reported `NOT_IMPLEMENTED` |
| **Security Scan Zero** | `PASS` | 0 AST hits, TRADING CAPABILITY = ZERO |
| **Full Pytest Suite Clean Pass** | `PASS` | 100% clean pass across full test suite |
| **Acceptance Payload Hash Match** | `PASS` | Recomputed canonical JSON SHA-256 matches recorded payload hash |
| **Clean Worktree Proof** | `PASS` | Working tree clean status verified |

---

## 2. Non-Self-Referential Verification Signature

```text
canonical_payload_sha256 = 29ddaf0862a9ab6cdceb4fe95a85060adb96f12f98c51eab8b8af79192e6d16a
```
