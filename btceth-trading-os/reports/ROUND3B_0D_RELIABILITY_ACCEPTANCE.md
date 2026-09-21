# Research Round 3B.0D: True Market-Time Causality & Reproducible Research Partition Closure Acceptance Report

**Acceptance Status**: `ROUND3B_0D_RELIABILITY = VERIFIED`  
**Timestamp**: `2026-09-21T20:24:35.608610+00:00`  
**Tested Code Commit**: `7b764fd0be39407de5f1a6a2bc40d9756c9ca0db`  
**Tested Tree**: `57f8e1bdb26160004b0ee5cec9349c8f664cdff4`  
**Canonical Baseline Commit**: `cfa80f3aabbb75a28969701d8013f6784c35a495`  
**Acceptance Payload SHA-256**: `16d1e9ca9a3e9e1e95d9c4329a6f761bea66d98f25df5a4ab85b6e055c78c30d`  
**Trading Capability**: `ZERO`  
**2024 Holdout**: `LOCKED`  
**Approved for Shadow**: `0`  
**Approved for Paper**: `0`  
**Canonical Merge**: `NOT AUTHORIZED`  
**Strategy Discovery**: `NOT AUTHORIZED`  

---

## 1. Mechanical Reliability Gates Matrix (46 Gates)

| Gate / Invariant | Status | Verification Detail |
| :--- | :--- | :--- |
| **WIP Audit & Classification** | `PASS` | 13/13 audited independently; 0 `COPY_AS_IS` |
| **Canonical Baseline Ancestry** | `PASS` | Descends strictly from canonical HEAD `cfa80f3` |
| **WIP Safety Branch Untouched** | `PASS` | Remote `origin/btceth-round3b-wip-safety` intact at `11d6e37` |
| **Canonical Remote Untouched** | `PASS` | Remote `origin/btceth-phase1b` intact at `cfa80f3` |
| **Independent Oracle Isolation** | `PASS` | AST audit: zero `btceth_os` imports (stdlib + Decimal only) |
| **Oracle Multi-Family Campaign** | `PASS` | 850/850 exact decimal matches across 5 families |
| **Partition Materializer Committed** | `PASS` | Committed manifest and builder tool in version control |
| **Parent Artifact SHA Verified** | `PASS` | 4/4 parent Silver artifacts match cryptographic SHA-256 |
| **Physical Dataset Binding** | `PASS` | All 8 physical partitions bound to registry with verified physical SHA-256 |
| **Partition Logical Hashes Verified** | `PASS` | Independent logical content SHA-256 cryptographically verified |
| **Partition Rebuild Reproducible** | `PASS` | Sandbox rebuild reproduces exact physical and logical digests |
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
| **Bar Semantics Explicit** | `PASS` | Explicit open/close timestamps on Candle; BarObservation dataclass |
| **Signal Available At Close Time** | `PASS` | Bar close signal available strictly at close timestamp (e.g. 01:00:00) |
| **Price Observation Authentic** | `PASS` | Authentic market observation timestamp recorded |
| **No Synthetic Timestamps** | `PASS` | Zero synthetic fill timestamps for price observation |
| **First Post-Decision Observation** | `PASS` | Queries first post-decision observation with ts >= decision_ts |
| **Positive Latency Blocks Next Open** | `PASS` | Next-bar open before decision completed fails closed |
| **No Unsafe Open Fallback** | `PASS` | Missing open price raises NO_VALID_EXECUTION_OBSERVATION |
| **No Current Close For Close Signal**| `PASS` | CURRENT_BAR_CLOSE rejected in strict causal backtest |
| **Execution Delay Applied** | `PASS` | Functional K-bar delay shifts execution to bar N+K |
| **Executable Price Causality** | `PASS` | fill_price_obs_ts >= decision_ts_ns strictly enforced |
| **Next Observation Fill Clock** | `PASS` | Return clock begins strictly after execution fill |
| **Strict Causal Walk Forward** | `PASS` | Walk-forward engines route strictly through `run_causal_backtest` |
| **Capital Policy Canonical Default** | `PASS` | `PortfolioCapitalGovernor` defaults to `config/research_capital_policy_v1.yaml` |
| **Capital Policy Config Hash** | `PASS` | Canonical YAML SHA-256 cryptographically verified |
| **Promotion DB Continuity** | `PASS` | `experiments.sqlite` verified (>= 26 experiments), missing DB fails closed |
| **Zero Promotions Verified** | `PASS` | Persistent shadow=0, paper=0; runtime loading reported `NOT_IMPLEMENTED` |
| **Critical Gates Recomputed** | `PASS` | Dynamic live recomputation on live data objects |
| **Security Scan Zero** | `PASS` | 0 AST hits, TRADING CAPABILITY = ZERO |
| **Full Pytest Suite Clean Pass** | `PASS` | 100% clean pass across full test suite |
| **Acceptance Payload Hash Match** | `PASS` | Recomputed canonical JSON SHA-256 matches recorded payload hash |
| **Clean Worktree Proof** | `PASS` | Working tree clean status verified |

---

## 2. Non-Self-Referential Verification Signature

```text
canonical_payload_sha256 = 16d1e9ca9a3e9e1e95d9c4329a6f761bea66d98f25df5a4ab85b6e055c78c30d
```
