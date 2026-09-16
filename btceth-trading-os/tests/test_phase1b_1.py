from __future__ import annotations

import json
from pathlib import Path
import pytest

from btceth_os.sources.registry import load_historical_datasets_registry


@pytest.fixture(scope="module")
def root_dir():
    return Path(__file__).resolve().parents[1]


def test_twenty_canonical_datasets_resolved(root_dir):
    datasets = load_historical_datasets_registry(root_dir / "config" / "historical_datasets.yaml")
    assert len(datasets) == 20, f"Expected exactly 20 canonical datasets, got {len(datasets)}"

    for d in datasets:
        assert d.archive_support_status == "VERIFIED_TRUE", f"{d.dataset_id}: invalid archive_support_status"
        assert d.monthly_support == "VERIFIED_TRUE", f"{d.dataset_id}: monthly_support must be VERIFIED_TRUE"
        assert d.checksum_support == "VERIFIED_TRUE", f"{d.dataset_id}: checksum_support must be VERIFIED_TRUE"

        if "FUNDING" in d.dataset_id:
            assert d.daily_support == "VERIFIED_FALSE", f"{d.dataset_id}: daily_support must be VERIFIED_FALSE"
            assert d.rest_support == "VERIFIED_TRUE", f"{d.dataset_id}: rest_support must be VERIFIED_TRUE"
            assert d.raw_format == "csv.zip", f"{d.dataset_id}: raw_format must be csv.zip"
        else:
            assert d.daily_support == "VERIFIED_TRUE", f"{d.dataset_id}: daily_support must be VERIFIED_TRUE"
            assert d.rest_support == "NOT_APPLICABLE", f"{d.dataset_id}: rest_support must be NOT_APPLICABLE"

        if "PREMIUM" in d.dataset_id:
            assert d.source_dataset_name == "premiumIndexKlines", f"{d.dataset_id}: must use premiumIndexKlines"

        if d.market == "spot":
            assert d.source_timestamp_policy.get("type") == "date_versioned"
        elif d.market == "usdm":
            assert d.source_timestamp_policy.get("type") == "fixed_ms"
            assert d.source_timestamp_policy.get("unit") == "ms"


def test_discovery_reports_and_probe_budget(root_dir):
    reports = root_dir / "reports"
    required_reports = [
        "BINANCE_ARCHIVE_DISCOVERY.json",
        "BINANCE_ARCHIVE_DISCOVERY.md",
        "BINANCE_ARCHIVE_PATH_MATRIX.md",
        "BINANCE_ARCHIVE_KNOWN_ISSUES.md",
        "BINANCE_ADDITIONAL_DATASET_CANDIDATES.md",
    ]
    for r in required_reports:
        p = reports / r
        assert p.is_file(), f"Missing required discovery report: {p}"
        assert p.stat().st_size > 0, f"Report {p} is empty"

    disc_data = json.loads((reports / "BINANCE_ARCHIVE_DISCOVERY.json").read_text())
    results = disc_data.get("results", {})

    total_bytes = results.get("total_probe_download_bytes", 0)
    assert total_bytes <= 50 * 1024 * 1024, f"Probe download budget exceeded: {total_bytes} bytes"
    assert total_bytes > 0, "No probe downloads recorded"

    spot_verif = results.get("spot_timestamp_verification", {})
    assert spot_verif.get("transition_verified") is True
    assert spot_verif.get("pre_2025", {}).get("digits") == 13
    assert spot_verif.get("post_2025", {}).get("digits") == 16

    usdm_verif = results.get("usdm_timestamp_verification", {})
    assert usdm_verif.get("fixed_ms_verified") is True
    assert usdm_verif.get("klines_2025_01_01", {}).get("digits") == 13
    assert usdm_verif.get("funding_rate_2024_11", {}).get("digits") == 13
