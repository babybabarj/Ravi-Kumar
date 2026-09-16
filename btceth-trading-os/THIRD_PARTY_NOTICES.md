# THIRD-PARTY SOFTWARE NOTICES AND ATTRIBUTION

This project incorporates, adapts, or references components from several open-source projects.
This document provides legal attribution, provenance records, and license boundaries in accordance with the terms of each respective license.

---

## Summary License & Provenance Matrix

| Project | Local Archive File | Archive SHA-256 Digest | Upstream License | Intended BTCETH Role | Reuse Mode | Boundary Rule |
|---|---|---|---|---|---|---|
| **Passivbot** | `passivbot-master.zip` | `bad79d36587b3812481e343c4a47c76ca3ce6d527e8ba42e88bfdc1a88e6c468` | The Unlicense (Public Domain) | Archive planning, discovery, checksum parsing, month/day boundaries | Selective Adaptation | Adapt selected functions with attribution; upgrade to streaming `.part` downloads and strict exact decimal typing. |
| **Jesse** | `jesse-master.zip` | `de72c7803b0f26efd2d0a555285e9e33040de1b72b0cda001665640f566008c0` | MIT License | Strategy research laboratory, hypothesis testing, research backtests | Python Dependency & Export Target | Jesse is an external consumer; canonical data will be exported to Jesse format. Does not own canonical truth. |
| **NautilusTrader** | `nautilus_trader-develop.zip` | `7df7feb2c7b8f861b699d317fa4e997b56370ea505c6b40a20219e69eba7e6d3` | GNU Lesser General Public License v3.0 (LGPL-3.0) | Production simulation, execution models, event store, Parquet catalog target | External Dependency & Data Target | LGPL boundary: Used via standard dynamic linking / public Python API. No proprietary modifications to LGPL internals. |
| **Hummingbot** | `hummingbot-master.zip` | `660c4f5cc2f5f9aa6fb5232b002998f566039cef9568884b9c114b95dd5cb334` | Apache License 2.0 | Specialist order-book synchronization, diff buffering, gap detection | Selective Algorithmic Adaptation | Adapt pure algorithms with attribution in headers; do not import massive monolith dependency. |
| **Freqtrade** | `freqtrade-develop.zip` | `196c5ed0651e83db3caa59acf4e5ed63c7c769b761e496d98aa417e59c470e8f` | GNU General Public License v3.0 (GPL-3.0) | Independent strategy challenger & backtest reference | External Reference & Challenger Only | **Strict GPL Boundary:** Do NOT copy, link, or incorporate GPL code into internal core components. Run only as external tool. |
| **OctoBot** | `OctoBot-master.zip` | `a1584b1c78c6f1305c0fbcb7c0be38175fa76b8abad7f0014f5e2bd515dfc5fa` | GNU General Public License v3.0 (GPL-3.0) | Architecture & evaluation pipeline reference | Architectural Reference Only | **Strict GPL Boundary:** Do NOT copy code. Reference for design concepts and UX only. |
| **CCXT** | `ccxt-master.zip` | `7f3e419437b6a1632b8cb654102a44e855853f226148b6ed7dfcbcdd61372638` | MIT License | Exchange abstraction, exact precision utilities (`Precise`), typed exchange errors | Python Dependency | Use library functions (`Precise`, error hierarchy) as a dependency. Never the sole authority over native Binance API. |
| **LEAN (QuantConnect)** | `Lean-master.zip` | `368754edc40c8bc89589810b1806f817e4245ea2de492b0c6a4d25bb532d1d2b` | Apache License 2.0 | Architectural reference for execution models, slippage, fee models, report card | Architectural Reference Only | Inform separation of concerns and statistical metrics. Do not rely on default optimistic execution assumptions. |

---

## Detailed Project Attributions & Notices

### 1. Passivbot
- **Repository:** https://github.com/enarjord/passivbot
- **License:** The Unlicense (Public Domain)
- **Local Archive:** `passivbot-master.zip` (SHA-256: `bad79d36587b3812481e343c4a47c76ca3ce6d527e8ba42e88bfdc1a88e6c468`)
- **Inspected Source Files:** `src/binance_ohlcv_archive.py`, `docs/plans/hlcvs_downloader_determinism_handoff.md`
- **Adaptation Scope:** Archive month/day eligibility calculations, `.CHECKSUM` verification parsing, and cancellation-safe async concurrency.
- **Required Modifications:** Replaced in-memory buffering with streaming `.part` downloads, incremental SHA-256 calculation, and strict decimal typing.
- **License Text:**
```text
This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.
```

---

### 2. Jesse
- **Repository:** https://github.com/jesse-ai/jesse
- **License:** MIT License
- **Local Archive:** `jesse-master.zip` (SHA-256: `de72c7803b0f26efd2d0a555285e9e33040de1b72b0cda001665640f566008c0`)
- **Inspected Source Files:** `jesse/models/Candle.py`, `jesse/modes/import_candles_mode/`
- **Use Mode:** Dependency / Export Target.
- **Attribution Notice:**
```text
MIT License
Copyright (c) 2019-present Saleh Mir (saleh@jesse.trade)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
```

---

### 3. NautilusTrader
- **Repository:** https://github.com/nautechsystems/nautilus_trader
- **License:** GNU Lesser General Public License v3.0 (LGPL-3.0)
- **Local Archive:** `nautilus_trader-develop.zip` (SHA-256: `7df7feb2c7b8f861b699d317fa4e997b56370ea505c6b40a20219e69eba7e6d3`)
- **Inspected Source Files:** `crates/persistence/src/backend/catalog.rs`, `crates/persistence/bin/to_parquet.rs`
- **Use Mode:** Dependency & Interoperability Target.
- **License Boundary:** Used exclusively through external Python interfaces without modifying internal LGPL components.

---

### 4. Hummingbot
- **Repository:** https://github.com/hummingbot/hummingbot
- **License:** Apache License 2.0
- **Local Archive:** `hummingbot-master.zip` (SHA-256: `660c4f5cc2f5f9aa6fb5232b002998f566039cef9568884b9c114b95dd5cb334`)
- **Inspected Source Files:** `hummingbot/connector/derivative/binance_perpetual/binance_perpetual_api_order_book_data_source.py`
- **Adaptation Scope:** Algorithmic order-book snapshot and diff-depth synchronization logic.
- **Attribution Notice:**
```text
Copyright 2020-present CoinAlpha, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0
```

---

### 5. Freqtrade
- **Repository:** https://github.com/freqtrade/freqtrade
- **License:** GNU General Public License v3.0 (GPL-3.0)
- **Local Archive:** `freqtrade-develop.zip` (SHA-256: `196c5ed0651e83db3caa59acf4e5ed63c7c769b761e496d98aa417e59c470e8f`)
- **Inspected Source Files:** `freqtrade/data/history/datahandlers/parquetdatahandler.py`
- **Boundary Policy:** Reference / external challenger only. Code is never copied into BTCETH OS codebase.

---

### 6. OctoBot
- **Repository:** https://github.com/Drakkar-Software/OctoBot
- **License:** GNU General Public License v3.0 (GPL-3.0)
- **Local Archive:** `OctoBot-master.zip` (SHA-256: `a1584b1c78c6f1305c0fbcb7c0be38175fa76b8abad7f0014f5e2bd515dfc5fa`)
- **Boundary Policy:** Architectural and design reference only. No source code copying.

---

### 7. CCXT (CryptoCurrency eXchange Trading Library)
- **Repository:** https://github.com/ccxt/ccxt
- **License:** MIT License
- **Local Archive:** `ccxt-master.zip` (SHA-256: `7f3e419437b6a1632b8cb654102a44e855853f226148b6ed7dfcbcdd61372638`)
- **Inspected Source Files:** `python/ccxt/base/precise.py`, `python/ccxt/base/errors.py`
- **Use Mode:** Python Dependency.
- **Attribution Notice:**
```text
The MIT License (MIT)
Copyright (c) 2017-2026 CCXT Dev Team
```

---

### 8. QuantConnect LEAN
- **Repository:** https://github.com/QuantConnect/Lean
- **License:** Apache License 2.0
- **Local Archive:** `Lean-master.zip` (SHA-256: `368754edc40c8bc89589810b1806f817e4245ea2de492b0c6a4d25bb532d1d2b`)
- **Inspected Source Files:** `Common/Orders/Fees/BinanceFuturesFeeModel.cs`, `FillModel.cs`, `SlippageModel.cs`
- **Use Mode:** Architectural Reference.
- **Attribution Notice:**
```text
Copyright 2014 QuantConnect Corp.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
```
