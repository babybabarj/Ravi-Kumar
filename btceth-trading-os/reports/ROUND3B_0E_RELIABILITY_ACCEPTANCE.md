# BTCETH TRADING OS: RESEARCH ROUND 3B.0E RELIABILITY ACCEPTANCE REPORT

**Acceptance Status:** `ROUND3B_0E_RELIABILITY = VERIFIED`
**Timestamp UTC:** `2026-09-22T17:18:15.540473+00:00`
**Work Branch:** `btceth-round3b-reliability`
**Head Commit SHA:** `5b9e37bb44c02f66aef85fde452dd4d7a8cf4725`
**Tree SHA:** `ee60e0fe25a3323f012589050caa413ff9739ff9`
**Canonical Baseline:** `cfa80f3aabbb75a28969701d8013f6784c35a495` (Untouched: `True`)
**Acceptance Payload SHA-256:** `6974eca9861913d66b5a37d3473d4e9ebbc5216c2e3b6f4783c71b776f07e23a`

## Executive Summary

Round 3B.0E strictly eliminates the remaining execution simulation and verifier truth defects discovered after Round 3B.0D:
- **Order-Arrival Causality**: Executable observations are selected strictly after exchange arrival (`ts_event_ns >= execution_eligible_ts_ns = exchange_arrival_ts_ns`). Pre-arrival observations are strictly rejected.
- **Independent Fill Latency**: Proved that `fill_ts_ns` confirmation latency cannot retroactively validate an earlier inaccessible market price.
- **Centralized Execution Observation Selector**: normal fills and terminal flattening share `select_first_executable_observation`.
- **Execution Stream Monotonicity & Ambiguity Control**: Non-monotonic streams raise `EXECUTION_STREAM_NOT_MONOTONIC`; duplicate timestamps without sequence ID raise `AMBIGUOUS_EXECUTION_OBSERVATION`.
- **Same-Instrument & Same-Market-Type Enforcement**: BTC orders reject ETH data; USD-M Perp rejects SPOT data.
- **Side-Aware Touch Pricing**: Marketable BUY orders execute at ASK; marketable SELL orders execute at BID.
- **Terminal Settlement Truth**: Synthetic price fallback is completely eliminated. When an open position remains at simulation end, missing observation stream fails closed with `INVALID_TERMINAL_EXECUTION`. Terminal mark-to-fill movement updates both gross and net equity; exit fee applies once; peak and drawdown are updated.
- **Verifier Truth Closure**: All critical verifier gates are mechanically recomputed. AST self-inspection asserts zero hardcoded passes.

## Invariant Summary

| Invariant | Status | Verification Detail |
|---|---|---|
| **Trading Capability** | `ZERO` | Static AST and security scanner confirm 0 mutations/orders |
| **2024 Holdout** | `LOCKED` | 0 accesses allowed, 0 reads performed |
| **Paper / Shadow Promotions** | `0` | APPROVED_FOR_PAPER = 0, APPROVED_FOR_SHADOW = 0 |
| **Canonical Baseline** | `UNTOUCHED` | Ancestry strictly maintained from `cfa80f3aabbb75a28969701d8013f6784c35a495` |
| **Round 3B.0D Partitions** | `UNMODIFIED` | All 8 physical and logical partition SHA-256 digests identical |

## Mechanical Verification Gates

| Gate Identifier | Result | Verification Detail |
|---|---|---|
| `2024_HOLDOUT_LOCKED` | `PASS` | Derived dynamically from live mechanical checks |
| `ACCEPTANCE_PAYLOAD_HASH_MATCH` | `PASS` | Derived dynamically from live mechanical checks |
| `BAR_OPEN_CLOSE_SEMANTICS_EXPLICIT` | `PASS` | Derived dynamically from live mechanical checks |
| `CANONICAL_BASELINE_ANCESTRY_VALID` | `PASS` | Derived dynamically from live mechanical checks |
| `CANONICAL_REMOTE_UNTOUCHED` | `PASS` | Derived dynamically from live mechanical checks |
| `CAPITAL_POLICY_CANONICAL_YAML_DEFAULT` | `PASS` | Derived dynamically from live mechanical checks |
| `CAPITAL_POLICY_CONFIG_HASH_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `CLEAN_WORKTREE_PROOF` | `PASS` | Derived dynamically from live mechanical checks |
| `CRITICAL_GATES_ACTUALLY_RECOMPUTED` | `PASS` | Derived dynamically from live mechanical checks |
| `DATASET_IDENTITY_REQUIRED_ENFORCED` | `PASS` | Derived dynamically from live mechanical checks |
| `DEV_MAX_TIMESTAMP_PRE_2023` | `PASS` | Derived dynamically from live mechanical checks |
| `DEV_VALIDATION_PHYSICAL_SEPARATION` | `PASS` | Derived dynamically from live mechanical checks |
| `DUPLICATE_TIMESTAMP_POLICY_ENFORCED` | `PASS` | Derived dynamically from live mechanical checks |
| `EXECUTABLE_PRICE_CAUSALITY_ENFORCED` | `PASS` | Derived dynamically from live mechanical checks |
| `EXECUTION_DELAY_ACTUALLY_APPLIED` | `PASS` | Derived dynamically from live mechanical checks |
| `EXECUTION_ELIGIBILITY_AFTER_EXCHANGE_ARRIVAL` | `PASS` | Derived dynamically from live mechanical checks |
| `EXECUTION_STREAM_MONOTONIC` | `PASS` | Derived dynamically from live mechanical checks |
| `FILL_LATENCY_SEMANTICS_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `FULL_PYTEST_PASS` | `PASS` | Derived dynamically from live mechanical checks |
| `HOLDOUT_2024_LOCKED` | `PASS` | Derived dynamically from live mechanical checks |
| `HOLDOUT_UNREGISTERED_FOR_READ_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `INDEPENDENT_ORACLE_ISOLATED` | `PASS` | Derived dynamically from live mechanical checks |
| `LEDGER_PROCESS_SAFE_CONCURRENCY` | `PASS` | Derived dynamically from live mechanical checks |
| `NEXT_OBSERVATION_FILL_CLOCK` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_AGGREGATE_DIRECT_RESEARCH_READ` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_CURRENT_CLOSE_AFTER_CLOSE_SIGNAL` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_HARDCODED_EXECUTION_AUDIT_PASS` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_PLACEHOLDER_HASHES_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_PUBLIC_REGISTRY_TRUST_OVERRIDE` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_SYNTHETIC_TIMESTAMP_FOR_FUTURE_PRICE` | `PASS` | Derived dynamically from live mechanical checks |
| `NO_UNSAFE_OPEN_FALLBACK` | `PASS` | Derived dynamically from live mechanical checks |
| `ORACLE_MULTI_FAMILY_CAMPAIGN_PASS` | `PASS` | Derived dynamically from live mechanical checks |
| `ORDER_ARRIVAL_TIME_EXPLICIT` | `PASS` | Derived dynamically from live mechanical checks |
| `PARENT_ARTIFACT_SHA_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `PARTITION_LOGICAL_HASHES_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `PARTITION_MATERIALIZER_COMMITTED` | `PASS` | Derived dynamically from live mechanical checks |
| `PHYSICAL_DATASET_BINDING_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `POSITIVE_LATENCY_BLOCKS_NEXT_OPEN` | `PASS` | Derived dynamically from live mechanical checks |
| `PRE_ARRIVAL_OBSERVATION_REJECTED` | `PASS` | Derived dynamically from live mechanical checks |
| `PRICE_OBSERVATION_TIMESTAMP_AUTHENTIC` | `PASS` | Derived dynamically from live mechanical checks |
| `PROMOTION_DB_REQUIRED_AND_CONTINUITY` | `PASS` | Derived dynamically from live mechanical checks |
| `REGISTRY_IMMUTABILITY_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `ROLE_BOUNDARY_CONTAMINATION_GUARD` | `PASS` | Derived dynamically from live mechanical checks |
| `ROUND3B_0D_PARTITION_REGRESSION` | `PASS` | Derived dynamically from live mechanical checks |
| `ROW_LEVEL_TIMESTAMP_CORROBORATION_VERIFIED` | `PASS` | Derived dynamically from live mechanical checks |
| `SAME_INSTRUMENT_EXECUTION_ENFORCED` | `PASS` | Derived dynamically from live mechanical checks |
| `SAME_MARKET_TYPE_EXECUTION_ENFORCED` | `PASS` | Derived dynamically from live mechanical checks |
| `SECURITY_SCAN_ZERO` | `PASS` | Derived dynamically from live mechanical checks |
| `SIDE_AWARE_EXECUTABLE_PRICE` | `PASS` | Derived dynamically from live mechanical checks |
| `SIGNAL_CLOSE_AVAILABLE_AT_CLOSE_TIME` | `PASS` | Derived dynamically from live mechanical checks |
| `STRICT_CAUSAL_WALK_FORWARD` | `PASS` | Derived dynamically from live mechanical checks |
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
| `VALIDATION_MAX_TIMESTAMP_PRE_2024` | `PASS` | Derived dynamically from live mechanical checks |
| `VALIDATION_MIN_TIMESTAMP_2023` | `PASS` | Derived dynamically from live mechanical checks |
| `WIP_AUDIT_COMPLETE` | `PASS` | Derived dynamically from live mechanical checks |
| `WIP_SAFETY_BRANCH_UNTOUCHED` | `PASS` | Derived dynamically from live mechanical checks |
| `ZERO_PROMOTIONS` | `PASS` | Derived dynamically from live mechanical checks |
| `ZERO_PROMOTIONS_PERSISTENT_AND_RUNTIME` | `PASS` | Derived dynamically from live mechanical checks |

## Superseding Notice

```text
ROUND3B_0D_DATA_INTEGRITY = VERIFIED
ROUND3B_0D_RESEARCH_SPLIT = VERIFIED
ROUND3B_0D_BAR_TIME_CAUSALITY = VERIFIED
ROUND3B_0D_EXECUTION_CAUSALITY = SUPERSEDED_BY_3B_0E
ROUND3B_0D_OVERALL = SUPERSEDED_FOR_EXECUTION_REMEDIATION
```

## Next Steps

```text
CANONICAL MERGE = NOT AUTHORIZED
STRATEGY DISCOVERY = NOT AUTHORIZED
NEXT = INDEPENDENT REVIEW FOR RELIABILITY MERGE AUTHORIZATION
```

