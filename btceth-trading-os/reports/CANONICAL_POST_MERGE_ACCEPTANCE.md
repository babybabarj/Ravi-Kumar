# BTCETH Trading OS — Canonical Post-Merge Acceptance Evidence

## 1. Executive Summary

| Dimension | Value / Status |
| :--- | :--- |
| **Canonical Post-Merge Acceptance** | **`VERIFIED`** |
| **Canonical Shared Branch** | `btceth-phase1b` |
| **Old Canonical Head** | `5873de692b8eb7d9b7775ef3c2a2e730f9fd8088` |
| **Hardened Merge Point** | `5f59383d765d7682be8ce25e5043145b4a43e692` |
| **Post-Merge Tooling Commit** | `f2b7988d54d222ec4c36535c58c8c17e3daa45d9` |
| **Tested Tree SHA** | `9020745821e843c9d1fcc525c8ee6b4e147648ec` |
| **Fast-Forward Only** | `TRUE` |
| **Merge Commit Created** | `FALSE` |
| **Force Push Used** | `FALSE` |
| **Working Tree Clean Before Verification** | `TRUE` |
| **Dirty Paths Before Verification** | `[]` |
| **Trading Capability** | `ZERO` (0 forbidden AST hits) |
| **2024 Holdout Boundary** | `LOCKED` (Unopened) |
| **Next Step** | `ROUND 3B WIP INDEPENDENT AUDIT` |

---

## 2. Milestone Verification Results

| Gate / Milestone | Verification Command | Status | Notes / Evidence |
| :--- | :--- | :--- | :--- |
| **Pytest Suite** | `python -m pytest` | **`PASS`** | 189 passed in 2.83s (0 failures, 0 errors) |
| **Security Scan** | `python -m btceth_os.security_scan` | **`PASS`** | `TRADING CAPABILITY = ZERO` (0 AST violations) |
| **Phase 1A** | `bash tools/mac_phase1a_verify.sh` | **`VERIFIED`** | Public WebSocket/REST live capture, orderbook synchronization |
| **Phase 1B.1** | `bash tools/mac_phase1b1_verify.sh` | **`VERIFIED`** | 20 canonical datasets, contract & request planner verified |
| **Phase 1B.2** | `bash tools/mac_phase1b2_verify.sh` | **`VERIFIED`** | 15 archives (94.8308 MiB), LIVE_REST funding parity passed |
| **Phase 1B.3** | `bash tools/mac_phase1b3_verify.sh` | **`VERIFIED`** | Raw SQLite Catalog in WAL mode |
| **Phase 1B.4** | `bash tools/mac_phase1b4_verify.sh` | **`VERIFIED`** | Bronze Record Parser |
| **Phase 1B.5** | `python tools/verify_phase1b5.py` | **`VERIFIED`** | Silver Parquet Decimal128(38, 18) |
| **Research Round 3A** | `python tools/verify_research_round3a.py` | **`VERIFIED`** | All 11 gates pass, 2024 Holdout Locked |
| **Demo Autopilot** | `python tools/verify_demo_autopilot.py` | **`VERIFIED`** | Verified infrastructure (`APPROVED_FOR_PAPER = 0`) |
| **Canonical Post-Merge Verifier** | `python tools/verify_canonical_post_merge.py` | **`VERIFIED`** | All 24 mechanical checks pass |

---

## 3. Cryptographic Invariants & Branch Anchors

| Artifact / Branch | Expected SHA | Observed SHA | Match |
| :--- | :--- | :--- | :--- |
| **Silver Parquet SHA-256** | `b4b77ca9497759ac8ee831a7c12ac963a6c5a2309a65d19f58c2da8e8d774513` | `b4b77ca9497759ac8ee831a7c12ac963a6c5a2309a65d19f58c2da8e8d774513` | **`MATCH`** |
| **Dataset v3.1.0 Logical SHA-256** | `a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930` | `a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930` | **`MATCH`** |
| **Pre-Merge V2 Provenance Hash** | `2efaa600d09116339cc23aa633ef5e5bdb2c3acaf7904f279f8a35ae48590664` | `2efaa600d09116339cc23aa633ef5e5bdb2c3acaf7904f279f8a35ae48590664` | **`MATCH`** |
| **Hardened Provenance Branch** | `5f59383d765d7682be8ce25e5043145b4a43e692` | `origin/btceth-phase1b-hardened` | **`PRESERVED`** |
| **Round 3B WIP Safety Branch** | `11d6e370db0d27cd635528a3c530286b28c60416` | `origin/btceth-round3b-wip-safety` | **`FROZEN`** |
| **Pre-Hardening Snapshot Branch** | `5873de692b8eb7d9b7775ef3c2a2e730f9fd8088` | `origin/btceth-pre-phase1b2-hardening-snapshot` | **`PRESERVED`** |

---

## 4. Policy Invariants

- `APPROVED_FOR_SHADOW = 0`
- `APPROVED_FOR_PAPER = 0`
- `TRADING CAPABILITY = ZERO`
- `2024 HOLDOUT = LOCKED`
- `NO_VALIDATED_EDGE` maintained
