# BTCETH TRADING OS: RESEARCH ROUND 3B.0I RELIABILITY ACCEPTANCE REPORT

**Acceptance Status:** `ROUND3B_0I_RELIABILITY = VERIFIED`
**Timestamp UTC:** `2026-09-23T06:32:38.204488+00:00`
**Work Branch:** `btceth-round3b-reliability`
**Head Commit SHA:** `4612bb0e6cdc64b9f28a352d213305e7ffb692a2`
**Tree SHA:** `e4859f17d25d31d12f31e2116c3c740259e244f1`
**Canonical Baseline:** `cfa80f3aabbb75a28969701d8013f6784c35a495` (Untouched: `True`)
**Acceptance Payload SHA-256:** `5bf089f4a14a888089cb610aae58cd0eed15c09340bbeff7856da22d83dd6346`
**Total Mechanical Gates:** `140` (Passed: `True`)

## Safety Boundaries
- `APPROVED_FOR_SHADOW = 0`
- `APPROVED_FOR_PAPER = 0`
- `TRADING CAPABILITY = ZERO`
- `2024 HOLDOUT = LOCKED`

## Summary of Closed Defects (3B.0I)
- **Cross-Series Capital Isolation**: BTC isolated vs BTC after ETH vs BTC interleaved matches to exact Decimal equality.
- **Run-Order Independence**: Interleaved execution produces invariant outputs across all metrics.
- **Repeated Run Determinism**: Consecutive runs in same Python process produce bit-for-bit identical results.
- **Caller Input Immutability**: Zero in-place mutation of caller candles, positions, costs, or lookbacks.
- **Failed-Run State Atomicity**: Failed executions do not corrupt process state; subsequent valid runs match clean baseline.
- **Capital Accounting Identities**: Exact mathematical accounting verified across 11 hand-verifiable fixtures.
- **Position Reversal Accounting**: Transitions +1 -> -1 and -1 -> +1 charge 2 units turnover fee with side-aware execution.
- **No Fee / Slippage Double Count**: Fees charged once per turnover event, slippage charged once per fill.
- **Walk-Forward Capital Reset**: Candidates evaluated with fresh starting capital.
- **Lookback Evaluation Order Independence**: Candidate permutations produce invariant lookback selection and metrics.
- **Decimal Accounting Integrity**: All internal equity/cost/pnl paths strictly Decimal.
- **Experiment Identity Binding**: Instrument and dataset partition explicitly bound into experiment records and hashes.
- **Single-Leg Architecture Enforcement**: Multi-asset mixing fails closed before P&L calculation.

## Mechanical Gates Verification Results
| Gate Name | Status | Description |
| :--- | :---: | :--- |
| `ANONYMOUS_PRIMARY_BACKTEST_BLOCKED` | `PASS` | Mechanical verification gate |
| `ANONYMOUS_WALK_FORWARD_BLOCKED` | `PASS` | Mechanical verification gate |
| `BAR_OPEN_CLOSE_SEMANTICS_EXPLICIT` | `PASS` | Mechanical verification gate |
| `BTC_AFTER_ETH_ISOLATION` | `PASS` | Mechanical verification gate |
| `BTC_ETH_VALUATION_CONTAMINATION_BLOCKED` | `PASS` | Mechanical verification gate |
| `CANONICAL_BASELINE_ANCESTRY_VALID` | `PASS` | Mechanical verification gate |
| `CANONICAL_REGISTRY_IDENTITY_EXPLICIT` | `PASS` | Mechanical verification gate |
| `CANONICAL_REMOTE_UNTOUCHED` | `PASS` | Mechanical verification gate |
| `CAPITAL_ACCOUNTING_IDENTITY` | `PASS` | Mechanical verification gate |
| `CAPITAL_POLICY_CANONICAL_YAML_DEFAULT` | `PASS` | Mechanical verification gate |
| `CAPITAL_POLICY_CONFIG_HASH_VERIFIED` | `PASS` | Mechanical verification gate |
| `COST_OBJECT_IMMUTABILITY` | `PASS` | Mechanical verification gate |
| `CROSS_SERIES_CAPITAL_ISOLATION` | `PASS` | Mechanical verification gate |
| `DATASET_INSTRUMENT_PROPAGATION` | `PASS` | Mechanical verification gate |
| `DECIMAL_ACCOUNTING_INTEGRITY` | `PASS` | Mechanical verification gate |
| `DETERMINISTIC_RESULT_REPRODUCIBILITY` | `PASS` | Mechanical verification gate |
| `DEV_MAX_TIMESTAMP_PRE_2023` | `PASS` | Mechanical verification gate |
| `DEV_VALIDATION_PHYSICAL_SEPARATION` | `PASS` | Mechanical verification gate |
| `DEV_VAL_SEQUENCE_CONTAMINATION_BLOCKED` | `PASS` | Mechanical verification gate |
| `DUPLICATE_TIMESTAMP_DIFFERING_PRICES_BLOCKED` | `PASS` | Mechanical verification gate |
| `ETH_AFTER_BTC_ISOLATION` | `PASS` | Mechanical verification gate |
| `EXECUTABLE_PRICE_CAUSALITY_ENFORCED` | `PASS` | Mechanical verification gate |
| `EXECUTION_DELAY_ACTUALLY_APPLIED` | `PASS` | Mechanical verification gate |
| `EXECUTION_DELAY_WINDOW_ALIGNED` | `PASS` | Mechanical verification gate |
| `EXECUTION_OBSERVATION_IDENTITY_EXPLICIT` | `PASS` | Mechanical verification gate |
| `EXECUTION_RECORDS_ONLY_FOR_TURNOVER` | `PASS` | Mechanical verification gate |
| `EXECUTION_WINDOW_UPPER_BOUND` | `PASS` | Mechanical verification gate |
| `EXPECTED_INSTRUMENT_ID_REQUIRED` | `PASS` | Mechanical verification gate |
| `EXPERIMENT_DATASET_BINDING` | `PASS` | Mechanical verification gate |
| `EXPERIMENT_INSTRUMENT_BINDING` | `PASS` | Mechanical verification gate |
| `FAILED_RUN_STATE_ATOMICITY` | `PASS` | Mechanical verification gate |
| `FLAT_TO_FLAT_NO_EXECUTION` | `PASS` | Mechanical verification gate |
| `FULL_PYTEST_PASS` | `PASS` | Mechanical verification gate |
| `GENERIC_PRICE_EXPLICIT_MODE_PERMITTED` | `PASS` | Mechanical verification gate |
| `GENERIC_PRICE_NO_STRICT_TOUCH_FALLBACK` | `PASS` | Mechanical verification gate |
| `GUARDED_LOADER_FAILS_ON_INCOMPLETE_IDENTITY` | `PASS` | Mechanical verification gate |
| `GUARDED_WALK_FORWARD_ALLOWED` | `PASS` | Mechanical verification gate |
| `HELD_LONG_EXACT_RETURN` | `PASS` | Mechanical verification gate |
| `HELD_SHORT_GAIN_EXACT_RETURN` | `PASS` | Mechanical verification gate |
| `HELD_SHORT_LOSS_EXACT_RETURN` | `PASS` | Mechanical verification gate |
| `HOLDOUT_UNREGISTERED_FOR_READ_VERIFIED` | `PASS` | Mechanical verification gate |
| `HOLD_NO_BID_ASK_REQUIRED` | `PASS` | Mechanical verification gate |
| `HOLD_NO_SLIPPAGE` | `PASS` | Mechanical verification gate |
| `HOLD_NO_TAKER_FEE` | `PASS` | Mechanical verification gate |
| `HOMOGENEOUS_BTC_SEQUENCE_ALLOWED` | `PASS` | Mechanical verification gate |
| `HOMOGENEOUS_ETH_SEQUENCE_ALLOWED` | `PASS` | Mechanical verification gate |
| `INPUT_CANDLE_IMMUTABILITY` | `PASS` | Mechanical verification gate |
| `INPUT_POSITION_IMMUTABILITY` | `PASS` | Mechanical verification gate |
| `LATENCY_TIMELINE_MONOTONIC` | `PASS` | Mechanical verification gate |
| `LEDGER_PROCESS_SAFE_CONCURRENCY` | `PASS` | Mechanical verification gate |
| `LOOKBACK_EVALUATION_ORDER_INDEPENDENCE` | `PASS` | Mechanical verification gate |
| `MARKET_TYPE_NOT_SILENTLY_HARDCODED` | `PASS` | Mechanical verification gate |
| `NEXT_OBSERVATION_FILL_CLOCK` | `PASS` | Mechanical verification gate |
| `NONZERO_LATENCY_REJECTS_ARRIVAL_OBSERVATION` | `PASS` | Mechanical verification gate |
| `NO_AGGREGATE_DIRECT_RESEARCH_READ` | `PASS` | Mechanical verification gate |
| `NO_CURRENT_CLOSE_AFTER_CLOSE_SIGNAL` | `PASS` | Mechanical verification gate |
| `NO_FEE_DOUBLE_COUNT` | `PASS` | Mechanical verification gate |
| `NO_PLACEHOLDER_HASHES_VERIFIED` | `PASS` | Mechanical verification gate |
| `NO_PUBLIC_REGISTRY_TRUST_OVERRIDE` | `PASS` | Mechanical verification gate |
| `NO_SLIPPAGE_DOUBLE_COUNT` | `PASS` | Mechanical verification gate |
| `NO_STRICT_MARKET_TYPE_DEFAULT` | `PASS` | Mechanical verification gate |
| `NO_STRICT_VENUE_DEFAULT` | `PASS` | Mechanical verification gate |
| `NO_SYNTHETIC_TIMESTAMP_FOR_FUTURE_PRICE` | `PASS` | Mechanical verification gate |
| `NO_UNSAFE_OPEN_FALLBACK` | `PASS` | Mechanical verification gate |
| `OBSERVATION_INSTRUMENT_ID_REQUIRED` | `PASS` | Mechanical verification gate |
| `ORACLE_AST_ISOLATED` | `PASS` | Mechanical verification gate |
| `ORACLE_MULTI_FAMILY_CAMPAIGN_PASS` | `PASS` | Mechanical verification gate |
| `PARENT_ARTIFACT_SHA_VERIFIED` | `PASS` | Mechanical verification gate |
| `PARTITION_LOGICAL_HASHES_VERIFIED` | `PASS` | Mechanical verification gate |
| `PARTITION_MATERIALIZER_COMMITTED` | `PASS` | Mechanical verification gate |
| `PHYSICAL_DATASET_BINDING_VERIFIED` | `PASS` | Mechanical verification gate |
| `POSITIVE_LATENCY_BLOCKS_NEXT_OPEN` | `PASS` | Mechanical verification gate |
| `POST_VALUATION_OBSERVATION_REJECTED` | `PASS` | Mechanical verification gate |
| `PRE_ARRIVAL_OBSERVATION_REJECTED` | `PASS` | Mechanical verification gate |
| `PRE_ARRIVAL_STRICT_INEQUALITY` | `PASS` | Mechanical verification gate |
| `PRICE_OBSERVATION_TIMESTAMP_AUTHENTIC` | `PASS` | Mechanical verification gate |
| `PRIMARY_CAUSAL_API_STRICT_BY_DEFAULT` | `PASS` | Mechanical verification gate |
| `PROMOTION_DB_REQUIRED_AND_CONTINUITY` | `PASS` | Mechanical verification gate |
| `PROMPT_3B_0D_REGRESSIONS_ZERO` | `PASS` | Mechanical verification gate |
| `REGISTRY_IMMUTABILITY_VERIFIED` | `PASS` | Mechanical verification gate |
| `REPEATED_RUN_DETERMINISM` | `PASS` | Mechanical verification gate |
| `RETURN_TIMELINE_CAUSALITY` | `PASS` | Mechanical verification gate |
| `REVERSAL_LONG_TO_SHORT_ACCOUNTING` | `PASS` | Mechanical verification gate |
| `REVERSAL_SHORT_TO_LONG_ACCOUNTING` | `PASS` | Mechanical verification gate |
| `REVERSAL_TURNOVER_TWO` | `PASS` | Mechanical verification gate |
| `ROLE_BOUNDARY_CONTAMINATION_GUARD` | `PASS` | Mechanical verification gate |
| `ROUND3B_0D_PARTITION_REGRESSION` | `PASS` | Mechanical verification gate |
| `ROUND3B_0E_ARRIVAL_CAUSALITY_REGRESSION` | `PASS` | Mechanical verification gate |
| `ROUND3B_0E_TERMINAL_REGRESSION` | `PASS` | Mechanical verification gate |
| `ROUND3B_0F_EXECUTION_WINDOW_REGRESSION` | `PASS` | Mechanical verification gate |
| `ROUND3B_0F_TOUCH_PRICING_REGRESSION` | `PASS` | Mechanical verification gate |
| `ROUND3B_0H_REGRESSION` | `PASS` | Mechanical verification gate |
| `ROW_LEVEL_TIMESTAMP_CORROBORATION_VERIFIED` | `PASS` | Mechanical verification gate |
| `RUN_ORDER_INDEPENDENCE` | `PASS` | Mechanical verification gate |
| `SAME_INSTRUMENT_EXECUTION_ENFORCED` | `PASS` | Mechanical verification gate |
| `SAME_MARKET_TYPE_EXECUTION_ENFORCED` | `PASS` | Mechanical verification gate |
| `SECURITY_SCAN_ZERO` | `PASS` | Mechanical verification gate |
| `SELECT_LOOKBACK_STRICT_CONTEXT` | `PASS` | Mechanical verification gate |
| `SERIES_DATASET_HOMOGENEITY` | `PASS` | Mechanical verification gate |
| `SERIES_INSTRUMENT_HOMOGENEITY` | `PASS` | Mechanical verification gate |
| `SERIES_MARKET_TYPE_HOMOGENEITY` | `PASS` | Mechanical verification gate |
| `SERIES_MISSING_IDENTITY_BLOCKED` | `PASS` | Mechanical verification gate |
| `SERIES_VENUE_HOMOGENEITY` | `PASS` | Mechanical verification gate |
| `SIDE_AWARE_EXECUTABLE_PRICE` | `PASS` | Mechanical verification gate |
| `SIGNAL_CLOSE_AVAILABLE_AT_CLOSE_TIME` | `PASS` | Mechanical verification gate |
| `SINGLE_LEG_ARCHITECTURE_ENFORCED` | `PASS` | Mechanical verification gate |
| `STREAM_MONOTONICITY_REQUIRED` | `PASS` | Mechanical verification gate |
| `STRICT_BUY_REQUIRES_ASK` | `PASS` | Mechanical verification gate |
| `STRICT_CAUSAL_WALK_FORWARD` | `PASS` | Mechanical verification gate |
| `STRICT_RESEARCH_CONTEXT_REQUIRED` | `PASS` | Mechanical verification gate |
| `STRICT_SELL_REQUIRES_BID` | `PASS` | Mechanical verification gate |
| `STRICT_WALK_FORWARD_CONTEXT` | `PASS` | Mechanical verification gate |
| `STRICT_WALK_FORWARD_CONTEXT_MECHANICALLY_VERIFIED` | `PASS` | Mechanical verification gate |
| `SYNTHETIC_HELPER_EXPLICIT_OPT_IN` | `PASS` | Mechanical verification gate |
| `TAMPER_EVIDENT_HASH_CHAIN_VERIFIED` | `PASS` | Mechanical verification gate |
| `TERMINAL_DRAWDOWN_INCLUDED` | `PASS` | Mechanical verification gate |
| `TERMINAL_EXIT_COST_APPLIED_ONCE` | `PASS` | Mechanical verification gate |
| `TERMINAL_LONG_GAIN_FIXTURE` | `PASS` | Mechanical verification gate |
| `TERMINAL_LONG_LOSS_FIXTURE` | `PASS` | Mechanical verification gate |
| `TERMINAL_MARK_TO_FILL_PNL_LONG` | `PASS` | Mechanical verification gate |
| `TERMINAL_MARK_TO_FILL_PNL_SHORT` | `PASS` | Mechanical verification gate |
| `TERMINAL_MISSING_OBSERVATION_FAILS_CLOSED` | `PASS` | Mechanical verification gate |
| `TERMINAL_REUSES_EXECUTION_SELECTOR` | `PASS` | Mechanical verification gate |
| `TERMINAL_SHORT_GAIN_FIXTURE` | `PASS` | Mechanical verification gate |
| `TERMINAL_SHORT_LOSS_FIXTURE` | `PASS` | Mechanical verification gate |
| `TERMINAL_SYNTHETIC_PRICE_FALLBACK_BLOCKED` | `PASS` | Mechanical verification gate |
| `TESTED_CODE_COMMIT_PRESERVED` | `PASS` | Mechanical verification gate |
| `TEST_WORKTREE_CLEAN` | `PASS` | Mechanical verification gate |
| `TRADE_PRINT_REQUIRES_TRADE_PRICE` | `PASS` | Mechanical verification gate |
| `VALIDATION_MAX_TIMESTAMP_PRE_2024` | `PASS` | Mechanical verification gate |
| `VALIDATION_MIN_TIMESTAMP_2023` | `PASS` | Mechanical verification gate |
| `VERIFIER_AST_TRUTH_CLOSURE` | `PASS` | Mechanical verification gate |
| `WALK_FORWARD_CAPITAL_RESET` | `PASS` | Mechanical verification gate |
| `WIP_AUDIT_COMPLETE` | `PASS` | Mechanical verification gate |
| `WIP_SAFETY_BRANCH_UNTOUCHED` | `PASS` | Mechanical verification gate |
| `WIP_SAFETY_REMOTE_UNTOUCHED` | `PASS` | Mechanical verification gate |
| `ZERO_DECISION_ZERO_EXECUTION_LATENCY_CAN_SELECT_ARRIVAL` | `PASS` | Mechanical verification gate |
| `ZERO_PROMOTIONS_PERSISTENT_AND_RUNTIME` | `PASS` | Mechanical verification gate |
| `ZERO_TURNOVER_NO_EXECUTION` | `PASS` | Mechanical verification gate |
| `ZERO_TURNOVER_SELECTOR_NOT_CALLED` | `PASS` | Mechanical verification gate |

---
*Independent Review Authorization: Research Round 3B.0I Verification Closure*
