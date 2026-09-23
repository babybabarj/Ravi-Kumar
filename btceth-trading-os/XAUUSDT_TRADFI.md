# XAUUSDT TradFi perpetual

XAUUSDT is Binance's USDT settled TradFi commodity perpetual for gold price exposure. It is a derivative, with no physical gold delivery. It is distinct from Tether Gold (XAUT), PAXG, and any spot gold market. The official USDⓈ-M API currently identifies it as `TRADIFI_PERPETUAL` with `underlyingType=COMMODITY`.

## Current public rule snapshot

The read only provider captured Binance responses on **2026-09-23 07:27:58 UTC** under `artifacts/instrument_specs/`. The XAU spec snapshot has rules logical SHA-256 `1fc3ee6782d74a9d6cccff1da3e95d0d194fb10ec488f9c61d2adf813f47e420`. These values are observations, not code constants:

| Field | Observed value |
|---|---:|
| Exchange status | `TRADING` |
| Price tick | `0.01` USDT |
| Quantity step and minimum | `0.001` XAU |
| Maximum lot quantity | `10000` XAU |
| Minimum notional | `5` USDT |
| Adjusted funding interval | `4` hours |

The provider records exact raw responses, retrieval times, physical SHA-256 digests, logical SHA-256 digests, and the parsed immutable spec. It leaves listing time, maximum leverage, contract size, price-index mode, and mark-price mode unknown until separately verified. Binance's `onboardDate` is retained in the raw response and is not treated as proof of first executable trading.

Sources: [USDⓈ-M exchange information](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data), including `GET /fapi/v1/exchangeInfo`, `GET /fapi/v1/fundingInfo`, `GET /fapi/v1/tradingSchedule`, and `GET /fapi/v1/premiumIndex`; [market stream routing](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect). The routed `/market/ws/xauusdt@markPrice` stream delivered an XAUUSDT event during the probe.

## Research and risk boundary

Contract last price, mark price, and price index are separate series. The provider verified that mark and index data are available, but their historical mechanics and rule changes still need source evidence. Funding must be reconciled to actual settlement timestamps; today's interval cannot be applied to older history by assumption.

Binance publishes a rolling commodity trading schedule. The current response proves schedule availability; it does not supply a complete historical calendar. Historical rule epochs, weekend closures, maintenance, reopen gaps, and current epoch forward evidence remain unverified. No XAU native historical dataset, strategy, shadow approval, paper approval, or live approval has been established. Account eligibility is unknown because read only account credentials were absent during this phase.

XAUTUSDT is a separate tokenized gold product and cannot share XAUUSDT data, funding, strategy, or execution state. See [XAUTUSDT_DISTINCTION.md](XAUTUSDT_DISTINCTION.md).
