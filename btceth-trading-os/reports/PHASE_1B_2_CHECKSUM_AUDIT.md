# Phase 1B.2 Cryptographic Checksum Audit

- **Audit Timestamp (UTC)**: `2026-09-21T16:47:58.250417+00:00`
- **Tested Code Commit**: `f2b7988d54d222ec4c36535c58c8c17e3daa45d9`
- **Triple-Reconciliation Oracle Status**: `PASS`
- **Formula**: `official_checksum == python_sha256 == os_sha256`

| Archive Filename | Official Checksum | Python SHA-256 | OS sha256 (`shasum`) | Reconciled |
| :--- | :--- | :--- | :--- | :---: |
| `BTCUSDT-1m-2024-12-31.zip` | `756551b6eb4f0a01...` | `756551b6eb4f0a01...` | `756551b6eb4f0a01...` | PASS |
| `BTCUSDT-1m-2025-01-01.zip` | `10a12909f1b0e3fc...` | `10a12909f1b0e3fc...` | `10a12909f1b0e3fc...` | PASS |
| `ETHUSDT-1m-2024-12-31.zip` | `70ae988d84bb7ad0...` | `70ae988d84bb7ad0...` | `70ae988d84bb7ad0...` | PASS |
| `ETHUSDT-1m-2025-01-01.zip` | `26cc71cf7a2bd023...` | `26cc71cf7a2bd023...` | `26cc71cf7a2bd023...` | PASS |
| `BTCUSDT-aggTrades-2024-12-31.zip` | `31bf57b571f0bf58...` | `31bf57b571f0bf58...` | `31bf57b571f0bf58...` | PASS |
| `ETHUSDT-trades-2024-12-31.zip` | `d344dbd740ce88f1...` | `d344dbd740ce88f1...` | `d344dbd740ce88f1...` | PASS |
| `BTCUSDT-1m-2024-11-01.zip` | `8fd920bd21fc7107...` | `8fd920bd21fc7107...` | `8fd920bd21fc7107...` | PASS |
| `ETHUSDT-1m-2024-11-01.zip` | `3d1b23645bdaab80...` | `3d1b23645bdaab80...` | `3d1b23645bdaab80...` | PASS |
| `BTCUSDT-1m-2024-11-01.zip` | `787558eacc52e25b...` | `787558eacc52e25b...` | `787558eacc52e25b...` | PASS |
| `BTCUSDT-1m-2024-11-01.zip` | `8337b5caeb471772...` | `8337b5caeb471772...` | `8337b5caeb471772...` | PASS |
| `BTCUSDT-1m-2024-11-01.zip` | `9c17708de0fdecd1...` | `9c17708de0fdecd1...` | `9c17708de0fdecd1...` | PASS |
| `BTCUSDT-aggTrades-2024-11-01.zip` | `778e6eb0375edbf5...` | `778e6eb0375edbf5...` | `778e6eb0375edbf5...` | PASS |
| `ETHUSDT-trades-2024-11-01.zip` | `c90874a4d0ff30d0...` | `c90874a4d0ff30d0...` | `c90874a4d0ff30d0...` | PASS |
| `BTCUSDT-fundingRate-2024-11.zip` | `e1b19cccfe2cdcba...` | `e1b19cccfe2cdcba...` | `e1b19cccfe2cdcba...` | PASS |
| `ETHUSDT-fundingRate-2024-11.zip` | `636a4c7c86445c27...` | `636a4c7c86445c27...` | `636a4c7c86445c27...` | PASS |
