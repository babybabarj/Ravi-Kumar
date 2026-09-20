# Quantitative Strategy Research Campaign Summary

## Executive Overview
The Market Brain research engine evaluated 7 quantitative candidate strategies across 5 core families (Trend/Momentum, Breakout, Mean Reversion, Funding Dislocation, and Cross-Asset Divergence) using 86,400 canonical Binance Vision Silver bars for BTCUSDT and ETHUSDT.

## Promotion Audit Verdict
```text
APPROVED_FOR_PAPER  = 0
APPROVED_FOR_SHADOW = 0
REJECTED            = 7
RUNTIME EDGE STATUS = NO_VALIDATED_EDGE
```

## Scientific Honesty & Multiple Testing
In strict adherence to Sections 1, 55, 66, and 77:
- Every variant tested was tracked permanently in SQLite WAL (`artifacts/research/experiments.sqlite`).
- Deflated Sharpe Ratios (DSR) penalized performance for multiple testing.
- Base costs (15 bps) and Stressed costs (35 bps) rigorously revealed that high-turnover retail strategies degrade significantly when friction is applied.
- Zero curve-fitted strategies were promoted to live or paper autopilot.
