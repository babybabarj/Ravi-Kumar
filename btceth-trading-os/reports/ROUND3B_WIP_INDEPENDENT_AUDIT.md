# Research Round 3B.0 — Independent WIP Audit Report

**Date**: `2026-09-21`  
**Audited Reference Commit**: `11d6e370db0d27cd635528a3c530286b28c60416` (`origin/btceth-round3b-wip-safety`)  
**Canonical Base Commit**: `cfa80f3aabbb75a28969701d8013f6784c35a495` (`origin/btceth-phase1b`)  
**Status**: `COMPLETED`  

---

## 1. Audit Methodology & Classifications

The 13 files preserved in the interrupted Round 3B WIP safety branch have been audited independently against first principles, mathematical rigor, and canonical system constraints.

Each file is assigned one of four mandatory dispositions:
- **`REUSE_CONCEPT_ONLY`**: The underlying research or forensic concept is sound, but the implementation is rejected and rewritten from scratch.
- **`REIMPLEMENT`**: The functionality is necessary, but the WIP code suffers from design defects, coupling, magic numbers, or lack of generality.
- **`ARCHIVE_ONLY`**: Historical diagnostic artifacts preserved solely for provenance.
- **`REJECT`**: Flawed implementation that violates core architectural invariants.

### Disposition Summary
- **REUSE_CONCEPT_ONLY**: 1 file
- **REIMPLEMENT**: 7 files
- **ARCHIVE_ONLY**: 4 files
- **REJECT**: 1 file
- **COPY_AS_IS**: **0 files**

---

## 2. File-by-File Audit Findings

### 1. `reports/REPOSITORY_STATE_REMEDIATION_PRECHECK.json`
- **Original Purpose**: Precheck diagnostics capturing timeline divergence before Phase 1B.2 remediation.
- **Classification**: **`ARCHIVE_ONLY`**
- **Rationale**: Represents historical state diagnostics. Fully superseded by `CANONICAL_POST_MERGE_ACCEPTANCE.json`.

### 2. `reports/REPOSITORY_STATE_REMEDIATION_PRECHECK.md`
- **Original Purpose**: Explanatory companion to the remediation precheck.
- **Classification**: **`ARCHIVE_ONLY`**
- **Rationale**: Historical artifact preserved for provenance.

### 3. `reports/RESEARCH_ROUND3B_GAP_FORENSICS.md`
- **Original Purpose**: Audit of 440 invalid hours in Dataset v3.1.0.
- **Classification**: **`REUSE_CONCEPT_ONLY`**
- **Defects in WIP**: Made unsupported causal claims ("server load caused drops", "FTX collapse", "Binance maintenance").
- **Replacement**: Reimplemented as `reports/ROUND3B_GAP_FORENSICS.md` using strictly descriptive terms (`OBSERVED`, `ASSOCIATED_WITH`).

### 4. `reports/ROUND3B_ACCOUNTING_RECONCILIATION.json`
- **Original Purpose**: Recorded 50/50 exact accounting matches.
- **Classification**: **`ARCHIVE_ONLY`**
- **Defects in WIP**: Small sample size (50 cases); only covered BTC spot/perp; used a test oracle coupled to production code.
- **Replacement**: Superseded by `ROUND3B_ACCOUNTING_ORACLE_V2.json` with 500+ randomized property-style cases across 5 asset/structure variants.

### 5. `reports/ROUND3B_ACCOUNTING_RECONCILIATION.md`
- **Original Purpose**: Human-readable accounting reconciliation report.
- **Classification**: **`ARCHIVE_ONLY`**
- **Replacement**: Superseded by `ROUND3B_ACCOUNTING_ORACLE_V2.md`.

### 6. `src/btceth_os/research/holdout_firewall.py`
- **Original Purpose**: Firewall to block 2024 holdout access.
- **Classification**: **`REJECT`**
- **Critical Defects**:
  1. Blocked all timestamps $\ge$ 2024-01-01, incorrectly prohibiting future 2025/2026 prospective data.
  2. Relied purely on filename regex matching `"2024"`; renaming a holdout file bypassed the firewall entirely.
- **Replacement**: `ResearchDataAccessGuard` implementing explicit dataset roles (`DEVELOPMENT`, `VALIDATION`, `LOCKED_HOLDOUT`, `PROSPECTIVE_FORWARD`, `SHADOW`, `PAPER`), manifest/hash checks, and bounded holdout window (2024-01-01 to 2024-11-30).

### 7. `src/btceth_os/research/structural/adversarial_cost.py`
- **Original Purpose**: Execution cost tiers and volatility-scaled slippage evaluation.
- **Classification**: **`REIMPLEMENT`**
- **Critical Defects**: Hardcoded magic numbers (`1.75` for spot/perp, `0.75` for relative pair); cost tiers hardcoded in python source instead of versioned configuration.
- **Replacement**: Versioned YAML policy `config/research_execution_cost_policy_v1.yaml` with explicit research assumption labels (`BASE_RESEARCH_ASSUMPTION`, `STRESSED_RESEARCH_ASSUMPTION`, `ADVERSARIAL_RESEARCH_ASSUMPTION`) and parameterized `SCENARIO_SLIPPAGE_MODEL`.

### 8. `src/btceth_os/research/structural/portfolio_equity.py`
- **Original Purpose**: Portfolio equity tracking and multi-strategy capital allocation.
- **Classification**: **`REIMPLEMENT`**
- **Defects in WIP**: Ad-hoc `allocate_multi_strategy_capital` function without explicit capital policy object; risk of silent resizing under scale-down.
- **Replacement**: `PortfolioCapitalGovernor` backed by `CapitalPolicy` with default `REJECT` on exhaustion and `SCALE_DOWN = DISABLED`.

### 9. `tests/test_holdout_firewall.py`
- **Original Purpose**: Tests for holdout firewall.
- **Classification**: **`REIMPLEMENT`**
- **Defects in WIP**: Tested insecure regex and global $\ge$ 2024 block.
- **Replacement**: `tests/test_holdout_guard.py` verifying renamed holdout files, manifest tamper, timestamp ranges, and positive allowance of 2025/2026 prospective data.

### 10. `tests/test_round3b_concurrency_adversary.py`
- **Original Purpose**: Tests capital exhaustion across concurrent strategies.
- **Classification**: **`REIMPLEMENT`**
- **Defects in WIP**: Lacked chronological event timelines; relied on arbitrary sizing multipliers.
- **Replacement**: `tests/test_capital_governor.py` exercising chronological overlap, capital release upon close, and simultaneous request arbitration.

### 11. `tests/test_round3b_temporal_causality.py`
- **Original Purpose**: Temporal causality, bar-close, and settlement boundary tests.
- **Classification**: **`REIMPLEMENT`**
- **Defects in WIP**: Assumed ambiguous exact-timestamp funding settlement ($T \le \text{settlement} \le T$); tested mock toy classes instead of real production code.
- **Replacement**: Tests using production feature functions, future row perturbation, strict bar-close causality, and conservative settlement boundary (`entry < settlement < exit`).

### 12. `tools/accounting_oracle.py`
- **Original Purpose**: Independent first-principles accounting oracle.
- **Classification**: **`REIMPLEMENT`**
- **Critical Defect**: Imported production engine classes (`MultiLegTradeEpisode`, `DetailedCostPolicy`, `PortfolioEquityEngine`), violating oracle independence and risking tautological agreement.
- **Replacement**: `tests/oracles/structural_accounting_oracle.py` using **strictly standard library and `Decimal` only** (0 `btceth_os` imports).

### 13. `tools/analyze_source_gaps.py`
- **Original Purpose**: Parse Dataset v3.1.0 and identify missing hours.
- **Classification**: **`REIMPLEMENT`**
- **Defects in WIP**: Hardcoded title `"440 INVALID HOURS"`; printed unsupported causal speculation; mixed float and Decimal types in variance calculations.
- **Replacement**: `tools/analyze_source_gaps.py` dynamically computing metrics with strict type discipline and purely descriptive language.
