# BTCETH Trading OS

Read-only public market-data collection workspace. No order placement, account trading, withdrawals, transfers, leverage changes, or position modification.

Verified milestones: Phase 1A live public capture, Phase 1B.0 data contracts and provenance, Phase 1B.1 official archive discovery/planning, Phase 1B.2 streamed archive retrieval, Phase 1B.3 historical RAW-object cataloguing, Phase 1B.4 strict Bronze parsing, and Phase 1B.5 immutable historical Silver output.

The Phase 1B.2 downloader stores only checksum-verified, ZIP-verified archive bytes under a physical-SHA-256 filename. It preserves a retrieval receipt and never promotes a partial download as RAW evidence. Phase 1B.3 records those immutable objects and receipts in a dedicated SQLite WAL catalog. Phase 1B.4 streams CSV-in-ZIP Bronze records with strict recognized schemas and exact financial values. Phase 1B.5 writes immutable, source-specific Parquet with Decimal128 values and raw member/row provenance; quality, gap, and reconciliation checks report problems without inventing market data. Run `python tools/verify_phase1b5.py` from the project environment for the full regression, safety, public-download, and Silver acceptance gate.

Offline research is deterministic and cannot access an exchange account. Use `python tools/run_walk_forward.py INPUT.parquet OUTPUT.json --train-bars 10000 --test-bars 2000 --lookbacks 30,60,120 --taker-fee-bps FEE --slippage-bps SLIPPAGE` with costs you have evidenced for the market and period under study. The command refuses to overwrite reports and evaluates each selected lookback only on its next out-of-sample block; it does not predict or promise profitability.

The local safety gate fails closed for stale signals, failed data-quality checks, unresolved gaps, drawdown, daily loss, and position limits. Paper fills are local Decimal calculations only; no exchange order or account functionality exists.

Run `python -m btceth_os.dashboard` and open `http://127.0.0.1:8000/` to view the read-only localhost dashboard. Until a local process writes `artifacts/dashboard/state.json`, it deliberately displays degraded/not-ready status instead of inventing market state, signals, or P&L.
