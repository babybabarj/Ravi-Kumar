# Binance Additional Dataset Candidates (Discovery Only)

During S3 prefix inspection of `data.binance.vision/data/futures/um/`, several non-canonical datasets were identified. These remain **strictly out of canonical Phase 1B scope** until separately reviewed and approved.

| Dataset Name | Observed Path | Cadence | Apparent Coverage | Potential Future Value | Known Caveats | Recommendation |
|---|---|---|---|---|---|---|
| **metrics** | `data/futures/um/daily/metrics/{symbol}/` | Daily | 2021 to present | Open interest, top trader long/short ratio, taker buy/sell volume ratio. High alpha potential for regime shift models. | Frequent schema changes, reported checksum inconsistencies (#498), coarse 5m cadence. | **DEFER_TO_PHASE_2** (Evaluate after Phase 1B core engine freeze). |
| **bookTicker** | `data/futures/um/{daily\|monthly}/bookTicker/{symbol}/` | Daily & Monthly | 2023 to present | Best bid/ask tick-level stream for order book reconstruction and micro-slippage modeling. | Giant file sizes (>1 GB per month). Heavy bandwidth footprint. | **DEFER_TO_PHASE_1C** (Evaluate for high-frequency execution backtests). |
| **bookDepth** | `data/futures/um/daily/bookDepth/{symbol}/` | Daily | 2024 to present | Deep level-2 snapshot deltas for order book simulation. | Extremely heavy; irregular archive structure; reported timestamp anomalies (#381). | **EXCLUDE_FOR_NOW** (Phase 1A live order book stream provides canonical real-time truth). |
| **liquidationSnapshot** | `data/futures/um/daily/liquidationSnapshot/` | Daily | Sporadic | Realized liquidation event tape. Useful for squeeze detection. | Sparse coverage; schema differences between daily dumps and WebSocket feeds. | **DEFER_TO_PHASE_2** (Secondary signal source). |

