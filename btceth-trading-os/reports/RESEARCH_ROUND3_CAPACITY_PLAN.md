# Research Round 3: Storage & Resource Capacity Plan

## 1. System Storage Inventory
- **Host OS**: macOS (Apple Silicon / Darwin)
- **Local Filesystem Mount**: `/System/Volumes/Data`
- **Total Filesystem Capacity**: 228 GiB
- **Available Free Disk Space**: **7.0 GiB** (verified via `df -h`)
- **Permitted Research Footprint**: $\le 2.0\text{ GiB}$ (preserving $\ge 5.0\text{ GiB}$ safety cushion)

---

## 2. Dataset Sizing & Format Strategy

### Parquet vs Tick / CSV Storage Comparison
| Data Format | Compression | Estimated Size (2020–2023, 48 Mo) | Feasibility |
| :--- | :--- | :--- | :--- |
| **Raw L2 Tick/Trades** | Uncompressed CSV | $> 250\text{ GiB}$ | **REJECTED** (Exceeds disk limit) |
| **1m Raw CSV Archives** | Plaintext CSV | $\approx 4.5\text{ GiB}$ | **REJECTED** (Too close to limit) |
| **1m Compressed Parquet** | Snappy / Dictionary | $\approx 650\text{ MB}$ | **APPROVED** ($< 10\%$ of free disk) |
| **8h Resampled Reference** | Snappy Parquet | $\approx 15\text{ MB}$ | **APPROVED** |

### Projected Storage Allocation for Round 3:
1. **`CORE_PRICE_HISTORY` (Spot & Perp 1m Klines, 2020–2023)**:
   - BTCUSDT Spot 1m: $\approx 98\text{ MB}$
   - BTCUSDT Perp 1m: $\approx 98\text{ MB}$
   - ETHUSDT Spot 1m: $\approx 95\text{ MB}$
   - ETHUSDT Perp 1m: $\approx 95\text{ MB}$
   - Subtotal: $\approx 386\text{ MB}$
2. **`CARRY_HISTORY` (Funding Settlements, 2020–2023)**:
   - BTCUSDT Funding: $\approx 40\text{ KB}$
   - ETHUSDT Funding: $\approx 40\text{ KB}$
   - Subtotal: $< 1\text{ MB}$
3. **`REFERENCE_PRICE_HISTORY` (Official Mark, Index, Premium 1m Klines, 2020–2023)**:
   - BTCUSDT Mark / Index / Premium: $\approx 140\text{ MB}$
   - ETHUSDT Mark / Index / Premium: $\approx 140\text{ MB}$
   - Subtotal: $\approx 280\text{ MB}$
4. **Temporary ZIP Download Cache (`artifacts/research/raw_zips/`)**:
   - Downloaded in streaming chunks with immediate extraction and cleanup of non-essential archives: $\approx 200\text{ MB}$

**Total Projected Footprint**: $\approx 870\text{ MB}$ ($\approx 12.4\%$ of available disk space, leaving $> 6.1\text{ GiB}$ free).

---

## 3. Memory & Computational Bounds
- **RAM Available**: 16 GiB unified memory.
- **Data Resampling**:
  - Full 1m series (approx. 2.1 million rows per series over 4 years) loaded via PyArrow zero-copy IPC.
  - Resampling to 1h, 8h, 24h intervals for structural carry analysis consumes $< 250\text{ MB}$ heap.
  - CPU parallelization: 8 workers using Python `ThreadPoolExecutor` for network I/O.
