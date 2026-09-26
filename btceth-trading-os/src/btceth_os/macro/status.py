"""
Canonical Macro / News Intelligence Status Aggregator (§31, §32, §33).
Ensures top-level status is never contradictory.
"""
from __future__ import annotations

from typing import Any, Dict


def aggregate_macro_status(
    r1_4_code_status: str = "VERIFIED",
    r1_4_source_status: str = "SOURCE_GATE_PENDING",
) -> dict[str, str]:
    """
    Compute unified top-level status for NEWS/MACRO-1A (§31-§33, §52, §53).

    Rules:
    - If code status == 'VERIFIED' and source status == 'VERIFIED':
      news_macro_1a_status = 'VERIFIED'
      news_macro_1a_r1_4_status = 'VERIFIED'
    - If code status == 'VERIFIED' and source status in ('BLS_DATA_API_RATE_LIMITED', 'SOURCE_GATE_PENDING', 'RATE_LIMITED'):
      news_macro_1a_status = 'SOURCE_GATE_PENDING'
      news_macro_1a_r1_4_status = 'SOURCE_GATE_PENDING'
    - Otherwise:
      news_macro_1a_status = 'REMEDIATION_REQUIRED'
      news_macro_1a_r1_4_status = 'REMEDIATION_REQUIRED'
    """
    c_status = r1_4_code_status.strip().upper()
    s_status = r1_4_source_status.strip().upper()

    if c_status == "VERIFIED" and s_status == "VERIFIED":
        top_status = "VERIFIED"
        r1_4_status = "VERIFIED"
    elif c_status == "VERIFIED" and s_status in (
        "BLS_DATA_API_RATE_LIMITED",
        "SOURCE_GATE_PENDING",
        "RATE_LIMITED",
    ):
        top_status = "SOURCE_GATE_PENDING"
        r1_4_status = "SOURCE_GATE_PENDING"
    else:
        top_status = "REMEDIATION_REQUIRED"
        r1_4_status = "REMEDIATION_REQUIRED"

    return {
        "news_macro_1a_status": top_status,
        "news_macro_1a_r1_4_status": r1_4_status,
        "news_macro_1a_r1_4_code_status": c_status,
        "news_macro_1a_r1_4_source_status": s_status,
        # Uppercase alias support
        "NEWS_MACRO_1A_STATUS": top_status,
        "NEWS_MACRO_1A_R1_4_STATUS": r1_4_status,
        "NEWS_MACRO_1A_R1_4_CODE_STATUS": c_status,
        "NEWS_MACRO_1A_R1_4_SOURCE_STATUS": s_status,
    }
