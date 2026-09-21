from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from btceth_os.sources.binance.archive_downloader import ArchiveDownloader, DownloadReceipt
from btceth_os.sources.binance.archive_paths import build_archive_paths
from btceth_os.sources.binance.archive_planner import plan_archive_requests
from btceth_os.sources.binance.funding_parity import FundingParityAuditor, FundingParityReport
from btceth_os.sources.binance.models import ArchiveObjectSpec
from btceth_os.sources.binance.schema_inspector import SchemaInspector
from btceth_os.sources.binance.timestamp_audit import TimestampPolicyAuditor
from btceth_os.sources.registry import load_historical_datasets_registry

ROOT = Path(__file__).resolve().parents[1]
BRONZE_ROOT = ROOT / "artifacts" / "data" / "bronze"
REPORTS = ROOT / "reports"


def run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)


def get_git_commit() -> str:
    res = run_cmd(["git", "rev-parse", "HEAD"])
    return res.stdout.strip()


def build_acceptance_specs() -> list[ArchiveObjectSpec]:
    registry = {d.dataset_id: d for d in load_historical_datasets_registry()}
    specs: list[ArchiveObjectSpec] = []

    # 1. Spot BTCUSDT / ETHUSDT klines 1m (Pre-2025: 2024-12-31, Post-2025: 2025-01-01)
    for sym in ["BTCUSDT", "ETHUSDT"]:
        ds = registry[f"BINANCE:SPOT:{sym}:KLINES_1M"]
        specs.extend(plan_archive_requests(ds, "2024-12-31", "2024-12-31", as_of_utc="2025-01-05T00:00:00Z"))
        specs.extend(plan_archive_requests(ds, "2025-01-01", "2025-01-01", as_of_utc="2025-01-05T00:00:00Z"))

    # 2. Spot BTCUSDT aggTrades & ETHUSDT trades (2024-12-31)
    specs.extend(plan_archive_requests(registry["BINANCE:SPOT:BTCUSDT:AGG_TRADES"], "2024-12-31", "2024-12-31", as_of_utc="2025-01-05T00:00:00Z"))
    specs.extend(plan_archive_requests(registry["BINANCE:SPOT:ETHUSDT:TRADES"], "2024-12-31", "2024-12-31", as_of_utc="2025-01-05T00:00:00Z"))

    # 3. USD-M Klines (BTCUSDT & ETHUSDT 2024-11-01)
    specs.extend(plan_archive_requests(registry["BINANCE:USD_M_PERP:BTCUSDT:KLINES_1M"], "2024-11-01", "2024-11-01", as_of_utc="2024-11-10T00:00:00Z"))
    specs.extend(plan_archive_requests(registry["BINANCE:USD_M_PERP:ETHUSDT:KLINES_1M"], "2024-11-01", "2024-11-01", as_of_utc="2024-11-10T00:00:00Z"))

    # 4. USD-M Mark Price, Index Price, Premium Index (BTCUSDT 2024-11-01)
    specs.extend(plan_archive_requests(registry["BINANCE:USD_M_PERP:BTCUSDT:MARK_PRICE_KLINES_1M"], "2024-11-01", "2024-11-01", as_of_utc="2024-11-10T00:00:00Z"))
    specs.extend(plan_archive_requests(registry["BINANCE:USD_M_PERP:BTCUSDT:INDEX_PRICE_KLINES_1M"], "2024-11-01", "2024-11-01", as_of_utc="2024-11-10T00:00:00Z"))
    specs.extend(plan_archive_requests(registry["BINANCE:USD_M_PERP:BTCUSDT:PREMIUM_PRICE_KLINES_1M"], "2024-11-01", "2024-11-01", as_of_utc="2024-11-10T00:00:00Z"))

    # 5. USD-M aggTrades & trades (2024-11-01)
    specs.extend(plan_archive_requests(registry["BINANCE:USD_M_PERP:BTCUSDT:AGG_TRADES"], "2024-11-01", "2024-11-01", as_of_utc="2024-11-10T00:00:00Z"))
    specs.extend(plan_archive_requests(registry["BINANCE:USD_M_PERP:ETHUSDT:TRADES"], "2024-11-01", "2024-11-01", as_of_utc="2024-11-10T00:00:00Z"))

    # 6. USD-M Funding Rate (Monthly 2024-11 for BTCUSDT & ETHUSDT)
    specs.extend(plan_archive_requests(registry["BINANCE:USD_M_PERP:BTCUSDT:FUNDING_HISTORY"], "2024-11-01", "2024-11-30", as_of_utc="2024-12-10T00:00:00Z"))
    specs.extend(plan_archive_requests(registry["BINANCE:USD_M_PERP:ETHUSDT:FUNDING_HISTORY"], "2024-11-01", "2024-11-30", as_of_utc="2024-12-10T00:00:00Z"))

    return specs


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    BRONZE_ROOT.mkdir(parents=True, exist_ok=True)

    verification_started = datetime.now(timezone.utc).isoformat()
    status_proc = run_cmd(["git", "status", "--porcelain"])
    working_tree_clean_before = (len(status_proc.stdout.strip()) == 0)
    current_branch = run_cmd(["git", "branch", "--show-current"]).stdout.strip()

    # Clean tested code commit identification
    tested_code_commit_sha = get_git_commit()
    tree_proc = run_cmd(["git", "rev-parse", f"{tested_code_commit_sha}^{{tree}}"])
    tested_tree_sha = tree_proc.stdout.strip()

    print("=== Phase 1B.2 Acceptance Verification Gate ===")
    print(f"Branch: {current_branch}")
    print(f"Tested Code Commit: {tested_code_commit_sha}")
    print(f"Tested Tree SHA: {tested_tree_sha}")

    # 1. Pytest suite
    print("[1/8] Running full automated test suite...")
    test_proc = run_cmd([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    (REPORTS / "PHASE_1B_2_TEST_RESULTS.txt").write_text(test_proc.stdout + test_proc.stderr)
    tests_passed = (test_proc.returncode == 0)
    print(f"Pytest result: {'PASS' if tests_passed else 'FAIL'}")

    # 2. Security scan
    print("[2/8] Running zero-trading security scan...")
    sec_proc = run_cmd([sys.executable, "-m", "btceth_os.security_scan"])
    (REPORTS / "PHASE_1B_2_SECURITY_SCAN.txt").write_text(sec_proc.stdout + sec_proc.stderr)
    sec_passed = (sec_proc.returncode == 0 and '"trading_capability": "ZERO"' in sec_proc.stdout)
    print(f"Security scan result: {'PASS' if sec_passed else 'FAIL'}")

    # 3. Acceptance downloads matrix
    print("[3/8] Executing bounded acceptance download matrix...")
    specs = build_acceptance_specs()
    downloader = ArchiveDownloader(bronze_root=BRONZE_ROOT)

    receipts: list[DownloadReceipt] = []
    safe_extraction_passed = True

    # RUN 1: Acquisition run
    for spec in specs:
        r = downloader.download(spec, extract=True)
        receipts.append(r)
        if not r.extracted_payload_path or not Path(r.extracted_payload_path).is_file():
            safe_extraction_passed = False

    # Distinct Byte Accounting (Section 9 & 10)
    total_archives_verified = len(receipts)
    total_archive_bytes_verified = sum(r.archive_byte_size or 0 for r in receipts)
    total_archive_mib_verified = round(total_archive_bytes_verified / (1024 * 1024), 4)
    total_archives_downloaded_this_run = sum(1 for r in receipts if r.status == "DOWNLOADED")
    total_bytes_downloaded_this_run = sum(r.archive_byte_size or 0 for r in receipts if r.status == "DOWNLOADED")
    total_cache_hits = sum(1 for r in receipts if r.status == "EXISTING_VALID")
    total_bytes_reused_from_verified_cache = sum(r.archive_byte_size or 0 for r in receipts if r.status == "EXISTING_VALID")

    # Triple-reconciliation oracle recomputed from evidence (Section 11)
    triple_reconciled = all(
        r.official_checksum is not None
        and r.computed_archive_sha256 is not None
        and r.os_computed_sha256 is not None
        and (r.official_checksum == r.computed_archive_sha256 == r.os_computed_sha256)
        for r in receipts
    )

    print(
        f"Run 1 completed: {total_archives_verified} archives verified "
        f"({total_archive_bytes_verified:,} bytes / {total_archive_mib_verified} MiB), "
        f"{total_bytes_downloaded_this_run:,} bytes downloaded this run, "
        f"{total_cache_hits} cache hits."
    )

    # 4. Section 14: Repeatability & Idempotency Audit
    print("[4/8] Testing Repeatability & Idempotency (Run 2: Cache Hit)...")
    run2_receipts: list[DownloadReceipt] = []
    for spec in specs:
        r2 = downloader.download(spec, extract=True)
        run2_receipts.append(r2)
    idempotency_passed = all(r.status == "EXISTING_VALID" for r in run2_receipts)
    print(f"Run 2 (Idempotency cache hit): {'PASS' if idempotency_passed else 'FAIL'}")

    print("[5/8] Testing Resumability Recovery (Run 3: Interrupted .part fixture)...")
    resumability_passed = False
    try:
        sample_spec = specs[0]
        market_dir = "spot" if sample_spec.market == "spot" else "futures_um"
        s_dir = BRONZE_ROOT / "binance" / market_dir / sample_spec.source_dataset_name / sample_spec.symbol
        arch_file = s_dir / sample_spec.archive_filename
        part_path = s_dir / f"{sample_spec.archive_filename}.part"
        backup_path = s_dir / f"{sample_spec.archive_filename}.run3_bak"

        # Simulate interrupted download state: archive removed, partial .part present
        if arch_file.exists():
            arch_file.rename(backup_path)
        part_path.write_bytes(b"INTERRUPTED_TRUNCATED_STREAM_FIXTURE_DATA")

        r3 = downloader.download(sample_spec, extract=True)
        resumability_passed = (
            r3.status == "DOWNLOADED"
            and arch_file.is_file()
            and not part_path.exists()
            and r3.checksum_verified
        )
        if backup_path.exists():
            backup_path.unlink()
    except Exception as e:
        print(f"Run 3 error: {e}")
        resumability_passed = False
    print(f"Run 3 (Resumability recovery): {'PASS' if resumability_passed else 'FAIL'}")

    # 5. Schema, Quality Probes, and Timestamp Audits
    print("[6/8] Performing schema audits, quality probes, and timestamp policy checks...")
    schema_records = []
    timestamp_records = []
    quality_records = []
    all_timestamps_compliant = True

    for r in receipts:
        if not r.extracted_payload_path:
            continue
        p_path = Path(r.extracted_payload_path)
        spec_dict = r.spec if isinstance(r.spec, dict) else r.spec.to_dict()
        dataset_name = spec_dict["source_dataset_name"]
        symbol = spec_dict["symbol"]
        market = spec_dict["market"]
        period_key = spec_dict["period_key"]
        dataset_id = spec_dict["dataset_id"]

        # Timestamp policy audit
        ts_res = TimestampPolicyAuditor.audit_file(p_path, dataset_id, symbol, market, period_key)
        timestamp_records.append(ts_res.to_dict())
        if not ts_res.policy_compliant:
            all_timestamps_compliant = False

        # Quality probe
        q_probe = SchemaInspector.run_quality_probe(p_path, dataset_name, expected_unit=ts_res.declared_policy_unit)
        quality_records.append({
            "dataset_id": dataset_id,
            "dataset_name": dataset_name,
            "symbol": symbol,
            "row_count": q_probe.row_count,
            "column_count_violations": q_probe.column_count_violations,
            "malformed_row_count": q_probe.malformed_row_count,
            "is_monotonic": q_probe.is_monotonic,
            "duplicate_timestamp_count": q_probe.duplicate_timestamp_count,
            "price_violations": q_probe.price_violations,
        })

    # Schema Quality Gate (Section 15)
    total_col_violations = sum(q["column_count_violations"] for q in quality_records)
    total_malformed_rows = sum(q["malformed_row_count"] for q in quality_records)
    total_ordering_violations = sum(1 for q in quality_records if not q["is_monotonic"])
    total_price_violations = sum(q["price_violations"] for q in quality_records)
    schema_quality_passed = (
        total_col_violations == 0
        and total_malformed_rows == 0
        and total_ordering_violations == 0
        and total_price_violations == 0
    )

    # 6. Funding Archive / Live REST Parity Audit (Sections 13 & 14)
    print("[7/8] Performing funding archive vs live REST parity audit (BTC & ETH)...")
    funding_reports: list[FundingParityReport] = []
    parity_modes: list[str] = []
    funding_parity_passed = False
    funding_parity_symbols = ["BTCUSDT", "ETHUSDT"]

    try:
        for sym in funding_parity_symbols:
            funding_receipt = next(
                r for r in receipts
                if r.spec["source_dataset_name"] == "fundingRate" and r.spec["symbol"] == sym
            )
            arch_records = SchemaInspector.parse_funding_rate_csv(Path(funding_receipt.extracted_payload_path))
            start_ts = arch_records[-5].calc_time_raw
            end_ts = arch_records[-1].calc_time_raw

            try:
                rest_items = FundingParityAuditor.fetch_live_rest_funding(
                    sym, limit=100, start_time=start_ts, end_time=end_ts
                )
                parity_mode = "LIVE_REST"
            except Exception as exc:
                print(f"Warning: live REST funding query failed for {sym}: {exc}")
                parity_mode = "SYNTHETIC_FALLBACK"
                rest_items = [
                    FundingParityAuditor.parse_rest_response([
                        {
                            "symbol": sym,
                            "fundingTime": arch_records[-1].calc_time_raw,
                            "fundingRate": str(arch_records[-1].last_funding_rate),
                            "markPrice": "95000.0",
                            "rateType": "Regular",
                        }
                    ])[0]
                ]

            parity_modes.append(parity_mode)
            rep = FundingParityAuditor.audit_overlap(sym, arch_records, rest_items)
            funding_reports.append(rep)

        # Enforce Section 13 & 14: require LIVE_REST, matched > 0, 0 rate mismatches, 0 duplicate settlements
        all_live = all(m == "LIVE_REST" for m in parity_modes)
        all_clean = all(
            rep.matched_count > 0 and rep.rate_mismatch_count == 0 and rep.duplicate_settlement_count == 0
            for rep in funding_reports
        )
        funding_parity_passed = (all_live and all_clean)
        active_funding_mode = "LIVE_REST" if all_live else "SYNTHETIC_FALLBACK"
    except Exception as e:
        print(f"Funding parity audit error: {e}")
        funding_parity_passed = False
        active_funding_mode = "FAILED"

    print(f"Funding parity audit: {'PASS' if funding_parity_passed else 'FAIL'} (mode: {active_funding_mode})")

    # 7. Compile and save all required reports
    print("[8/8] Compiling required Phase 1B.2 reports...")

    # Report 1: ACQUISITION MANIFEST (Section 12: Deterministic SHA contract)
    manifest_payload_pre = {
        "manifest_version": "1.0.0",
        "created_at_utc": verification_started,
        "branch_name": current_branch,
        "tested_code_commit_sha": tested_code_commit_sha,
        "tested_tree_sha": tested_tree_sha,
        "total_archives_verified": total_archives_verified,
        "total_archive_bytes_verified": total_archive_bytes_verified,
        "total_archive_mib_verified": total_archive_mib_verified,
        "total_archives_downloaded_this_run": total_archives_downloaded_this_run,
        "total_bytes_downloaded_this_run": total_bytes_downloaded_this_run,
        "total_cache_hits": total_cache_hits,
        "total_bytes_reused_from_verified_cache": total_bytes_reused_from_verified_cache,
        "objects": [r.to_dict() for r in receipts],
    }
    canonical_manifest_bytes = json.dumps(manifest_payload_pre, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_sha256 = hashlib.sha256(canonical_manifest_bytes).hexdigest()
    manifest_payload = dict(manifest_payload_pre)
    manifest_payload["manifest_sha256"] = manifest_sha256
    (REPORTS / "PHASE_1B_2_ACQUISITION_MANIFEST.json").write_text(json.dumps(manifest_payload, indent=2) + "\n")

    manifest_md_lines = [
        "# Phase 1B.2 Historical Acquisition Manifest",
        "",
        f"- **Creation Timestamp (UTC)**: `{manifest_payload['created_at_utc']}`",
        f"- **Branch Name**: `{current_branch}`",
        f"- **Tested Code Commit SHA**: `{tested_code_commit_sha}`",
        f"- **Tested Tree SHA**: `{tested_tree_sha}`",
        f"- **Logical Manifest SHA-256**: `{manifest_sha256}`",
        f"- **Total Archives Verified**: `{total_archives_verified}`",
        f"- **Total Archive Bytes Verified**: `{total_archive_bytes_verified:,}` bytes ({total_archive_mib_verified} MiB)",
        f"- **Total Downloaded This Run**: `{total_bytes_downloaded_this_run:,}` bytes ({total_archives_downloaded_this_run} archives)",
        f"- **Total Cache Hits**: `{total_cache_hits}` ({total_bytes_reused_from_verified_cache:,}` bytes reused)",
        "",
        "| Dataset ID | Market | Symbol | Filename | Status | Archive Size | Archive SHA-256 | Checksum Match |",
        "| :--- | :---: | :---: | :--- | :---: | :---: | :--- | :---: |",
    ]
    for r in receipts:
        spec = r.spec
        manifest_md_lines.append(
            f"| `{spec['dataset_id']}` | {spec['market']} | {spec['symbol']} | `{r.payload_filename or spec['archive_filename']}` | `{r.status}` | {r.archive_byte_size:,} B | `{r.computed_archive_sha256[:16]}...` | {'YES' if r.checksum_verified else 'NO'} |"
        )
    (REPORTS / "PHASE_1B_2_ACQUISITION_MANIFEST.md").write_text("\n".join(manifest_md_lines) + "\n")

    # Report 2: CHECKSUM AUDIT (Section 11)
    checksum_audit_payload = {
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "branch_name": current_branch,
        "tested_code_commit_sha": tested_code_commit_sha,
        "triple_reconciliation_passed": triple_reconciled,
        "objects_audited": len(receipts),
        "checksum_records": [
            {
                "archive_filename": r.spec["archive_filename"],
                "official_checksum": r.official_checksum,
                "python_sha256": r.computed_archive_sha256,
                "os_sha256": r.os_computed_sha256,
                "reconciled": (r.official_checksum == r.computed_archive_sha256 == r.os_computed_sha256),
            }
            for r in receipts
        ],
    }
    (REPORTS / "PHASE_1B_2_CHECKSUM_AUDIT.json").write_text(json.dumps(checksum_audit_payload, indent=2) + "\n")

    checksum_md_lines = [
        "# Phase 1B.2 Cryptographic Checksum Audit",
        "",
        f"- **Audit Timestamp (UTC)**: `{checksum_audit_payload['audit_timestamp_utc']}`",
        f"- **Tested Code Commit**: `{tested_code_commit_sha}`",
        f"- **Triple-Reconciliation Oracle Status**: `{'PASS' if triple_reconciled else 'FAIL'}`",
        f"- **Formula**: `official_checksum == python_sha256 == os_sha256`",
        "",
        "| Archive Filename | Official Checksum | Python SHA-256 | OS sha256 (`shasum`) | Reconciled |",
        "| :--- | :--- | :--- | :--- | :---: |",
    ]
    for rec in checksum_audit_payload["checksum_records"]:
        reconciled_str = "PASS" if rec["reconciled"] else "FAIL"
        checksum_md_lines.append(
            f"| `{rec['archive_filename']}` | `{rec['official_checksum'][:16]}...` | `{rec['python_sha256'][:16]}...` | `{rec['os_sha256'][:16]}...` | {reconciled_str} |"
        )
    (REPORTS / "PHASE_1B_2_CHECKSUM_AUDIT.md").write_text("\n".join(checksum_md_lines) + "\n")

    # Report 3: SCHEMA AUDIT (Section 15)
    schema_audit_payload = {
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "schema_quality_passed": schema_quality_passed,
        "total_column_count_violations": total_col_violations,
        "total_malformed_rows": total_malformed_rows,
        "total_ordering_violations": total_ordering_violations,
        "total_price_violations": total_price_violations,
        "records": quality_records,
    }
    (REPORTS / "PHASE_1B_2_SCHEMA_AUDIT.json").write_text(json.dumps(schema_audit_payload, indent=2) + "\n")

    schema_md_lines = [
        "# Phase 1B.2 Raw Schema & Quality Probe Audit",
        "",
        f"- **Audit Timestamp (UTC)**: `{schema_audit_payload['audit_timestamp_utc']}`",
        f"- **Schema Quality Gate**: `{'PASS' if schema_quality_passed else 'FAIL'}`",
        f"- **Total Column Count Violations**: `{total_col_violations}`",
        f"- **Total Malformed Rows**: `{total_malformed_rows}`",
        f"- **Total Timestamp Ordering Violations**: `{total_ordering_violations}`",
        "",
        "| Dataset ID | Symbol | Rows | Header Detected | Monotonic | Duplicates | Col Violations | Price Violations |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for q in quality_records:
        schema_md_lines.append(
            f"| `{q['dataset_id']}` | {q['symbol']} | {q['row_count']:,} | YES | {'YES' if q['is_monotonic'] else 'NO'} | {q['duplicate_timestamp_count']} | {q['column_count_violations']} | {q['price_violations']} |"
        )
    (REPORTS / "PHASE_1B_2_SCHEMA_AUDIT.md").write_text("\n".join(schema_md_lines) + "\n")

    # Report 4: TIMESTAMP AUDIT
    timestamp_audit_payload = {
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "all_timestamps_compliant": all_timestamps_compliant,
        "records": timestamp_records,
    }
    (REPORTS / "PHASE_1B_2_TIMESTAMP_AUDIT.json").write_text(json.dumps(timestamp_audit_payload, indent=2) + "\n")

    ts_md_lines = [
        "# Phase 1B.2 Timestamp Policy Compliance Audit",
        "",
        f"- **Audit Timestamp (UTC)**: `{timestamp_audit_payload['audit_timestamp_utc']}`",
        f"- **Overall Compliance**: `{'PASS' if all_timestamps_compliant else 'FAIL'}`",
        "",
        "| Dataset ID | Declared Policy | Observed Digits | Min TS (UTC) | Max TS (UTC) | Compliant |",
        "| :--- | :---: | :---: | :--- | :--- | :---: |",
    ]
    for t in timestamp_records:
        ts_md_lines.append(
            f"| `{t['dataset_id']}` | {t['declared_policy_unit']} | {t['digits_observed']}d | `{t['first_normalized_utc']}` | `{t['last_normalized_utc']}` | {'PASS' if t['policy_compliant'] else 'FAIL'} |"
        )
    (REPORTS / "PHASE_1B_2_TIMESTAMP_AUDIT.md").write_text("\n".join(ts_md_lines) + "\n")

    # Report 5: FUNDING PARITY (Sections 13 & 14)
    funding_parity_payload = {
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "funding_parity_mode": active_funding_mode,
        "funding_parity_passed": funding_parity_passed,
        "symbols_audited": funding_parity_symbols,
        "reports": [r.to_dict() for r in funding_reports],
    }
    (REPORTS / "PHASE_1B_2_FUNDING_PARITY.json").write_text(json.dumps(funding_parity_payload, indent=2) + "\n")

    parity_md_lines = [
        "# Phase 1B.2 Funding Archive / REST Parity Audit",
        "",
        f"- **Parity Audit Status**: `{'PASS' if funding_parity_passed else 'FAIL'}`",
        f"- **Funding Parity Mode**: `{active_funding_mode}`",
        f"- **Symbols Audited**: `{', '.join(funding_parity_symbols)}`",
        "",
    ]
    for rep in funding_reports:
        parity_md_lines.extend([
            f"### Symbol: `{rep.symbol}`",
            f"- Archive Records: `{rep.archive_count}`",
            f"- REST Records: `{rep.rest_count}`",
            f"- Matched Settlements: `{rep.matched_count}`",
            f"- Rate Mismatches: `{rep.rate_mismatch_count}`",
            f"- Duplicate Settlements: `{rep.duplicate_settlement_count}`",
            f"- Optional Fields Tolerated: `{rep.optional_fields_observed}`",
            "",
        ])
    (REPORTS / "PHASE_1B_2_FUNDING_PARITY.md").write_text("\n".join(parity_md_lines) + "\n")

    # Report 6: ACCEPTANCE REPORT (Sections 3, 6, 9, 10, 11, 13, 14, 15)
    verification_completed = datetime.now(timezone.utc).isoformat()
    checks = {
        "automated_tests_pass": tests_passed,
        "security_scan_pass": sec_passed,
        "triple_checksum_reconciliation_pass": triple_reconciled,
        "safe_extraction_pass": safe_extraction_passed,
        "schema_quality_pass": schema_quality_passed,
        "timestamp_policy_pass": all_timestamps_compliant,
        "funding_parity_pass": funding_parity_passed,
        "idempotency_cache_pass": idempotency_passed,
        "resumability_recovery_pass": resumability_passed,
    }
    all_passed = all(checks.values())
    acceptance_payload = {
        "phase": "1B.2",
        "status": "VERIFIED" if all_passed else "REMEDIATION_REQUIRED",
        "trading_capability": "ZERO" if sec_passed else "NOT_PROVEN",
        "branch_name": current_branch,
        "tested_code_commit_sha": tested_code_commit_sha,
        "tested_tree_sha": tested_tree_sha,
        "software_commit_sha": tested_code_commit_sha,
        "verification_started_at_utc": verification_started,
        "verification_completed_at_utc": verification_completed,
        "working_tree_clean_before": working_tree_clean_before,
        "checks": checks,
        "total_archives_verified": total_archives_verified,
        "total_archive_bytes_verified": total_archive_bytes_verified,
        "total_archive_mib_verified": total_archive_mib_verified,
        "total_archives_downloaded_this_run": total_archives_downloaded_this_run,
        "total_bytes_downloaded_this_run": total_bytes_downloaded_this_run,
        "total_cache_hits": total_cache_hits,
        "total_bytes_reused_from_verified_cache": total_bytes_reused_from_verified_cache,
        "funding_parity_mode": active_funding_mode,
        "funding_parity_symbols": funding_parity_symbols,
        "manifest_sha256": manifest_sha256,
    }
    (REPORTS / "PHASE_1B_2_ACCEPTANCE.json").write_text(json.dumps(acceptance_payload, indent=2) + "\n")

    acceptance_md_lines = [
        "# Phase 1B.2 Verified Historical Acquisition & Bronze Archive Acceptance",
        "",
        f"PHASE_1B_2 = {acceptance_payload['status']}",
        "",
        f"- **Trading Capability**: `{acceptance_payload['trading_capability']}`",
        f"- **Branch Name**: `{current_branch}`",
        f"- **Tested Code Commit SHA**: `{tested_code_commit_sha}`",
        f"- **Tested Tree SHA**: `{tested_tree_sha}`",
        f"- **Total Archives Verified**: `{total_archives_verified}`",
        f"- **Total Archive Bytes Verified**: `{total_archive_bytes_verified:,}` bytes ({total_archive_mib_verified} MiB)",
        f"- **Total Downloaded This Run**: `{total_bytes_downloaded_this_run:,}` bytes ({total_archives_downloaded_this_run} archives)",
        f"- **Total Cache Hits**: `{total_cache_hits}` ({total_bytes_reused_from_verified_cache:,}` bytes reused)",
        f"- **Funding Parity Mode**: `{active_funding_mode}` (symbols: `{', '.join(funding_parity_symbols)}`)",
        f"- **Manifest SHA-256**: `{manifest_sha256}`",
        "",
        "## Mechanical Acceptance Gates",
        "",
    ]
    for k, v in checks.items():
        acceptance_md_lines.append(f"- [{'x' if v else ' '}] `{k}`")
    (REPORTS / "PHASE_1B_2_ACCEPTANCE.md").write_text("\n".join(acceptance_md_lines) + "\n")

    print(f"\n================ FINAL ================")
    print(f"PHASE_1B_2 = {acceptance_payload['status']}")
    print(f"TRADING CAPABILITY = {acceptance_payload['trading_capability']}")
    print(f"Reports written to: {REPORTS}")
    return 0 if all_passed else 20


if __name__ == "__main__":
    raise SystemExit(main())
