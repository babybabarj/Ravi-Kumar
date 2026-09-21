# Phase 1B.2 Forward Port Audit

**Branch**: `btceth-phase1b-hardened`  
**Base Commit**: `5873de692b8eb7d9b7775ef3c2a2e730f9fd8088` (Phase 1B.5 & Research Round 3A Baseline)  
**Remediation Baseline**: `6e18e19b8849646b856cff3d1c4476059e74d47d` (Phase 1B.2 Hardened Remediation)  
**Verification Date**: 2026-09-21  

---

## 1. Executive Summary

This audit documents the semantic forward-port of the hardened Phase 1B.2 historical acquisition and Bronze layer into the forward project line containing Phase 1B.3, 1B.4, 1B.5, and Research Round 3A.

The forward-port successfully integrates all Phase 1B.2 cryptographic, semantic, and defensive invariants while maintaining 100% backward compatibility with all downstream pipelines, catalogs, parsers, and research backtests.

---

## 2. Comparison: Old vs Hardened Behavior

| Architectural Dimension | Old Baseline (`963bd6a` / `5873de6`) | Hardened Implementation (`6e18e19` / Forward-Port) | Resolution & Impact |
| :--- | :--- | :--- | :--- |
| **Download Protocol** | Download archive stream before or concurrently with sidecar | **Strict Checksum-First**: Official `.CHECKSUM` sidecar fetched and parsed before streaming any archive bytes | Eliminates unvalidated downloads; fails closed immediately on missing or malformed sidecar. |
| **Local Storage Layout** | Deep nested directories with checksum embedded in archive filename (`.../{filename.stem}.{checksum}.zip`) | **Canonical Bronze Archive Layout**: `bronze/binance/{market}/{source_dataset_name}/{symbol}/{archive_filename}` | Adheres to Phase 1B.2 specification while returning full resolved path via `local_path` / `local_archive_path`. |
| **Integrity Reconciliation** | Python in-memory SHA-256 only | **Triple-Reconciliation Oracle**: `official_checksum == python_sha256 == os_sha256` using OS `shasum -a 256` | Independent OS binary cross-check prevents runtime hash corruption or library defects. |
| **Archive Unpacking** | Direct zip extraction without security checks | **Safe Zip Extractor (`bronze.py`)**: Rejects path traversal (`../`, `..\\`), absolute paths, symlinks, null bytes, multi-member archives, and corrupt CRCs | Bronze extraction is completely quarantined and hardened against zip-slip vulnerabilities. |
| **Schema & Quality Probes** | Naive comma-split parsing | **Raw Schema Inspector (`schema_inspector.py`)**: Dynamic header detection, strict numeric bounds, monotonic timestamp validation | Detects header vs headerless files; executes non-destructive quality probes on raw CSV payloads. |
| **Funding Rate Semantics** | Vulnerable to index-based column offset traps | **Catastrophic Trap Enforced**: Explicitly parses `calc_time`, `funding_interval_hours` (8), `last_funding_rate` (-0.00012359). Hard crash if interval is parsed as rate | Completely eliminates catastrophic funding rate scale distortion. |
| **Funding Parity Audit** | None | **Live REST Parity Auditor (`funding_parity.py`)**: Strict overlap comparison with tolerance for optional metadata fields | Proves historical archive matches live Binance USD-M exchange API. |
| **Timestamp Policy Audit** | Informal inspection | **Formal Timestamp Policy Auditor (`timestamp_audit.py`)**: Verifies 13-digit ms (USD-M and pre-2025 Spot) vs 16-digit us (post-2025 Spot) | Enforces temporal compliance across all acquisition datasets. |

---

## 3. Downstream Dependency Analysis & Semantic Compatibility

Downstream components were audited for interface requirements:

1. **`ArchiveCatalog` (`src/btceth_os/sources/binance/archive_catalog.py`)**:
   - *Requirements*: Expects `result.local_path`, `result.receipt_path`, `result.physical_sha256`, `result.official_checksum`, and `result.spec`.
   - *Resolution*: `DownloadReceipt` maintains backward-compatible properties/attributes `local_path`, `receipt_path`, `physical_sha256`, `content_length`, `etag`, and `last_modified`. Bidirectional synchronization in `__post_init__` populates both legacy and forward fields. `to_dict()` outputs both schemas.
2. **`BronzeRecord` Parser (`src/btceth_os/sources/binance/archive_parser.py`)**:
   - *Requirements*: Consumes `Path(result.local_path)`.
   - *Resolution*: Directly compatible; `result.local_path` points to the valid extracted or archive path.
3. **`Historical Silver` Parquet Builder (`src/btceth_os/sources/binance/historical_silver.py`)**:
   - *Requirements*: Consumes records from `iter_bronze_records` and `result.physical_sha256`.
   - *Resolution*: Unchanged interface; `physical_sha256` perfectly reconciled.
4. **Verification Scripts (`verify_phase1b3.py`, `verify_phase1b4.py`, `verify_phase1b5.py`)**:
   - *Requirements*: Expect `ArchiveDownloader(ARTIFACTS / "raw")` with positional root argument, `result.physical_sha256`, `result.spec.archive_url`.
   - *Resolution*: `ArchiveDownloader.__init__` accepts positional `raw_root` or keyword `bronze_root`. `ArchiveObjectSpec` implements `__getitem__`, `get`, `keys`, `values`, `items` for dual object/dict access.
5. **Research Dataset Builder (`tools/build_research_dataset.py`)**:
   - *Requirements*: Instantiates `ArchiveDownloader(raw_dir)` and streams monthly archives.
   - *Resolution*: Fully verified and functioning cleanly.

---

## 4. Verification Evidence & Test Compatibility

1. **Automated Unit & Integration Tests**:
   - `pytest`: **181 passed** (0 failures, 0 errors).
   - Test suites covering all hardened and downstream components:
     - `test_archive_downloader.py` (7 hardened tests)
     - `test_bronze_extraction.py` (8 tests)
     - `test_schema_inspector.py` (6 tests)
     - `test_timestamp_audit.py` (4 tests)
     - `test_funding_parity.py` (2 tests)
     - `test_archive_catalog.py` (4 tests)
     - `test_archive_parser.py` (8 tests)
     - `test_historical_silver.py` (6 tests)
     - All Phase 1A smoke, autopilot, and research backtest suites.
2. **Verification Gates**:
   - `Phase 1A Gate`: **PASS** (`mac_phase1a_verify.sh`)
   - `Phase 1B.1 Gate`: **PASS** (`mac_phase1b1_verify.sh`)
   - `Phase 1B.2 Gate`: **PASS** (`mac_phase1b2_verify.sh`, all 8 gate checks)
   - `Security Scan`: **PASS** (`TRADING CAPABILITY = ZERO`, 0 hits)
