# BTCETH TRADING OS: RESEARCH ROUND 3B.0F RELIABILITY ACCEPTANCE REPORT

**Acceptance Status:** `ROUND3B_0F_RELIABILITY = VERIFIED`
**Timestamp UTC:** `2026-09-22T20:07:30.788888+00:00`
**Work Branch:** `btceth-round3b-reliability`
**Head Commit SHA:** `136f4a85dc317d526b7613bf24d88fce7f5d925c`
**Tree SHA:** `add3a563ae238c4b0166112759113b90ade77aaf`
**Canonical Baseline:** `cfa80f3aabbb75a28969701d8013f6784c35a495` (Untouched: `True`)
**Acceptance Payload SHA-256:** `1e0e6e4f070e134134d3a02751d8638103ee61af907005eca525951006f4f189`

## Executive Summary

Round 3B.0F permanently closes the remaining execution-semantic defects discovered during review of Round 3B.0E:
- **Execution Window Integrity**: Enforced mandatory upper time bound on regular execution observations (`execution_window_end_ts_ns = next_bar_close_ts_ns`). Observations after the valuation close are rejected with `NO_VALID_EXECUTION_OBSERVATION_IN_WINDOW`. Return-timeline causality order (`signal_close_ts <= fill_obs_ts <= valuation_close_ts`) is strictly enforced.
- **Strict Instrument Identity**: Eliminated fail-open matching. Missing expected instrument raises `EXECUTION_INSTRUMENT_IDENTITY_REQUIRED`; missing observation instrument raises `EXECUTION_OBSERVATION_INSTRUMENT_REQUIRED`. Mismatched instrument, market type, or venue are rejected.
- **Guarded Dataset Loader Propagation**: `load_guarded_kline_candles()` populates `instrument_id`, `market_type`, `venue`, and `dataset_id` from canonical metadata onto every emitted `Candle`.
- **Dynamic Market Type Resolution**: Eliminated hardcoded USD-M perp assumptions in `run_causal_backtest()`; rejects incompatible market type pairings with `MARKET_TYPE_MISMATCH`.
- **Strict Executable Touch Pricing**: In `ExecutionMode.BID_ASK_TOUCH`, BUY requires `ask` (`EXECUTABLE_ASK_MISSING`) and SELL requires `bid` (`EXECUTABLE_BID_MISSING`). Generic price fallback inside touch mode is blocked. In `ExecutionMode.TRADE_PRINT`, requires `trade_price` (`EXECUTABLE_TRADE_PRICE_MISSING`). Added explicit `ExecutionMode.GENERIC_PRICE`.
- **Regression Proof**: All Round 3B.0E order-arrival causality, terminal mark-to-fill settlement, and Round 3B.0D research partition boundaries remain verified and unchanged.

## Invariant Summary

| Invariant | Status | Verification Detail |
|---|---|---|
| **Trading Capability** | `ZERO` | Static AST and security scanner confirm 0 mutations/orders |
| **2024 Holdout** | `LOCKED` | 0 accesses allowed, 0 reads performed |
| **Paper / Shadow Promotions** | `0` | APPROVED_FOR_PAPER = 0, APPROVED_FOR_SHADOW = 0 |
| **Canonical Baseline** | `UNTOUCHED` | Ancestry strictly maintained from `cfa80f3aabbb75a28969701d8013f6784c35a495` |
| **Round 3B.0D Partitions** | `UNMODIFIED` | All 8 physical and logical partition SHA-256 digests identical |
| **Round 3B.0E Regressions** | `PASS` | Order-arrival causality and terminal settlement verified |

## Mechanical Verification Gates

| Gate Identifier | Result | Verification Detail |
|---|---|---|
| `2024_HOLDOUT_LOCKED` | `PASS` | Derived dynamically from live mechanical checks |
| `ACCEPTANCE_PAYLOAD_HASH_MATCH` | `PASS` | Derived dynamically from live mechanical checks |
| `BAR_OPEN_CLOSE_SEMANTICS_EXPLICIT` | `PASS` | Derived dynamically from live mechanical checks |
| `CANONICAL_REMOTE_UNTOUCHED` | `PASS` | Derived dynamically from live mechanical checks |
| `CAPITAL_POLICY_CANONICAL_YAML_DEFAULT` | `PASS` | Derived dynamically from live mechanical checks |
| `CAPITAL_POLICY_CONFIG_HASH_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `CLEAN_WORKTREE_PROOF` | `PASS` | Derived dynamically from live mechanical checks |
| `CRITICAL_GATES_ACTUALLY_RECOMPUTED` | `PASS` | Derived dynamically from live mechanical checks |
| `DATASET_IDENTITY_REQUIRED_ENFORCED` | `PASS` | Derived dynamically from live mechanical checks |
| `DATASET_INSTRUMENT_PROPAGATION` | `PASS` | Derived dynamically from live mechanical checks |
| `DEV_MAX_TIMESTAMP_PRE_2023` | `PASS` | Derived dynamically from live mechanical checks |
| `DEV_VALIDATION_PHYSICAL_SEPARATION` | `PASS` | Derived dynamically from live mechanical checks |
| `DUPLICATE_TIMESTAMP_POLICY_ENFORCED` | `PASS` | Derived dynamically from live mechanical checks |
| `EXECUTABLE_PRICE_CAUSALITY_ENFORCED` | `PASS` | Derived dynamically from live mechanical checks |
| `EXECUTION_DELAY_ACTUALLY_APPLIED` | `PASS` | Derived dynamically from live mechanical checks |
| `EXECUTION_DELAY_WINDOW_ALIGNED` | `PASS` | Derived dynamically from live mechanical checks |
| `EXECUTION_ELIGIBILITY_AFTER_EXCHANGE_ARRIVAL` | `PASS` | Derived dynamically from live mechanical checks |
| `EXECUTION_STREAM_MONOTONIC` | `PASS` | Derived dynamically from live mechanical checks |
| `EXECUTION_WINDOW_UPPER_BOUND` | `PASS` | Derived dynamically from live mechanical checks |
| `EXPECTED_INSTRUMENT_ID_REQUIRED` | `PASS` | Derived dynamically from live mechanical checks |
| `FILL_LATENCY_SEMANTICS_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `FULL_PYTEST_PASS` | `PASS` | Derived dynamically from live mechanical checks |
| `GENERIC_PRICE_NO_STRICT_TOUCH_FALLBACK` | `PASS` | Derived dynamically from live mechanical checks |
| `HOLDOUT_2024_LOCKED` | `PASS` | Derived dynamically from live mechanical checks |
| `HOLDOUT_UNREGISTERED_FOR_READ_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `LEDGER_PROCESS_SAFE_CONCURRENCY` | `PASS` | Derived dynamically from live mechanical checks |
| `MARKET_TYPE_NOT_SILENTLY_HARDCODED` | `PASS` | Derived dynamically from live mechanical checks |
| `NEXT_OBSERVATION_FILL_CLOCK` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_AGGREGATE_DIRECT_RESEARCH_READ` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_CURRENT_CLOSE_AFTER_CLOSE_SIGNAL` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_HARDCODED_EXECUTION_AUDIT_PASS` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_PLACEHOLDER_HASHES_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_PUBLIC_REGISTRY_TRUST_OVERRIDE` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_SYNTHETIC_TIMESTAMP_FOR_FUTURE_PRICE` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_UNSAFE_OPEN_FALLBACK` | `PASS` | Derived dynamically from live mechanical checks |
| `OBSERVATION_INSTRUMENT_ID_REQUIRED` | `PASS` | Derived dynamically from live mechanical checks |
| `ORACLE_AST_ISOLATED` | `PASS` | Derived dynamically from live mechanical checks |
| `ORACLE_MULTI_FAMILY_CAMPAIGN_PASS` | `PASS` | Derived dynamically from live mechanical checks |
| `ORDER_ARRIVAL_TIME_EXPLICIT` | `PASS` | Derived dynamically from live mechanical checks |
| `PARENT_ARTIFACT_SHA_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `PARTITION_LOGICAL_HASHES_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `PARTITION_MATERIALIZER_COMMITTED` | `PASS` | Derived dynamically from live mechanical checks |
| `PHYSICAL_DATASET_BINDING_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `POSITIVE_LATENCY_BLOCKS_NEXT_OPEN` | `PASS` | Derived dynamically from live mechanical checks |
| `POST_VALUATION_OBSERVATION_REJECTED` | `PASS` | Derived dynamically from live mechanical checks |
| `PRE_ARRIVAL_OBSERVATION_REJECTED` | `PASS` | Derived dynamically from live mechanical checks |
| `PRICE_OBSERVATION_TIMESTAMP_AUTHENTIC` | `PASS` | Derived dynamically from live mechanical checks |
| `PROMOTION_DB_REQUIRED_AND_CONTINUITY` | `PASS` | Derived dynamically from live mechanical checks |
| `REGISTRY_IMMUTABILITY_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `RETURN_TIMELINE_CAUSALITY` | `PASS` | Derived dynamically from live mechanical checks |
| `ROLE_BOUNDARY_CONTAMINATION_GUARD` | `PASS` | Derived dynamically from live mechanical checks |
| `ROUND3B_0D_PARTITION_REGRESSION` | `PASS` | Derived dynamically from live mechanical checks |
| `ROUND3B_0E_ORDER_ARRIVAL_REGRESSION` | `PASS` | Derived dynamically from live mechanical checks |
| `ROUND3B_0E_TERMINAL_REGRESSION` | `PASS` | Derived dynamically from live mechanical checks |
| `ROW_LEVEL_TIMESTAMP_CORROBORATION_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `SAME_INSTRUMENT_EXECUTION_ENFORCED` | `PASS` | Derived dynamically from live mechanical checks |
| `SAME_MARKET_TYPE_EXECUTION_ENFORCED` | `PASS` | Derived dynamically from live mechanical checks |
| `SECURITY_SCAN_ZERO` | `PASS` | Derived dynamically from live mechanical checks |
| `SIDE_AWARE_EXECUTABLE_PRICE` | `PASS` | Derived dynamically from live mechanical checks |
| `SIGNAL_CLOSE_AVAILABLE_AT_CLOSE_TIME` | `PASS` | Derived dynamically from live mechanical checks |
| `STRICT_BUY_REQUIRES_ASK` | `PASS` | Derived dynamically from live mechanical checks |
| `STRICT_CAUSAL_WALK_FORWARD` | `PASS` | Derived dynamically from live mechanical checks |
| `STRICT_SELL_REQUIRES_BID` | `PASS` | Derived dynamically from live mechanical checks |
| `TAMPER_EVIDENT_HASH_CHAIN_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `TERMINAL_DRAWDOWN_INCLUDED` | `PASS` | Derived dynamically from live mechanical checks |
| `TERMINAL_EXIT_COST_APPLIED_ONCE` | `PASS` | Derived dynamically from live mechanical checks |
| `TERMINAL_LONG_GAIN_FIXTURE` | `PASS` | Derived dynamically from live mechanical checks |
| `TERMINAL_LONG_LOSS_FIXTURE` | `PASS` | Derived dynamically from live mechanical checks |
| `TERMINAL_MARK_TO_FILL_PNL_LONG` | `PASS` | Derived dynamically from live mechanical checks |
| `TERMINAL_MARK_TO_FILL_PNL_SHORT` | `PASS` | Derived dynamically from live mechanical checks |
| `TERMINAL_MISSING_OBSERVATION_FAILS_CLOSED` | `PASS` | Derived dynamically from live mechanical checks |
| `TERMINAL_REUSES_EXECUTION_SELECTOR` | `PASS` | Derived dynamically from live mechanical checks |
| `TERMINAL_SHORT_GAIN_FIXTURE` | `PASS` | Derived dynamically from live mechanical checks |
| `TERMINAL_SHORT_LOSS_FIXTURE` | `PASS` | Derived dynamically from live mechanical checks |
| `TERMINAL_SYNTHETIC_PRICE_FALLBACK_BLOCKED` | `PASS` | Derived dynamically from live mechanical checks |
| `TEST_WORKTREE_CLEAN` | `PASS` | Derived dynamically from live mechanical checks |
| `TRADE_PRINT_REQUIRES_TRADE_PRICE` | `PASS` | Derived dynamically from live mechanical checks |
| `VALIDATION_MAX_TIMESTAMP_PRE_2024` | `PASS` | Derived dynamically from live mechanical checks |
| `VALIDATION_MIN_TIMESTAMP_2023` | `PASS` | Derived dynamically from live mechanical checks |
| `WIP_SAFETY_REMOTE_UNTOUCHED` | `PASS` | Derived dynamically from live mechanical checks |
| `ZERO_PROMOTIONS` | `PASS` | Derived dynamically from live mechanical checks |
| `ZERO_PROMOTIONS_PERSISTENT_AND_RUNTIME` | `PASS` | Derived dynamically from live mechanical checks |

## Superseding Notice

```text
ROUND3B_0D_DATA_INTEGRITY = VERIFIED
ROUND3B_0D_RESEARCH_SPLIT = VERIFIED
ROUND3B_0D_BAR_TIME_CAUSALITY = VERIFIED
ROUND3B_0E_EXECUTION_ARRIVAL_CAUSALITY = VERIFIED
ROUND3B_0E_TERMINAL_SETTLEMENT = VERIFIED
ROUND3B_0F_EXECUTION_WINDOW_INTEGRITY = VERIFIED
ROUND3B_0F_INSTRUMENT_IDENTITY = VERIFIED
ROUND3B_0F_STRICT_TOUCH_PRICING = VERIFIED
ROUND3B_0F_OVERALL = VERIFIED
```

## Next Steps

```text
CANONICAL MERGE = NOT AUTHORIZED
STRATEGY DISCOVERY = NOT AUTHORIZED
NEXT = INDEPENDENT REVIEW FOR RELIABILITY MERGE AUTHORIZATION
```

