# Research Round 2 Audit: Current Research Engine & Validation Baseline

## Audit Scope & Metadata
- **Audit Date**: 2026-09-21
- **Branch**: `btceth-phase1b`
- **Audited Commit**: `e0a94eb22b92d823849c041627b87bedaf06e347`
- **Auditor**: BTCETH Trading OS Market Brain Research & Audit Engine
- **Files Inspected**:
  - `src/btceth_os/research/market_brain.py`
  - `src/btceth_os/research/features/`
  - `src/btceth_os/research/families/`
  - `src/btceth_os/research/validation/statistical.py`
  - `src/btceth_os/research/validation/robustness.py`
  - `src/btceth_os/research/validation/policy.py`
  - `src/btceth_os/research/experiment_registry.py`
  - `src/btceth_os/research/manifest.py`
  - `config/strategy_validation_policy.yaml`
  - `tools/run_strategy_research.py`
  - `reports/RESEARCH_DATA_READINESS.json`
  - `reports/STRATEGY_VALIDATION_RESULTS.json`
  - `reports/STRATEGY_REPORT_CARDS/`
  - `artifacts/research/experiments.sqlite`

---

## Findings Summary by Classification Taxonomy

| Finding ID | Classification | Component | Description | Remediation Plan |
| :--- | :--- | :--- | :--- | :--- |
| `AUD-001` | **SEMANTIC_BUG** | `market_brain.py` | `OI_EXPANSION` triggered solely by ATR expansion ratio ($>1.35$). Open interest data was not used. | Rename to `VOLATILITY_EXPANSION`. Only label `OI_EXPANSION` when verified open-interest data exists. |
| `AUD-002` | **SEMANTIC_BUG** | `market_brain.py` | `OI_UNWIND` triggered solely by ATR compression ratio ($\le 0.65$) and flat slope. | Rename to `RANGE_COMPRESSION` / `VOLATILITY_COMPRESSION`. Explicitly mark `oi_state = "UNAVAILABLE"`. |
| `AUD-003` | **SEMANTIC_BUG** | `market_brain.py` | `LIQUIDITY_STRESS` triggered only by realized volatility $\ge 0.85$ or 2h drawdown $\ge 3.5\%$. | Rename to `MARKET_STRESS`. Only label `LIQUIDITY_STRESS` if verified order book depth or spread metrics exist. |
| `AUD-004` | **SEMANTIC_BUG** | `market_brain.py` | Mutually exclusive single enum erases multi-dimensional market context (e.g. funding extreme obscures trend). | Refactor into multi-dimensional compositional `MarketState` preserving all dimensions simultaneously. |
| `AUD-005` | **IMPLEMENTATION_BUG** | `market_brain.py` | `FUNDING_EXTREME_ABS = 0.0004` commented as "40 bps / 8h". $0.0004 = 4\text{ bps}$, whereas $40\text{ bps} = 0.0040$. | Correct threshold to empirical 30 bps ($0.0030$) and implement unit-safe conversion helpers. |
| `AUD-006` | **IMPLEMENTATION_BUG** | `run_strategy_research.py` | Placeholder `pbo_val = 0.50` hardcoded during individual strategy promotion policy evaluation. | Calculate genuine CSCV PBO across each family's parameter variant search space. |
| `AUD-007` | **IMPLEMENTATION_BUG** | `statistical.py` | `compute_pbo_cscv` silently returned `0.0` on insufficient inputs, mimicking a "perfect" overfit score. | Return explicit `PBO_NOT_COMPUTABLE` / `None` with diagnostic reason code when uncomputable. |
| `AUD-008` | **STATISTICAL_WEAKNESS** | `run_strategy_research.py` | Hardcoded `var_sr = 0.25` for DSR calculation rather than computing cross-sectional trial variance. | Estimate empirical Sharpe cross-sectional variance from the actual variant search space. |
| `AUD-009` | **STATISTICAL_WEAKNESS** | `run_strategy_research.py` | Single 15-day train / 15-day test split on 1 month of data. High-frequency 1m decision horizon. | Multi-year dataset (2021–2024), rolling walk-forward validation with dynamic purging & embargo, lower-turnover horizons. |
| `AUD-010` | **STATISTICAL_WEAKNESS** | `robustness.py`, `backtest.py` | Cost model used lump-sum turnover fee without separating exchange fees, spread, slippage, and point-in-time funding. | Create audited cost policy layer with exact point-in-time funding cash flows crossing 8-hour boundaries. |
| `AUD-011` | **DOCUMENTATION_OVERCLAIM** | `statistical.py` | Docstring labeled fixed-length moving block bootstrap ($k=5$) as "stationary block bootstrap". | Accurately name function `run_moving_block_bootstrap` and implement sensitivity checks across block lengths. |
| `AUD-012` | **IMPRECISE** | `unit_rates.py` (missing) | Scattered decimal constants ($0.0001$, $0.0004$, etc.) without dedicated unit conversion utilities. | Create `src/btceth_os/research/unit_rates.py` with `bps_to_fraction`, `fraction_to_bps`, and thorough unit tests. |
| `AUD-013` | **IMPRECISE** | `strategy_validation_policy.yaml` | Policy v1.0.0 lacked multi-year consistency, regime-by-regime stability, and `NOT_COMPUTABLE` state handling. | Upgrade policy to Version 2.0.0 with explicit multi-year and statistical requirements. |
| `AUD-014` | **CORRECT** | `manifest.py` | Deterministic logical SHA-256 calculation independent of filesystem metadata is sound and verified. | Retain as canonical dataset identity standard. |
| `AUD-015` | **CORRECT** | `experiment_registry.py` | SQLite WAL persistence and permanent experiment tracking correctly recorded all 7 Round 1 failures without deletion. | Retain; preserve Round 1 records without overwriting. |
| `AUD-016` | **CORRECT** | `features/registry.py` | Point-in-time verification via future perturbation and truncated history equivalence tests is sound. | Retain and enforce for all future features. |
| `AUD-017` | **CORRECT** | `security_scan.py` | Security scanner correctly verified `TRADING CAPABILITY = ZERO` with 0 hits on forbidden mutation endpoints. | Inviolable security invariant; maintain unchanged. |
| `AUD-018` | **CORRECT** | Autopilot / Policy Gate | Zero forced promotion upheld: all 7 Round 1 strategies were rejected, and `APPROVED_FOR_PAPER = 0` was maintained. | Inviolable scientific honesty invariant; maintain in Round 2. |

---

## Preservation of Historical Records
The 7 rejected strategies from Round 1 remain permanently recorded in `artifacts/research/experiments.sqlite`:
1. `STRAT_A1_BTC_TREND_FAST`: `REJECTED`
2. `STRAT_A2_BTC_TREND_SLOW`: `REJECTED`
3. `STRAT_B1_BTC_DONCHIAN_2H`: `REJECTED`
4. `STRAT_B2_ETH_DONCHIAN_4H`: `REJECTED`
5. `STRAT_C1_BTC_MEAN_REV_1H`: `REJECTED`
6. `STRAT_D1_BTC_FUNDING_DISLOC`: `REJECTED`
7. `STRAT_G1_ETH_CROSS_ASSET_DIV`: `REJECTED`

None of these records will be altered or removed. Round 2 candidate strategies will receive new unique experiment IDs and version tags.
