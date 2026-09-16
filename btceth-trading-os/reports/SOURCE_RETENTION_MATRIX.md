# Source Retention Matrix

| Source | Dataset | Phase 1A policy |
|---|---|---|
| Binance USD-M | OI / positioning / taker statistics | Perishable; bootstrap available official history then capture forward continuously |
| Binance USD-M | aggTrades / bookTicker / diff depth | Forward WebSocket capture + official REST/archive recovery where available |
| Binance USD-M | liquidation sample | Forward only; PARTIAL / SAMPLED_LARGEST_ORDER, never total liquidation truth |
| Binance Spot | aggTrades / bookTicker / diff depth | Forward WebSocket capture + official archive/REST historical build in Phase 1B |
| Deribit | BTC/ETH option state | Forward capture immediately; preserve raw option state and source timestamps |
