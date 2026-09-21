# Research Round 3B.0B: Final Reliability Binding & Runtime Integration Acceptance Report

**Acceptance Status**: `ROUND3B_0B_RELIABILITY = VERIFIED`  
**Timestamp**: `2026-09-21T18:25:19.486245+00:00`  
**Tested Code Commit**: `1fa44ec685f5dc2441e2a5634e9c6b5c87f05c68`  
**Tested Tree**: `e17edf9c0ace4b0305dcdc1f2f07d0d9a5500abe`  
**Canonical Baseline Commit**: `cfa80f3aabbb75a28969701d8013f6784c35a495`  
**Acceptance Payload SHA-256**: `3634754e3a1acd68a61b7a93857199dde6e3902500466ce3f4d0f6b59fe19f02`  
**Trading Capability**: `ZERO`  
**2024 Holdout**: `LOCKED`  
**Approved for Shadow**: `0`  
**Approved for Paper**: `0`  
**Canonical Merge**: `NOT AUTHORIZED`  
**Strategy Discovery**: `NOT AUTHORIZED`  

---

## 1. Mechanical Reliability Gates Matrix (24 Gates + Closure Gates)

| Gate / Invariant | Status | Verification Detail |
| :--- | :--- | :--- |
| **WIP Audit & Classification** | `PASS` | 13/13 audited independently; 0 `COPY_AS_IS` |
| **Canonical Baseline Ancestry** | `PASS` | Descends strictly from canonical HEAD `cfa80f3` |
| **WIP Safety Branch Untouched** | `PASS` | Remote `origin/btceth-round3b-wip-safety` intact at `11d6e37` |
| **Canonical Remote Untouched** | `PASS` | Remote `origin/btceth-phase1b` intact at `cfa80f3` |
| **Independent Oracle Isolation** | `PASS` | AST audit: zero `btceth_os` imports (stdlib + Decimal only) |
| **Oracle Multi-Family Campaign** | `PASS` | 850/850 exact decimal matches across 5 families; 5-dim mutation caught |
| **Physical Dataset Binding** | `PASS` | Physical files bound to registry entries; physical SHA-256 cryptographically verified |
| **Registry Immutability** | `PASS` | `CANONICAL_DATASET_REGISTRY` wrapped in `MappingProxyType`; mutation raises `TypeError` |
| **No Placeholder Hashes** | `PASS` | All fake digests (`holdout_2024_locked_sha256`) eliminated |
| **Holdout Unregistered for Read** | `PASS` | 2024 holdout status strictly `LOCKED_UNREGISTERED_FOR_READ`; no readable hash |
| **Dataset Identity Required** | `PASS` | Permissive default dataset ID eliminated; missing ID raises `DATASET_IDENTITY_REQUIRED` |
| **Row-Level Timestamp Bounds** | `PASS` | Parquet row group stats / values inspected; 2024 rows trigger `HOLDOUT_FIREWALL_VIOLATION` |
| **Registry Authoritative** | `PASS` | Registry truth authoritative; metadata conflict raises `METADATA_REGISTRY_MISMATCH` |
| **Unknown Operations Fail Closed** | `PASS` | Unrecognized operations fail closed with `UNKNOWN_RESEARCH_OPERATION` |
| **Prospective Whitelist** | `PASS` | Strict whitelist (`PROSPECTIVE_VALIDATION`, `SHADOW`, `PAPER`); `FINAL_HOLDOUT_AUDIT` blocked |
| **Tamper-Evident Hash Chain** | `PASS` | Pre-append integrity check active; 0 holdout accesses; hash chain continuous |
| **Real Causal Backtest Engine** | `PASS` | `run_causal_backtest()` enforces `TemporalEventContract` on all simulated fills |
| **Strategy Funding Boundary** | `PASS` | Only causal typed funding signals permitted; unsettled/raw funding blocked |
| **Capital Policy Canonical Default** | `PASS` | `PortfolioCapitalGovernor` defaults to `config/research_capital_policy_v1.yaml` |
| **Strict Schema & Parameter Bounds** | `PASS` | Mandatory fields required; bounds enforced; `scale_down_enabled == False` |
| **Capital Governor Decimal Validation**| `PASS` | `close_episode()` rejects non-Decimal, NaN, Inf |
| **Zero Promotions Verified** | `PASS` | Derived from SQLite and runtime registry: approved shadow=0, approved paper=0 |
| **Security Scan Zero** | `PASS` | 0 AST hits, TRADING CAPABILITY = ZERO |
| **Full Pytest Suite Clean Pass** | `PASS` | 100% clean pass across full test suite |
| **Acceptance Payload Hash Match** | `PASS` | Recomputed canonical JSON SHA-256 matches recorded payload hash |
| **Clean Worktree Proof** | `PASS` | Working tree clean status verified |

---

## 2. Non-Self-Referential Verification Signature

```text
canonical_payload_sha256 = 3634754e3a1acd68a61b7a93857199dde6e3902500466ce3f4d0f6b59fe19f02
```
