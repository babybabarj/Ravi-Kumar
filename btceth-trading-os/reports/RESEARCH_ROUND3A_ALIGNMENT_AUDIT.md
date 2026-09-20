# Research Round 3A: Source Alignment & Missingness Audit

## 1. Executive Summary
This audit details the source series timestamp alignment, missing data handling, and official archive provenance verification for Dataset v3.1.0 in the BTCETH Trading OS.

---

## 2. Official Binance Vision Archive Provenance

### Verification of `premiumIndexKlines` vs `premiumPriceKlines`
- Direct HEAD probes executed against `data.binance.vision`:
  - `https://data.binance.vision/data/futures/um/monthly/premiumIndexKlines/BTCUSDT/1m/BTCUSDT-1m-2020-01.zip` $\to$ **`200 OK`**
  - `https://data.binance.vision/data/futures/um/monthly/premiumIndexKlines/BTCUSDT/1m/BTCUSDT-1m-2020-01.zip.CHECKSUM` $\to$ **`200 OK`**
  - `https://data.binance.vision/data/futures/um/monthly/premiumPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2020-01.zip` $\to$ **`404 Not Found`**
- **Conclusion**: `premiumIndexKlines` is the authoritative Binance Vision object path. The provenance is formally recorded in [`reports/RESEARCH_ROUND3A_DATA_MANIFEST.json`](file:///Users/ravi/btceth-phase1a-mac/btceth-trading-os/reports/RESEARCH_ROUND3A_DATA_MANIFEST.json).

---

## 3. Elimination of Silent Fallback Substitutions

In the defective Round 3 resampler:
```python
m_close = mark_lookup.get(last_m_ts, h_perp_close)    # Substituted traded close for mark price
idx_close = index_lookup.get(last_m_ts, h_spot_close)  # Substituted spot close for index price
prem_close = premium_lookup.get(last_m_ts, 0.0)        # Substituted zero for premium index
```

### Remediation in Dataset v3.1.0
- Replaced with explicit nullable types and availability flags:
  `spot_available`, `perp_available`, `mark_available`, `index_available`, `premium_available`.
- If an observation is missing, its value remains `None`.
- Policy: `FAIL_CLOSED_NO_FALLBACK`.
- Strategies requiring a reference price check availability; if unavailable, the bar is marked `BAR_INVALID_FOR_STRATEGY` and rejected.

---

## 4. Cross-Asset Alignment & Isolation

### Remediation of `eth_dev[i]` Index Leak
- In Round 3, `STRUCT_C1_BTCETH_REL_FUNDING` used:
  `lambda bars, i: abs(bars[i].funding_rate - eth_dev[i].funding_rate) >= 0.0010`
  When evaluating 2023 validation bars, `i` indexed into `btc_val` while referencing `eth_dev` (2020–2022).
- **Remediation**:
  Replaced with an explicit timestamp join using `ts_event_ns` as key:
  - `btc_dev` joined with `eth_dev`
  - `btc_val` joined with `eth_val`
  - Strict isolation: zero cross-generational contamination.

---

## 5. Dataset v3.1.0 Quality Metrics
- Total Hourly Timestamps (48 Months): 35,064
- Fully Valid Hours (all 5 series present): 34,624 (98.75%)
- Incomplete / Gap Hours: 440 (1.25%)
- Logical SHA-256: `a085cf7f69d03357277e7ae6c5a3d82fbb6b684a936576c536b53060b758f930`
