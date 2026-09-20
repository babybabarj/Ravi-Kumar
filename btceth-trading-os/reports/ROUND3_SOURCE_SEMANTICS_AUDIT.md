# Research Round 3: Source Semantics & Reference Price Audit

## Executive Summary
In Research Round 2, data generation noted:
```text
MARK/INDEX/PREMIUM DATA = DERIVED_AND_ALIGNED
```
This audit examines the semantic, economic, and mathematical distinctions between derived Spot/Perp price differentials and the official Binance USD-M reference-price datasets (`markPriceKlines`, `indexPriceKlines`, and `premiumIndexKlines`).

Treating derived Spot/Perp spread as interchangeable with official Mark Price, Index Price, or Premium Index introduces subtle but severe model misspecifications into liquidation modeling, funding estimation, and basis arbitrage. In Research Round 3, these concepts are strictly separated into verified, distinct source streams.

---

## Semantic Taxonomy & Mathematical Definitions

### 1. Traded Perpetual Price ($P_{\text{perp}}$)
- **Source**: `futures/um/monthly/klines/{symbol}/1m/`
- **Definition**: The volume-weighted execution price of trades executed on the Binance USD-M order book.
- **Role**: Entry and exit prices for perpetual market orders, fills, and slippage calculations.
- **Volatility**: High (susceptible to local order book micro-spikes, aggressive taker market orders, and temporary liquidity voids).

### 2. Traded Spot Price ($P_{\text{spot}}$)
- **Source**: `spot/monthly/klines/{symbol}/1m/`
- **Definition**: The execution price of trades executed on the Binance Spot exchange.
- **Role**: Entry and exit prices for spot cash-and-carry leg purchases/sales.
- **Funding**: Zero funding cash flows. Spot is full unencumbered physical asset ownership.

### 3. Traded Basis ($\text{Basis}_{\text{traded}}$)
- **Definition**: Raw price difference between the traded perpetual contract and the traded spot market:
  $$\text{Basis}_{\text{traded}} = P_{\text{perp}} - P_{\text{spot}}$$
  $$\text{Basis Ratio} = \frac{P_{\text{perp}} - P_{\text{spot}}}{P_{\text{spot}}}$$
- **Limitation**: Reflects execution price differences on Binance alone; does **not** equal the Binance funding rate formula basis nor the mark price.

### 4. Official Index Price ($P_{\text{index}}$)
- **Source**: `futures/um/monthly/indexPriceKlines/{symbol}/1m/`
- **Definition**: A volume-weighted composite basket of spot prices from major global exchanges (Binance, Coinbase, Kraken, Bybit, etc.).
- **Properties**:
  - Independent of idiosyncratic Binance order book microstructure.
  - Automatically filters outlier prices from individual constituent exchanges.
  - Serves as the fundamental anchor for both Mark Price and Premium Index calculations.

### 5. Official Mark Price ($P_{\text{mark}}$)
- **Source**: `futures/um/monthly/markPriceKlines/{symbol}/1m/`
- **Definition**: The smoothed price calculated by Binance to evaluate unrealized P&L and trigger liquidations:
  $$P_{\text{mark}} = P_{\text{index}} \times (1 + \text{Funding Basis Moving Average})$$
  $$\text{Funding Basis} = \frac{\text{Impact Mid Price} - P_{\text{index}}}{P_{\text{index}}}$$
- **Critical Role**:
  - **Liquidations**: Perpetuals are liquidated when $P_{\text{mark}}$ touches maintenance margin, **not** when traded price $P_{\text{perp}}$ spikes.
  - **Settlement**: Funding payments are calculated on $P_{\text{mark}} \times \text{Position Size}$, not traded price.
  - **Smoothing**: Prevents unnecessary liquidations during temporary illiquid spikes on the perpetual order book.

### 6. Official Premium Index ($P_{\text{premium}}$)
- **Source**: `futures/um/monthly/premiumIndexKlines/{symbol}/1m/`
- **Definition**: The real-time premium rate calculated every second by Binance:
  $$P_{\text{premium}} = \frac{\max(0, \text{Impact Bid Price} - P_{\text{index}}) - \max(0, P_{\text{index}} - \text{Impact Ask Price})}{P_{\text{index}}}$$
- **Role**:
  - The 8-hour funding rate is calculated as the time-weighted average price (TWAP) of the Premium Index plus an interest rate clamp:
    $$F = \text{Clamp}\left(\text{TWAP}(P_{\text{premium}}, 8\text{h}) + \text{Clamp}(I - \text{TWAP}(P_{\text{premium}}, 8\text{h}), -0.05\%, 0.05\%), -0.75\%, +0.75\%\right)$$
  - Where $I$ is the interest rate component (typically 0.01% per 8h for BTC/ETH).

---

## Comparative Matrix

| Characteristic | Traded Perp | Traded Spot | Mark Price | Index Price | Premium Index | Derived Spread |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Official Archive** | `klines` | `klines` | `markPriceKlines` | `indexPriceKlines` | `premiumIndexKlines` | None (Synthetic) |
| **Unit** | Quote Currency (USDT) | Quote Currency (USDT) | Quote Currency (USDT) | Quote Currency (USDT) | Rate Fraction (e.g. `0.00015`) | Quote Currency (USDT) |
| **Constituents** | Binance Perp | Binance Spot | Spot Index + Basis | Multi-Exchange Spot | Binance Book vs Spot Index | Binance Perp vs Spot |
| **Used in Liquidations?** | No | No | **YES** | Anchor | No | No |
| **Used in Funding Rate?** | No | No | **YES (Notional)** | Anchor | **YES (TWAP)** | No |
| **Execution Price?** | **YES** | **YES** | No | No | No | No |

---

## Findings & Remediation

1. **AUD-R3-001 (Semantic Imprecision)**:
   - *Finding*: Round 2 labeled `MARK/INDEX/PREMIUM DATA = DERIVED_AND_ALIGNED`, using $P_{\text{perp}} - P_{\text{spot}}$ as a proxy for basis and reference prices.
   - *Remediation*: Ingest official `markPriceKlines`, `indexPriceKlines`, and `premiumIndexKlines`. Decouple all feature and accounting definitions into:
     - `trade_basis`: $P_{\text{perp}} - P_{\text{spot}}$
     - `mark_spot_basis`: $P_{\text{mark}} - P_{\text{spot}}$
     - `perp_index_basis`: $P_{\text{perp}} - P_{\text{index}}$
     - `official_premium_index`: $P_{\text{premium}}$

2. **AUD-R3-002 (Liquidation Risk Underestimation)**:
   - *Finding*: Using traded price rather than mark price fails to account for actual liquidation distance on Binance USD-M futures.
   - *Remediation*: Model margin requirements and liquidation proximity strictly against $P_{\text{mark}}$.

3. **AUD-R3-003 (Funding Forecasting Error)**:
   - *Finding*: Forecasting funding from raw traded spread introduces noise from single-venue taker spikes.
   - *Remediation*: Forecast next funding settlement using the TWAP of the official `premiumIndexKlines` and trailing settlement history.
