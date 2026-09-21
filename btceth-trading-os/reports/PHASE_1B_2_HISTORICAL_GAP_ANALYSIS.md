# Phase 1B.2 Historical Gap Analysis

## Objective
Forensically compare the hardened Phase 1B.2 implementation (`c882c6a`) against the historical commit `963bd6a5657c2ed4f924ade045fb703b73f5412e` to evaluate architectural completeness, safety invariants, and evidence density.

---

## Capability Classification Matrix

| Capability Area | Historical (`963bd6a`) | Hardened (`c882c6a`) | Classification |
| :--- | :--- | :--- | :---: |
| **Checksum Validation** | Python SHA-256 vs official checksum | Triple-reconciliation: official == Python SHA-256 == OS `shasum -a 256` oracle | **PRESENT_BUT_WEAKER** |
| **Safe ZIP Extraction** | Not implemented; raw ZIPs unextracted | Safe extraction with traversal (`../`), symlink, null byte, and containment checks | **MISSING** |
| **Raw Schema Inspection** | Not implemented | Dynamic header detection, canonical column maps (klines, trades, aggTrades, funding), quality probes | **MISSING** |
| **Funding Rate Safety Trap** | Not implemented; risk of interval vs rate confusion | Strict semantic mapping, interval != rate assertion, magnitude bound check ($|r| \le 0.1$) | **MISSING** |
| **Funding Archive / REST Parity** | Not implemented | Automated overlap audit, timestamp matching, optional REST field tolerance | **MISSING** |
| **Timestamp Policy Audit** | Config declarations only | Mechanical audit of Spot ms (pre-2025: 13 digits), Spot us (post-2025: 16 digits), USD-M fixed ms | **MISSING** |
| **Acceptance Breadth** | 1 archive (`BTCUSDT-fundingRate-2024-11`, 746 bytes) | 15 archives across all 10 dataset categories for BTCUSDT & ETHUSDT Spot and USD-M (99.4 MB) | **PRESENT_BUT_WEAKER** |
| **Repeatability Verification** | Unit test only | 3-run mechanical gate: Run 1 clean, Run 2 cache hit, Run 3 interrupted `.part` recovery | **PRESENT_BUT_WEAKER** |
| **Audit Reporting** | Single `ACCEPTANCE.json` (3 boolean fields) | 6 comprehensive reports (.json + .md): Manifest, Checksums, Schemas, Timestamps, Funding, Acceptance | **PRESENT_BUT_WEAKER** |
| **Zero-Trading Security** | ZERO capability, 0 AST hits | ZERO capability, 0 AST hits | **ALREADY_PRESENT_AND_CORRECT** |

---

## Key Conclusions
1. The historical implementation `963bd6a` established the initial streaming download and `.part` promotion pattern, but left safe Bronze extraction, schema inspection, timestamp policy enforcement, and funding rate safety unbuilt.
2. The hardened implementation (`c882c6a`) fills all identified gaps with independent cryptographic oracles, catastrophic regression tests, and full report evidence.
3. No canonical historical inputs or contracts were invalidated; rather, the acquisition pipeline has been hardened to production standards.
