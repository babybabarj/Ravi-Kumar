from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from ..core import canonical_json


@dataclass(frozen=True)
class StrategyReportCard:
    strategy_id: str
    family: str
    symbol: str
    hypothesis: str
    dataset_logical_sha256: str
    code_commit: str
    parameters: dict[str, Any]
    
    # Sample metrics
    train_bars: int
    test_bars: int
    out_of_sample_trades: int
    
    # Financial metrics
    gross_return: float
    net_return_base: float
    net_return_stressed: float
    annualized_sharpe: float
    annualized_sortino: float
    max_drawdown: float
    profit_factor: float
    win_rate: float
    net_expectancy_bps: float
    
    # Robustness & Statistical Rigor
    parameter_stability_pct: float
    deflated_sharpe_ratio: float
    pbo: float
    top1_trade_share_pct: float
    bootstrap_lower_ci_bps: float
    
    # Promotion Gate
    status: str  # APPROVED_FOR_PAPER, APPROVED_FOR_SHADOW, REJECTED
    rejection_reasons: list[str]
    created_at_utc: str = ""

    def __post_init__(self) -> None:
        if not self.created_at_utc:
            object.__setattr__(self, "created_at_utc", datetime.now(timezone.utc).isoformat())

    def to_markdown(self) -> str:
        status_badge = "✅ APPROVED FOR PAPER" if self.status == "APPROVED_FOR_PAPER" else (
            "⚠️ APPROVED FOR SHADOW" if self.status == "APPROVED_FOR_SHADOW" else "❌ REJECTED"
        )
        reasons_block = "\n".join(f"- {r}" for r in self.rejection_reasons) if self.rejection_reasons else "- None (All criteria satisfied)"
        
        md = f"""# Strategy Report Card: `{self.strategy_id}`

**Status**: {status_badge}  
**Family**: `{self.family}`  
**Symbol**: `{self.symbol}`  
**Evaluation Timestamp**: `{self.created_at_utc}`  
**Code Commit**: `{self.code_commit}`  
**Dataset SHA-256**: `{self.dataset_logical_sha256[:16]}...`

---

## 1. Core Hypothesis
> {self.hypothesis}

**Parameters**:
```json
{json.dumps(self.parameters, indent=2)}
```

---

## 2. Empirical Performance Summary (Out-of-Sample)

| Metric | Measured Value | Validation Threshold | Status |
| :--- | :--- | :--- | :--- |
| **OOS Trades** | {self.out_of_sample_trades} | $\\ge 30$ | {"PASS" if self.out_of_sample_trades >= 30 else "FAIL"} |
| **Gross Return** | {self.gross_return:+.2%} | N/A | INFO |
| **Net Return (Base Costs)** | {self.net_return_base:+.2%} | $> 0.00\\%$ | {"PASS" if self.net_return_base > 0 else "FAIL"} |
| **Net Return (Stressed Costs)** | {self.net_return_stressed:+.2%} | $> 0.00\\%$ | {"PASS" if self.net_return_stressed > 0 else "FAIL"} |
| **Annualized Sharpe** | {self.annualized_sharpe:.2f} | $\\ge 1.00$ | {"PASS" if self.annualized_sharpe >= 1.0 else "FAIL"} |
| **Annualized Sortino** | {self.annualized_sortino:.2f} | $\\ge 1.30$ | {"PASS" if self.annualized_sortino >= 1.3 else "FAIL"} |
| **Max Drawdown** | {self.max_drawdown:.2%} | $\\le 15.00\\%$ | {"PASS" if self.max_drawdown <= 0.15 else "FAIL"} |
| **Profit Factor** | {self.profit_factor:.2f} | $\\ge 1.25$ | {"PASS" if self.profit_factor >= 1.25 else "FAIL"} |
| **Win Rate** | {self.win_rate:.1%} | N/A | INFO |
| **Net Expectancy (bps/trade)**| {self.net_expectancy_bps:+.1f} bps | $\\ge +2.0$ bps | {"PASS" if self.net_expectancy_bps >= 2.0 else "FAIL"} |

---

## 3. Statistical Rigor & Overfitting Diagnostics

| Test / Diagnostic | Result | Acceptance Limit | Outcome |
| :--- | :--- | :--- | :--- |
| **Deflated Sharpe Ratio (DSR)** | {self.deflated_sharpe_ratio:.3f} | $\\ge 0.95$ ($p < 0.05$) | {"PASS" if self.deflated_sharpe_ratio >= 0.95 else "FAIL"} |
| **Probability of Backtest Overfit (PBO)** | {self.pbo:.2f} | $\\le 0.50$ | {"PASS" if self.pbo <= 0.50 else "FAIL"} |
| **Parameter Neighborhood Stability** | {self.parameter_stability_pct:.1%} | $\\ge 60.0\\%$ | {"PASS" if self.parameter_stability_pct >= 0.60 else "FAIL"} |
| **Top 1% Trade Concentration** | {self.top1_trade_share_pct:.1%} | $\\le 35.0\\%$ | {"PASS" if self.top1_trade_share_pct <= 0.35 else "FAIL"} |
| **Bootstrap Expectancy 95% Lower CI** | {self.bootstrap_lower_ci_bps:+.1f} bps | $\\ge 0.0$ bps | {"PASS" if self.bootstrap_lower_ci_bps >= 0.0 else "FAIL"} |

---

## 4. Promotion Gate Findings & Decision

**Final Tier**: `{self.status}`

### Recorded Findings / Deficiencies:
{reasons_block}

---
*Report generated automatically by BTCETH Trading OS Market Brain Research Engine.*
"""
        return md

    def save(self, output_dir: Path | str) -> tuple[Path, Path]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        md_path = out / f"{self.strategy_id}.md"
        json_path = out / f"{self.strategy_id}.json"

        md_path.write_text(self.to_markdown(), encoding="utf-8")
        
        card_dict = {
            "strategy_id": self.strategy_id,
            "family": self.family,
            "symbol": self.symbol,
            "hypothesis": self.hypothesis,
            "dataset_logical_sha256": self.dataset_logical_sha256,
            "code_commit": self.code_commit,
            "parameters": self.parameters,
            "out_of_sample_trades": self.out_of_sample_trades,
            "gross_return": self.gross_return,
            "net_return_base": self.net_return_base,
            "net_return_stressed": self.net_return_stressed,
            "annualized_sharpe": self.annualized_sharpe,
            "annualized_sortino": self.annualized_sortino,
            "max_drawdown": self.max_drawdown,
            "profit_factor": self.profit_factor,
            "win_rate": self.win_rate,
            "net_expectancy_bps": self.net_expectancy_bps,
            "parameter_stability_pct": self.parameter_stability_pct,
            "deflated_sharpe_ratio": self.deflated_sharpe_ratio,
            "pbo": self.pbo,
            "top1_trade_share_pct": self.top1_trade_share_pct,
            "bootstrap_lower_ci_bps": self.bootstrap_lower_ci_bps,
            "status": self.status,
            "rejection_reasons": self.rejection_reasons,
            "created_at_utc": self.created_at_utc,
        }
        json_path.write_text(json.dumps(card_dict, indent=2) + "\n", encoding="utf-8")
        return md_path, json_path
