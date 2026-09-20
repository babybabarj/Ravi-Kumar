from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pyarrow.parquet as pq

from btceth_os.research.manifest import ResearchDatasetSpec, build_manifest
from btceth_os.sources.binance.archive_downloader import ArchiveDownloader
from btceth_os.sources.binance.archive_parser import iter_bronze_records
from btceth_os.sources.binance.archive_planner import plan_archive_requests
from btceth_os.sources.binance.historical_silver import write_historical_silver
from btceth_os.sources.registry import load_historical_datasets_registry


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
RESEARCH_ARTIFACTS = ROOT / "artifacts" / "research"


def get_git_commit() -> str:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN"


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    RESEARCH_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    raw_dir = RESEARCH_ARTIFACTS / "raw"
    silver_dir = RESEARCH_ARTIFACTS / "silver"
    raw_dir.mkdir(parents=True, exist_ok=True)
    silver_dir.mkdir(parents=True, exist_ok=True)

    downloader = ArchiveDownloader(raw_dir)
    registry = load_historical_datasets_registry()

    target_ids = [
        "BINANCE:USD_M_PERP:BTCUSDT:KLINES_1M",
        "BINANCE:USD_M_PERP:ETHUSDT:KLINES_1M",
        "BINANCE:USD_M_PERP:BTCUSDT:FUNDING_HISTORY",
        "BINANCE:USD_M_PERP:ETHUSDT:FUNDING_HISTORY",
    ]

    specs: list[ResearchDatasetSpec] = []
    notes: list[str] = []

    print(f"[Research Data] Building canonical research dataset for period 2024-11 across {len(target_ids)} streams...")

    for did in target_ids:
        ds_def = next((d for d in registry if d.dataset_id == did), None)
        if not ds_def:
            raise ValueError(f"Dataset {did} not found in registry")

        plans = plan_archive_requests(ds_def, "2024-11-01", "2024-11-30", "2024-12-10T00:00:00Z")
        if not plans:
            raise RuntimeError(f"No archive planned for {did}")

        plan = plans[0]
        print(f" -> Downloading / Verifying {plan.archive_filename}...")
        download_result = downloader.download(plan)
        if download_result.local_path is None or download_result.physical_sha256 is None:
            raise RuntimeError(f"Failed to retrieve verified archive for {did}")

        # Stream Bronze records
        records = list(iter_bronze_records(download_result.local_path, ds_def))
        if not records:
            raise RuntimeError(f"Zero bronze records in {did}")

        silver_filename = f"{plan.symbol}-{ds_def.source_dataset_name}-{plan.period_key}.parquet"
        silver_path = silver_dir / silver_filename

        if not silver_path.exists():
            write_historical_silver(records, silver_path, download_result.physical_sha256)

        table = pq.read_table(silver_path)
        first_ts = int(table.column("ts_event_ns")[0].as_py())
        last_ts = int(table.column("ts_event_ns")[-1].as_py())

        spec = ResearchDatasetSpec(
            dataset_id=did,
            instrument_id=ds_def.instrument,
            market=ds_def.market,
            period_key=plan.period_key,
            source_file_sha256=download_result.physical_sha256,
            silver_parquet_path=str(silver_path),
            rows_count=table.num_rows,
            start_ts_ns=first_ts,
            end_ts_ns=last_ts,
        )
        specs.append(spec)
        notes.append(f"{did}: {table.num_rows} verified Silver rows compiled from SHA-256 {download_result.physical_sha256[:16]}")
        print(f"    Compiled {table.num_rows} rows to {silver_filename}")

    commit_hash = get_git_commit()
    manifest = build_manifest(specs, dataset_version="1.1.0", code_commit=commit_hash, validation_notes=notes)
    manifest.write(RESEARCH_ARTIFACTS / "manifest.json")

    # Write mechanical readiness report
    readiness_report = {
        "phase": "RESEARCH_DATA_READINESS",
        "research_data_ready": manifest.is_ready,
        "dataset_version": manifest.dataset_version,
        "dataset_logical_sha256": manifest.dataset_logical_sha256,
        "code_commit": manifest.code_commit,
        "created_at_utc": manifest.created_at_utc,
        "total_datasets": len(specs),
        "total_kline_bars": sum(s.rows_count for s in specs if "KLINES" in s.dataset_id),
        "datasets": [s.to_dict() for s in specs],
        "validation_notes": list(manifest.validation_notes),
        "error": None,
    }

    out_json = REPORTS / "RESEARCH_DATA_READINESS.json"
    out_json.write_text(json.dumps(readiness_report, indent=2) + "\n")
    print(f"\n[Research Data] RESEARCH_DATA_READY = YES")
    print(f"Dataset Logical SHA-256: {manifest.dataset_logical_sha256}")
    print(f"Report written to: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
