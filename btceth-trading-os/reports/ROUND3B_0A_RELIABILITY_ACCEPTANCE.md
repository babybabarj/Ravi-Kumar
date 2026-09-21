# Research Round 3B.0A: Reliability Acceptance Report

**Acceptance Status**: `ROUND3B_0A_RELIABILITY = VERIFIED`  
**Timestamp**: `2026-09-21T17:48:29.228813+00:00`  
**Tested Code Commit**: `7b6a49232f57b2ba07dfc0c393bac54de4b3e6a4`  
**Tested Tree**: `271d0b4318d05cc061363824138b3ad237f3642d`  
**Canonical Baseline Commit**: `cfa80f3aabbb75a28969701d8013f6784c35a495`  
**Acceptance Payload SHA-256**: `c0d3bde03c689ef0d2ceff8328ebc37395f93f4fba25a8103184205e64c5b620`  
**Trading Capability**: `ZERO`  
**2024 Holdout**: `LOCKED`  
**Approved for Shadow**: `0`  
**Approved for Paper**: `0`  
**Canonical Merge**: `NOT AUTHORIZED`  
**Strategy Discovery**: `NOT AUTHORIZED`  

---

## 1. Mechanical Reliability Gates Matrix

| Gate / Invariant | Status | Verification Detail |
| :--- | :--- | :--- |
| **WIP Audit & Classification** | `PASS` | 13/13 WIP files audited independently; 0 `COPY_AS_IS` |
| **Canonical Baseline Ancestry** | `PASS` | Descends strictly from post-merge HEAD `cfa80f3` |
| **WIP Safety Branch Untouched** | `PASS` | Remote `origin/btceth-round3b-wip-safety` intact at `11d6e37` |
| **Canonical Remote Untouched** | `PASS` | Remote `origin/btceth-phase1b` intact at `cfa80f3` |
| **Independent Oracle Isolation** | `PASS` | AST audit: zero `btceth_os` imports (stdlib + Decimal only) |
| **Oracle Multi-Family Campaign** | `PASS` | 850/850 exact decimal matches across 5 families; 5-dim mutation caught |
| **Temporal Integration Pass** | `PASS` | 11 real features perturbation-invariant; typed funding signals verified |
| **Portfolio Capital Governor** | `PASS` | YAML policy loaded, input validation, duplicate/unknown/chronology fail-closed |
| **Data Guard & Ledger Integrity** | `PASS` | Precedence invariant enforced, zero unlock capability, 0 holdout accesses |
| **Versioned Execution Cost Policy** | `PASS` | YAML tiers (`BASE`, `STRESSED`, `ADVERSARIAL`), parameterized slippage |
| **Descriptive Gap Forensics** | `PASS` | Dynamic counts; zero unsupported causal assertions |
| **2024 Holdout Strict Lock** | `PASS` | 2024 holdout strictly protected in manifest and guard |
| **Zero Forced Promotion Derived** | `PASS` | Mechanically derived: `paper_count == 0`, `shadow_count == 0` |
| **Security Scan Zero** | `PASS` | 0 AST hits, TRADING CAPABILITY = ZERO |
| **Full Pytest Regression Suite** | `PASS` | 100% test suite clean pass |
| **Clean Worktree Proof** | `PASS` | Working tree clean status verified |

---

## 2. Non-Self-Referential Verification Signature

```text
canonical_payload_sha256 = c0d3bde03c689ef0d2ceff8328ebc37395f93f4fba25a8103184205e64c5b620
```
