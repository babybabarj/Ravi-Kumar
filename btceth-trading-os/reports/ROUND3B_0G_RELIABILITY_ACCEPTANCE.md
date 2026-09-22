# BTCETH TRADING OS: RESEARCH ROUND 3B.0G RELIABILITY ACCEPTANCE REPORT

**Acceptance Status:** `ROUND3B_0G_RELIABILITY = VERIFIED`
**Timestamp UTC:** `2026-09-22T20:42:51.711582+00:00`
**Work Branch:** `btceth-round3b-reliability`
**Head Commit SHA:** `5e88bbd26aeb2195560409308645cacf5ba40d33`
**Tree SHA:** `061e169d9c1e2e65b6470a816b2ecf50ad70dc0a`
**Canonical Baseline:** `cfa80f3aabbb75a28969701d8013f6784c35a495` (Untouched: `True`)
**Acceptance Payload SHA-256:** `6e28b1a481fb327f12fd654a7fe1d8001a391213fd455b2813e5942b2ef93888`

## Safety Boundaries
- `APPROVED_FOR_SHADOW = 0`
- `APPROVED_FOR_PAPER = 0`
- `TRADING CAPABILITY = ZERO`
- `2024 HOLDOUT = LOCKED`

## Summary of Closed Defect (3B.0G)
- **Hold-State Accounting**: `run_causal_backtest()` completely bypasses execution observation selection when `target_position == previous_position` (`turnover == 0`).
- **Discrete-Bar Return**: Held interval computes `gross_period_return = Decimal(previous) * ((next_close - current_close) / current_close)`; no synthetic split around intermediate marks.
- **Short-Hold Precision**: Short held from 100 to 110 earns exactly -10.0%; short held from 100 to 90 earns exactly +10.0%.
- **Intermediate Quote Invariance**: Intermediate quotes inside hold periods have 0 effect on held P&L.
- **Zero Turnover Costs**: Zero taker fee and zero slippage on hold bars.
- **Strict Research Identity Closure**: Explicit non-null `instrument_id`, `dataset_id`, `market_type`, `venue` required in strict research mode; missing identity raises `RESEARCH_EXECUTION_CONTEXT_INCOMPLETE`.
- **Canonical Metadata Complete**: All canonical readable partitions populated with explicit market identity; loader fails closed if incomplete.

## Mechanical Gates Verification Results
| Gate Name | Status | Description |
| :--- | :---: | :--- |
| `BAR_OPEN_CLOSE_SEMANTICS_EXPLICIT` | `PASS` | Mechanical verification gate |
| `CANONICAL_BASELINE_ANCESTRY_VALID` | `PASS` | Mechanical verification gate |
| `CANONICAL_REGISTRY_IDENTITY_EXPLICIT` | `PASS` | Mechanical verification gate |
| `CANONICAL_REMOTE_UNTOUCHED` | `PASS` | Mechanical verification gate |
| `CAPITAL_POLICY_CANONICAL_YAML_DEFAULT` | `PASS` | Mechanical verification gate |
| `CAPITAL_POLICY_CONFIG_HASH_VERIFIED` | `PASS` | Mechanical verification gate |
| `DATASET_IDENTITY_REQUIRED_ENFORCED` | `PASS` | Mechanical verification gate |
| `DATASET_INSTRUMENT_PROPAGATION` | `PASS` | Mechanical verification gate |
| `DEV_MAX_TIMESTAMP_PRE_2023` | `PASS` | Mechanical verification gate |
| `DEV_VALIDATION_PHYSICAL_SEPARATION` | `PASS` | Mechanical verification gate |
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
| `HELD_LONG_EXACT_RETURN` | `PASS` | Mechanical verification gate |
| `HELD_SHORT_GAIN_EXACT_RETURN` | `PASS` | Mechanical verification gate |
| `HELD_SHORT_LOSS_EXACT_RETURN` | `PASS` | Mechanical verification gate |
| `HOLDOUT_UNREGISTERED_FOR_READ_VERIFIED` | `PASS` | Mechanical verification gate |
| `HOLD_NO_BID_ASK_REQUIRED` | `PASS` | Mechanical verification gate |
| `HOLD_NO_SLIPPAGE` | `PASS` | Mechanical verification gate |
| `HOLD_NO_TAKER_FEE` | `PASS` | Mechanical verification gate |
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
| `SIDE_AWARE_EXECUTABLE_PRICE` | `PASS` | Mechanical verification gate |
| `SIGNAL_CLOSE_AVAILABLE_AT_CLOSE_TIME` | `PASS` | Mechanical verification gate |
| `STREAM_MONOTONICITY_REQUIRED` | `PASS` | Mechanical verification gate |
| `STRICT_BUY_REQUIRES_ASK` | `PASS` | Mechanical verification gate |
| `STRICT_CAUSAL_WALK_FORWARD` | `PASS` | Mechanical verification gate |
| `STRICT_RESEARCH_CONTEXT_REQUIRED` | `PASS` | Mechanical verification gate |
| `STRICT_SELL_REQUIRES_BID` | `PASS` | Mechanical verification gate |
| `STRICT_WALK_FORWARD_CONTEXT` | `PASS` | Mechanical verification gate |
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
*Independent Review Authorization: Research Round 3B.0G Verification Closure*
