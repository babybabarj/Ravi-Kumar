# BTCETH TRADING OS: RESEARCH ROUND 3B.0H RELIABILITY ACCEPTANCE REPORT

**Acceptance Status:** `ROUND3B_0H_RELIABILITY = VERIFIED`
**Timestamp UTC:** `2026-09-22T21:42:45.082709+00:00`
**Work Branch:** `btceth-round3b-reliability`
**Head Commit SHA:** `3c22f9b971a46d166e0dffb1e6982db2ff37782f`
**Tree SHA:** `7e12d5af77610a75f33239efb69d97ce26b2aeca`
**Canonical Baseline:** `cfa80f3aabbb75a28969701d8013f6784c35a495` (Untouched: `True`)
**Acceptance Payload SHA-256:** `637d30be3d70099c7e34e9ecb282f928b3a11ada3867a5055a4b1306ff56f18a`
**Total Mechanical Gates:** `118` (Passed: `True`)

## Safety Boundaries
- `APPROVED_FOR_SHADOW = 0`
- `APPROVED_FOR_PAPER = 0`
- `TRADING CAPABILITY = ZERO`
- `2024 HOLDOUT = LOCKED`

## Summary of Closed Defects (3B.0H)
- **Strict Research Entrypoint Defaults**: `run_causal_backtest()` defaults to strict research context (`is_strict = True`) and fails closed on unidentified candles unless caller explicitly opts into synthetic test context.
- **Explicit Synthetic Permissive Helper**: `run_synthetic_causal_backtest()` provides explicit opt-in for synthetic unit tests requiring bare candle fixtures.
- **Walk-Forward Research Context**: `walk_forward_causal()`, `walk_forward_momentum()`, and `_select_lookback()` strictly require canonical dataset identity upfront and route strictly to causal engine with strict research context.
- **Valuation Series Identity Homogeneity**: Single-leg causal engine enforces complete homogeneity of `instrument_id`, `dataset_id`, `market_type`, `venue` across all candles before any P&L calculation.
- **Explicit Fail-Closed Identity Error Codes**: Specific error codes (`RESEARCH_SERIES_IDENTITY_MISMATCH`, `RESEARCH_SERIES_DATASET_MISMATCH`, `RESEARCH_SERIES_MARKET_TYPE_MISMATCH`, `RESEARCH_SERIES_VENUE_MISMATCH`, `RESEARCH_SERIES_IDENTITY_INCOMPLETE`, `RESEARCH_EXECUTION_CONTEXT_INCOMPLETE`).
- **Valuation Series Splicing Rejection**: Mixing BTC and ETH or DEV and VAL partitions in a single valuation series fails closed before P&L calculation.
- **Verifier Truth Closure**: Replaced walk-forward shortcut with authentic adversarial test evidence; prohibited gate aliasing via AST self-audit; derived gate counts dynamically.
- **Full Regression Invariants Preserved**: Zero turnover hold-state accounting (3B.0G), execution window integrity & touch pricing (3B.0F), order arrival causality & terminal settlement (3B.0E), partition system & 2024 holdout firewall (3B.0D).

## Mechanical Gates Verification Results
| Gate Name | Status | Description |
| :--- | :---: | :--- |
| `ANONYMOUS_PRIMARY_BACKTEST_BLOCKED` | `PASS` | Mechanical verification gate |
| `ANONYMOUS_WALK_FORWARD_BLOCKED` | `PASS` | Mechanical verification gate |
| `BAR_OPEN_CLOSE_SEMANTICS_EXPLICIT` | `PASS` | Mechanical verification gate |
| `BTC_ETH_VALUATION_CONTAMINATION_BLOCKED` | `PASS` | Mechanical verification gate |
| `CANONICAL_BASELINE_ANCESTRY_VALID` | `PASS` | Mechanical verification gate |
| `CANONICAL_REGISTRY_IDENTITY_EXPLICIT` | `PASS` | Mechanical verification gate |
| `CANONICAL_REMOTE_UNTOUCHED` | `PASS` | Mechanical verification gate |
| `CAPITAL_POLICY_CANONICAL_YAML_DEFAULT` | `PASS` | Mechanical verification gate |
| `CAPITAL_POLICY_CONFIG_HASH_VERIFIED` | `PASS` | Mechanical verification gate |
| `DATASET_INSTRUMENT_PROPAGATION` | `PASS` | Mechanical verification gate |
| `DEV_MAX_TIMESTAMP_PRE_2023` | `PASS` | Mechanical verification gate |
| `DEV_VALIDATION_PHYSICAL_SEPARATION` | `PASS` | Mechanical verification gate |
| `DEV_VAL_SEQUENCE_CONTAMINATION_BLOCKED` | `PASS` | Mechanical verification gate |
| `DUPLICATE_TIMESTAMP_DIFFERING_PRICES_BLOCKED` | `PASS` | Mechanical verification gate |
| `EXECUTABLE_PRICE_CAUSALITY_ENFORCED` | `PASS` | Mechanical verification gate |
| `EXECUTION_DELAY_ACTUALLY_APPLIED` | `PASS` | Mechanical verification gate |
| `EXECUTION_DELAY_WINDOW_ALIGNED` | `PASS` | Mechanical verification gate |
| `EXECUTION_OBSERVATION_IDENTITY_EXPLICIT` | `PASS` | Mechanical verification gate |
| `EXECUTION_RECORDS_ONLY_FOR_TURNOVER` | `PASS` | Mechanical verification gate |
| `EXECUTION_WINDOW_UPPER_BOUND` | `PASS` | Mechanical verification gate |
| `EXPECTED_INSTRUMENT_ID_REQUIRED` | `PASS` | Mechanical verification gate |
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
| `LATENCY_TIMELINE_MONOTONIC` | `PASS` | Mechanical verification gate |
| `LEDGER_PROCESS_SAFE_CONCURRENCY` | `PASS` | Mechanical verification gate |
| `MARKET_TYPE_NOT_SILENTLY_HARDCODED` | `PASS` | Mechanical verification gate |
| `NEXT_OBSERVATION_FILL_CLOCK` | `PASS` | Mechanical verification gate |
| `NONZERO_LATENCY_REJECTS_ARRIVAL_OBSERVATION` | `PASS` | Mechanical verification gate |
| `NO_AGGREGATE_DIRECT_RESEARCH_READ` | `PASS` | Mechanical verification gate |
| `NO_CURRENT_CLOSE_AFTER_CLOSE_SIGNAL` | `PASS` | Mechanical verification gate |
| `NO_PLACEHOLDER_HASHES_VERIFIED` | `PASS` | Mechanical verification gate |
| `NO_PUBLIC_REGISTRY_TRUST_OVERRIDE` | `PASS` | Mechanical verification gate |
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
| `RETURN_TIMELINE_CAUSALITY` | `PASS` | Mechanical verification gate |
| `REVERSAL_TURNOVER_TWO` | `PASS` | Mechanical verification gate |
| `ROLE_BOUNDARY_CONTAMINATION_GUARD` | `PASS` | Mechanical verification gate |
| `ROUND3B_0D_PARTITION_REGRESSION` | `PASS` | Mechanical verification gate |
| `ROUND3B_0E_ARRIVAL_CAUSALITY_REGRESSION` | `PASS` | Mechanical verification gate |
| `ROUND3B_0E_TERMINAL_REGRESSION` | `PASS` | Mechanical verification gate |
| `ROUND3B_0F_EXECUTION_WINDOW_REGRESSION` | `PASS` | Mechanical verification gate |
| `ROUND3B_0F_TOUCH_PRICING_REGRESSION` | `PASS` | Mechanical verification gate |
| `ROW_LEVEL_TIMESTAMP_CORROBORATION_VERIFIED` | `PASS` | Mechanical verification gate |
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
| `WIP_AUDIT_COMPLETE` | `PASS` | Mechanical verification gate |
| `WIP_SAFETY_BRANCH_UNTOUCHED` | `PASS` | Mechanical verification gate |
| `WIP_SAFETY_REMOTE_UNTOUCHED` | `PASS` | Mechanical verification gate |
| `ZERO_DECISION_ZERO_EXECUTION_LATENCY_CAN_SELECT_ARRIVAL` | `PASS` | Mechanical verification gate |
| `ZERO_PROMOTIONS_PERSISTENT_AND_RUNTIME` | `PASS` | Mechanical verification gate |
| `ZERO_TURNOVER_NO_EXECUTION` | `PASS` | Mechanical verification gate |
| `ZERO_TURNOVER_SELECTOR_NOT_CALLED` | `PASS` | Mechanical verification gate |

---
*Independent Review Authorization: Research Round 3B.0H Verification Closure*
