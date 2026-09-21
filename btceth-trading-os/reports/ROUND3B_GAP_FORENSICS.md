# Research Round 3B — Descriptive Source Gap Forensics Report

**Dataset Version**: `v3.1.0`  
**Evaluation Policy**: `FAIL_CLOSED_NO_FALLBACK`  
**Language Specification**: Strictly descriptive observations (`OBSERVED`, `ASSOCIATED_WITH`, `TEMPORALLY_NEAR`). Zero unsupported causal assertions.  

---

## 1. Executive Summary & Dataset Completeness

- **BTCUSDT Total Hours**: `35064` | **Valid Hours**: `34624` (`98.75%`) | **Invalid Hours**: `440`
- **ETHUSDT Total Hours**: `35064` | **Valid Hours**: `34816` (`99.29%`) | **Invalid Hours**: `248`
- **Discrete Gap Runs**: BTCUSDT observed `26` runs; ETHUSDT observed `22` runs.
- **Fail-Closed Guarantee**: Under `FAIL_CLOSED_NO_FALLBACK`, zero missing hours were forward-filled or fabricated. Any strategy evaluation encountering a missing hour is rejected.

---

## 2. Invalid Observations by Source Series

| Symbol | Spot Missing | Perp Missing | Mark Price Missing | Index Price Missing | Premium Index Missing | Total Invalid Hours |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **BTCUSDT** | 31 | 0 | 192 | 288 | 169 | **440** |
| **ETHUSDT** | 31 | 0 | 48 | 72 | 169 | **248** |

> [!NOTE]
> Perpetual contract traded bars (`perp_1m`) exhibited **0 missing hours** across the entire 4-year history for both BTCUSDT and ETHUSDT. Missing observations were concentrated in derived reference streams (`indexPriceKlines` and `markPriceKlines`).

---

## 3. Invalid Hours Distribution by Calendar Year

| Year | BTCUSDT Invalid Hours | ETHUSDT Invalid Hours |
| :--- | :--- | :--- |
| **2020** | 18 | 18 |
| **2021** | 133 | 133 |
| **2022** | 192 | 48 |
| **2023** | 97 | 49 |

---

## 4. Longest Consecutive Gap Windows (BTCUSDT)

| Rank | Start (UTC) | End (UTC) | Duration | Missing Series |
| :--- | :--- | :--- | :--- | :--- |
| **#1** | `2021-07-24T00:00:00+00:00` | `2021-07-27T23:00:00+00:00` | `96h` | `mark, premium` |
| **#2** | `2022-07-24T00:00:00+00:00` | `2022-07-25T23:00:00+00:00` | `48h` | `index` |
| **#3** | `2022-07-27T00:00:00+00:00` | `2022-07-28T23:00:00+00:00` | `48h` | `index` |
| **#4** | `2022-07-30T00:00:00+00:00` | `2022-07-31T23:00:00+00:00` | `48h` | `index, mark` |
| **#5** | `2023-04-07T00:00:00+00:00` | `2023-04-08T23:00:00+00:00` | `48h` | `index` |
| **#6** | `2021-07-01T00:00:00+00:00` | `2021-07-01T23:00:00+00:00` | `24h` | `mark, premium` |
| **#7** | `2022-04-27T00:00:00+00:00` | `2022-04-27T23:00:00+00:00` | `24h` | `index` |
| **#8** | `2022-10-02T00:00:00+00:00` | `2022-10-02T23:00:00+00:00` | `24h` | `index, mark, premium` |
| **#9** | `2023-02-13T00:00:00+00:00` | `2023-02-13T23:00:00+00:00` | `24h` | `index` |
| **#10** | `2023-02-24T00:00:00+00:00` | `2023-02-24T23:00:00+00:00` | `24h` | `index, mark, premium` |

---

## 5. Statistical Regime Proximity

Observations temporally associated with elevated market stress:
- **Gaps Temporally Near Volatility Spikes (> 1.5% hourly return vol)**: `0 / 440` (0.0%)
- **Gaps Temporally Near Extreme Funding (|rate| >= 5 bps)**: `50 / 440` (11.4%)
