# Phase 1A Acceptance

PHASE_1A = VERIFIED

- [x] automated_tests_pass
- [x] security_scan_pass
- [x] live_smoke_process_pass
- [x] all_rest_collectors_observed
- [x] required_ws_streams_observed
- [x] liquidation_streams_reachable
- [x] four_orderbooks_synchronized
- [x] no_source_errors
- [x] raw_append_only_evidence_present
- [x] silver_parquet_readback
- [x] catalog_present
- [x] sqlite_wal

CANONICAL LIVE CAPTURE = VERIFIED
TRADING CAPABILITY = ZERO
NEXT = PHASE 1B

## Smoke summary

```json
{
  "rest": 20,
  "ws": 12,
  "duplicates": 0,
  "conflicts": 0,
  "errors": [],
  "ws_stream_results": [
    {
      "market": "spot",
      "dataset": "aggtrade",
      "instrument_id": "BINANCE:SPOT:BTCUSDT",
      "sparse": false,
      "messages_received": 1,
      "status": "EVENT_RECEIVED"
    },
    {
      "market": "spot",
      "dataset": "book_ticker",
      "instrument_id": "BINANCE:SPOT:BTCUSDT",
      "sparse": false,
      "messages_received": 1,
      "status": "EVENT_RECEIVED"
    },
    {
      "market": "spot",
      "dataset": "depth_delta",
      "instrument_id": "BINANCE:SPOT:BTCUSDT",
      "sparse": false,
      "messages_received": 1,
      "status": "EVENT_RECEIVED"
    },
    {
      "market": "usdm",
      "dataset": "aggtrade",
      "instrument_id": "BINANCE:USD_M_PERP:BTCUSDT",
      "sparse": false,
      "messages_received": 1,
      "status": "EVENT_RECEIVED"
    },
    {
      "market": "usdm",
      "dataset": "book_ticker",
      "instrument_id": "BINANCE:USD_M_PERP:BTCUSDT",
      "sparse": false,
      "messages_received": 1,
      "status": "EVENT_RECEIVED"
    },
    {
      "market": "usdm",
      "dataset": "depth_delta",
      "instrument_id": "BINANCE:USD_M_PERP:BTCUSDT",
      "sparse": false,
      "messages_received": 1,
      "status": "EVENT_RECEIVED"
    },
    {
      "market": "usdm",
      "dataset": "liquidation_sample",
      "instrument_id": "BINANCE:USD_M_PERP:BTCUSDT",
      "sparse": true,
      "messages_received": 0,
      "status": "CONNECTED_NO_EVENT_ACCEPTABLE"
    },
    {
      "market": "spot",
      "dataset": "aggtrade",
      "instrument_id": "BINANCE:SPOT:ETHUSDT",
      "sparse": false,
      "messages_received": 1,
      "status": "EVENT_RECEIVED"
    },
    {
      "market": "spot",
      "dataset": "book_ticker",
      "instrument_id": "BINANCE:SPOT:ETHUSDT",
      "sparse": false,
      "messages_received": 1,
      "status": "EVENT_RECEIVED"
    },
    {
      "market": "spot",
      "dataset": "depth_delta",
      "instrument_id": "BINANCE:SPOT:ETHUSDT",
      "sparse": false,
      "messages_received": 1,
      "status": "EVENT_RECEIVED"
    },
    {
      "market": "usdm",
      "dataset": "aggtrade",
      "instrument_id": "BINANCE:USD_M_PERP:ETHUSDT",
      "sparse": false,
      "messages_received": 1,
      "status": "EVENT_RECEIVED"
    },
    {
      "market": "usdm",
      "dataset": "book_ticker",
      "instrument_id": "BINANCE:USD_M_PERP:ETHUSDT",
      "sparse": false,
      "messages_received": 1,
      "status": "EVENT_RECEIVED"
    },
    {
      "market": "usdm",
      "dataset": "depth_delta",
      "instrument_id": "BINANCE:USD_M_PERP:ETHUSDT",
      "sparse": false,
      "messages_received": 1,
      "status": "EVENT_RECEIVED"
    },
    {
      "market": "usdm",
      "dataset": "liquidation_sample",
      "instrument_id": "BINANCE:USD_M_PERP:ETHUSDT",
      "sparse": true,
      "messages_received": 0,
      "status": "CONNECTED_NO_EVENT_ACCEPTABLE"
    }
  ],
  "ws_required_missing": [],
  "orderbooks_synced": 4,
  "orderbook_results": [
    {
      "market": "spot",
      "symbol": "BTCUSDT",
      "last_update_id": 100406858348,
      "best_bid": "81587.76000000",
      "best_ask": "81587.77000000",
      "deltas_applied": 3
    },
    {
      "market": "spot",
      "symbol": "ETHUSDT",
      "last_update_id": 81253560355,
      "best_bid": "2655.00000000",
      "best_ask": "2655.01000000",
      "deltas_applied": 3
    },
    {
      "market": "usdm",
      "symbol": "BTCUSDT",
      "last_update_id": 11613835647929,
      "best_bid": "81595.20",
      "best_ask": "81595.30",
      "deltas_applied": 3
    },
    {
      "market": "usdm",
      "symbol": "ETHUSDT",
      "last_update_id": 11613836179536,
      "best_bid": "2653.66",
      "best_ask": "2653.67",
      "deltas_applied": 3
    }
  ],
  "orderbook_errors": [],
  "silver_rows": 32,
  "catalog_heartbeats": 34
}
```
