from __future__ import annotations

import json
from pathlib import Path
import pytest

from tools.analyze_source_gaps import generate_forensics_reports

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"


def test_gap_forensics_dynamic_metrics() -> None:
    """Verify gap forensics derives metrics mechanically without hardcoded values."""
    if not (ROOT / "artifacts" / "research" / "silver_v3" / "BTCUSDT-resampled-1h-v3.1.0.parquet").is_file():
        pytest.skip("Round 3B parent artifact BTCUSDT-resampled-1h-v3.1.0.parquet not present")
    rep = generate_forensics_reports(write_reports=False)
    assert rep["dataset_version"] == "v3.1.0"
    assert rep["unsupported_causal_claims"] == 0

    btc = rep["symbols"]["BTCUSDT"]
    assert btc["total_hours"] == 35064
    assert btc["invalid_hours_count"] == 440
    assert btc["valid_hours_count"] == 35064 - 440
    assert btc["valid_ratio_pct"] == 98.75
    assert btc["by_source"]["perp"] == 0  # 0 perp gaps invariant

    eth = rep["symbols"]["ETHUSDT"]
    assert eth["total_hours"] == 35064
    assert eth["invalid_hours_count"] == 248
    assert eth["valid_hours_count"] == 35064 - 248
    assert eth["by_source"]["perp"] == 0


def test_gap_forensics_markdown_has_zero_unsupported_causal_claims() -> None:
    """Verify markdown report contains strictly descriptive language and no unsupported claims."""
    md_file = REPORTS_DIR / "ROUND3B_GAP_FORENSICS.md"
    assert md_file.is_file(), "Forensics markdown must exist"

    text = md_file.read_text(encoding="utf-8").lower()
    forbidden_causal_phrases = [
        "caused by",
        "caused the gap",
        "server load caused",
        "ftx collapse caused",
        "maintenance caused",
    ]
    for phrase in forbidden_causal_phrases:
        assert phrase not in text, f"Found forbidden unsupported causal claim: '{phrase}'"
