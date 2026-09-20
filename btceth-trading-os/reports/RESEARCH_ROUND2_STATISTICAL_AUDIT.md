# Statistical Validation & Multiple-Testing Audit (Research Round 2)

## 1. Mathematical Framework & Formulas

### 1.1 Deflated Sharpe Ratio (DSR)
Bailey & López de Prado (2014) established that as the number of explored trials ($N$) grows, the expected maximum Sharpe ratio under the null hypothesis of zero skill ($E[\max_N]$) increases:
$$E[\max_N] \approx \sqrt{V} \left( (1 - \gamma_E) Z^{-1}\left(1 - \frac{1}{N}\right) + \gamma_E Z^{-1}\left(1 - \frac{1}{N \cdot e}\right) \right)$$
where:
- $\gamma_E \approx 0.5772156649$ (Euler-Mascheroni constant)
- $V = \operatorname{Var}(\{SR_n\})$ is the empirical cross-sectional variance of Sharpe ratios across all explored parameter variants in the family search space
- $Z^{-1}(p)$ is the inverse standard normal cumulative distribution function

The standard error of the estimated Sharpe ratio is adjusted for sample length $T$, skewness $\gamma_3$, and kurtosis $\gamma_4$:
$$\hat{\sigma}_{SR} = \sqrt{\frac{1 - \frac{1}{2} \gamma_3 \widehat{SR} + \frac{\gamma_4 - 1}{4} \widehat{SR}^2}{T - 1}}$$

The Deflated Sharpe Ratio is the probability that the observed Sharpe ratio exceeds the expected maximum under multiple testing:
$$\text{DSR} = \Phi\left( \frac{\widehat{SR} - E[\max_N]}{\hat{\sigma}_{SR}} \right)$$

**Validation Rule**: A candidate strategy must achieve $\text{DSR} \ge 0.95$ ($p < 0.05$) to reject the null hypothesis of selection bias.

---

### 1.2 Combinatorially Symmetric Cross-Validation (CSCV) & PBO
To prevent selection bias across backtest splits:
1. The return matrix $M \times T$ ($M$ variants, $T$ periods) is partitioned into $S = 16$ contiguous chronological blocks.
2. All $\binom{16}{8} = 12,870$ combinations (sampled up to 500 combinations) are evaluated.
3. For each combination $c$, in-sample (IS) performance selects the optimal variant $m^* = \arg\max_{m} R_{m, \text{IS}}$.
4. The out-of-sample (OOS) rank of variant $m^*$ is computed among all $M$ variants in $c^c$.
5. If variant $m^*$ ranks in the lower $50\%$ of variants out-of-sample, the trial is flagged as overfit.
6. The Probability of Backtest Overfitting (PBO) is:
$$\text{PBO} = \frac{1}{C} \sum_{c=1}^C \mathbf{1}\left( \text{rank}(m^*, \text{OOS}) \ge \frac{M}{2} \right)$$

**Uncomputable Rule**: If $M < 2$ or $T < 2S$, PBO cannot be calculated and is marked `PBO_NOT_COMPUTABLE`. It is **never** reported as `0.0`.

---

### 1.3 Stationary / Moving Block Bootstrap
To evaluate serial correlation and trade dependency:
- Consecutive blocks of trade returns (lengths $k \in \{5, 10, 20\}$) are resampled $B = 1,000$ times.
- The 95% lower confidence bound of trade expectancy is computed:
$$\text{Expectancy}_{\text{Lower 95\% CI}} \ge 0.0 \text{ bps}$$

---

### 1.4 Dynamic Purging & Embargo Boundaries
To eliminate lookahead contamination between training and test sets:
- **Purging**: Removes observations where the forward return or trade holding horizon crosses the split boundary.
- **Embargo**: An idle buffer equal to $\max(\text{lookback}, \text{holding\_horizon})$ is inserted after the split to prevent autoregressive feature persistence from leaking information.

---

### 1.5 Multi-Year Consistency
To ensure edge survival across different macro environments:
- Minimum profitable years ratio: $\ge 66\%$ ($\ge 2$ of 3 years profitable after stressed costs).
- Maximum single calendar year drawdown: $\le 12\%$.
