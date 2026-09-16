# Binance Public Data Archive Known Issues Audit

This report audits known user-reported issues from the official `binance/binance-public-data` repository relevant to our BTC and ETH datasets.

| Issue ID | Topic | Reported Concern | Repository State | Classification | BTCETH OS Mitigation |
|---|---|---|---|---|---|
| **#475** | Monthly vs Daily Kline Disagreement | User reports monthly Spot kline archives disagree with daily archives and API for specific dates (2020-12-21, 2021-09-29). | OPEN | `REPORTED` | Planner strictly enforces non-overlap. Downloader validates daily-vs-monthly candle consistency on ingest. |
| **#469** | Missing Checksum Sidecars | User reported 7 corrupted zips and 5 missing checksums in historical monthly data. | OPEN | `REPORTED` | Wave 1B.2 downloader requires valid 64-hex SHA-256 sidecar before atomic promotion; files lacking checksum fail ingest. |
| **#483** | USD-M Mark/Index Gaps | User reported missing 1m markPriceKlines and indexPriceKlines rows across multiple symbols. | OPEN | `REPORTED` | Quality engine validates continuous 1-minute monotonic timestamp grids and logs gap anomalies. |
| **#484** | Futures Duplicate/Missing Timestamps | User reported duplicate and missing timestamps in USD-M metrics and markPriceKlines for BTCUSDT/ETHUSDT (2023-2025). | OPEN | `REPORTED` | Canonical deduplication and monotonic index constraints enforce zero duplicates in Bronze/Silver. |
| **#495** | FundingRate Contract Discontinuities | User reported LITUSDT fundingRate archives contain post-delisting rows and REST omits old history after ticker reuse. | OPEN | `REPORTED` | Not applicable to BTC/ETH (permanent contracts), but BTCETH OS isolates fundingRate historical ingest from REST live tape. |
| **#498** | Checksum Mismatches in Metrics | Persistent checksum mismatches reported in `metrics` dataset for secondary altcoins. | OPEN | `NOT_APPLICABLE` | BTC/ETH core datasets verified intact; `metrics` is classified as discovery-only candidate. |

## Operating Classification Rules
- `REPORTED`: User-filed issue with external reports; unconfirmed by Binance core team.
- `CONFIRMED_BY_OUR_TEST`: Mechanically replicated in our bounded test environment.
- `RESOLVED`: Upstream patch or archive replacement verified.
- `UNRESOLVED`: Open upstream issue without official fix.
- `NOT_APPLICABLE`: Issue pertains to altcoin delisting or non-BTC/ETH instruments.

