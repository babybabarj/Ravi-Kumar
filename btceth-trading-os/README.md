# BTCETH Trading OS

Read-only public market-data collection workspace. No order placement, account trading, withdrawals, transfers, leverage changes, or position modification.

Verified milestones: Phase 1A live public capture, Phase 1B.0 data contracts and provenance, Phase 1B.1 official archive discovery/planning, Phase 1B.2 streamed archive retrieval, and Phase 1B.3 historical RAW-object cataloguing.

The Phase 1B.2 downloader stores only checksum-verified, ZIP-verified archive bytes under a physical-SHA-256 filename. It preserves a retrieval receipt and never promotes a partial download as RAW evidence. Phase 1B.3 records those immutable objects and receipts in a dedicated SQLite WAL catalog. Run `tools/mac_phase1b3_verify.sh` to execute the current full regression, safety, public-download, and catalog acceptance gate.
