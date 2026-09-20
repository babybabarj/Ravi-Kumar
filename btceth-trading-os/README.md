# BTCETH Trading OS

Read-only public market-data collection workspace. No order placement, account trading, withdrawals, transfers, leverage changes, or position modification.

Verified milestones: Phase 1A live public capture, Phase 1B.0 data contracts and provenance, Phase 1B.1 official archive discovery/planning, and Phase 1B.2 streamed archive retrieval.

The Phase 1B.2 downloader stores only checksum-verified, ZIP-verified archive bytes under a physical-SHA-256 filename. It preserves a retrieval receipt and never promotes a partial download as RAW evidence. Run `tools/mac_phase1b2_verify.sh` to execute its full regression, safety, and public-archive acceptance gate.
