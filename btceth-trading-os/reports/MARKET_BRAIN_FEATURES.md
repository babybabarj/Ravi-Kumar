# Market Brain Feature Catalog & Point-in-Time Contract

## Inviolable Point-in-Time Rule
> $available\_ts \le decision\_ts$. Every feature strictly uses closed bars at or prior to the decision point.
Future-row perturbation and truncated-history equivalence tests guarantee zero lookahead leakage.

| Feature ID | Category | Lookback (Bars) | Source Fields | Description |
| :--- | :--- | :--- | :--- | :--- |
| `log_return_1m` | `price_returns` | 1 | `close` | Natural log price return over 1m (1 1m bars) |
| `log_return_5m` | `price_returns` | 5 | `close` | Natural log price return over 5m (5 1m bars) |
| `log_return_15m` | `price_returns` | 15 | `close` | Natural log price return over 15m (15 1m bars) |
| `log_return_1h` | `price_returns` | 60 | `close` | Natural log price return over 1h (60 1m bars) |
| `log_return_4h` | `price_returns` | 240 | `close` | Natural log price return over 4h (240 1m bars) |
| `trend_slope_30m` | `price_returns` | 30 | `close` | OLS linear regression slope over past 30 bars, normalized by close |
| `breakout_dist_60m` | `price_returns` | 60 | `close, high, low` | Normalized distance from prior 60-bar high/low channel |
| `norm_range_pos_30m` | `price_returns` | 30 | `close, high, low` | Stochastic %K normalized price position in 30m high-low window |
| `rolling_drawdown_2h` | `price_returns` | 120 | `close` | Peak-to-trough drawdown over rolling 120-minute window |
| `realized_vol_60m` | `volatility` | 60 | `close` | Annualized close-to-close realized volatility over rolling 60-bar window |
| `parkinson_vol_60m` | `volatility` | 60 | `high, low` | Annualized Parkinson high-low range volatility over rolling 60-bar window |
| `garman_klass_vol_60m` | `volatility` | 60 | `open, high, low, close` | Annualized Garman-Klass OHLC volatility over rolling 60-bar window |
| `atr_pct_14` | `volatility` | 14 | `high, low, close` | 14-bar Average True Range expressed as percentage of close |
| `range_compression_15_60` | `volatility` | 60 | `high, low, close` | Ratio of 15m ATR to 60m ATR (< 0.70 = compression squeeze) |
| `funding_rate_current` | `derivatives` | 1 | `funding_rate` | Point-in-time effective 8h funding rate for the current bar |
| `funding_zscore_24h` | `derivatives` | 1440 | `funding_rate` | 24-hour rolling z-score of the effective funding rate |
| `minutes_to_funding` | `derivatives` | 1 | `ts_event_ns` | Minutes remaining until the next scheduled 8h funding event |
| `eth_btc_ratio` | `cross_asset` | 1 | `close_btc, close_eth` | ETH/BTC price ratio at each synchronized minute bar |
| `eth_btc_rel_return` | `cross_asset` | 1 | `ret_btc, ret_eth` | Difference between ETH return and BTC return |
| `btc_eth_corr_60m` | `cross_asset` | 60 | `ret_btc, ret_eth` | 60-minute rolling Pearson correlation between BTC and ETH returns |
| `eth_btc_ratio_zscore_24h` | `cross_asset` | 1440 | `eth_btc_ratio` | 24-hour rolling z-score of the ETH/BTC price ratio |
| `session_flags` | `time_session` | 1 | `ts_event_ns` | Point-in-time binary session membership (Asia 00-08 UTC, Europe 07-16 UTC, US 13-21 UTC, Weekend) |
