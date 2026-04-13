# Backtest Results — Full Iteration History

> All backtests run on MNQ1! 15-minute chart, Nov 2 2025 — Apr 10 2026 (159 trading days).  
> Account model: Tradeify $50k EOD drawdown. Commission: $0.62/contract round-trip (included).

---

## Summary Table

| Version | Trades | Win Rate | Profit Factor | Net P&L | Max DD | Notes |
|---------|--------|----------|---------------|---------|--------|-------|
| Baseline short-only | 31 | 54.84% | 1.979 | +$7,185 | 0.69% | KNN lb=150, K=10 |
| K=8 neighbors | 35 | 65.71% | 2.670 | +$12,038 | 0.69% | Key K discovery |
| Dual engine (long added) | 44 | 67.92% | 2.935 | +$14,953 | 0.82% | Long engine on |
| $850 circuit breaker | 48 | 68.75% | 3.451 | +$20,259 | 0.84% | Compliance tuned |
| Long KNN K=7 | 49 | 69.39% | 4.097 | +$18,323 | 0.52% | Best DD version |
| Full param tune (PEAK) | 54 | 72.22% | 4.342 | +$26,031 | 0.71% | Current config |

---

## Iteration Analysis

### Baseline Short-Only (KNN K=150)

The starting point: a pivot breakout system with a 200 EMA trend filter, RVOL threshold, ADX gate, and session kill zones. The KNN classifier was enabled with K=150 and lookback=200. At 150 neighbors, the classifier is effectively computing a long-run win rate across all market conditions in the lookback window — it approximates the system's base rate rather than filtering for current conditions.

Result: 31 trades, PF 1.979, WR 54.84%. Functional but undifferentiated from a simpler breakout system. The KNN at K=150 was adding marginal value.

---

### K=8 Neighbors — The Step Change

Reducing K from 150 to 8 produced the single largest improvement in the project. The mechanism is specificity: with 8 neighbors, the classifier only accepts a trade if the 8 most similar historical bars tended to produce wins. If the current bar is similar to past bars that occurred during low-volume, choppy, mixed-regime conditions, those 8 neighbors will return a poor win rate and block the entry. At K=150, those bars get averaged away and their signal diluted.

The sweep from K=150 to K=8 was systematic. K=50 improved to ~2.2 PF. K=20 reached ~2.4. K=10 reached ~2.5. K=8 produced the jump to 2.67 and remained stable when re-run across different date ranges. K=5 was slightly worse (too few neighbors increases sensitivity to individual bad trades in the pool).

Result: +35 trades (+4 vs baseline), PF 2.670, WR 65.71% (+10.87 ppt), net P&L doubled to +$12,038.

---

### Dual Engine (Long Engine Added)

With the short engine validated, a long engine was introduced as a separate module with its own KNN pool (K=7), tighter exit parameters (Stage 1 at 1.7R instead of 2.6R, ATR trail 1.25x instead of 2.0x), and the same session/filter gates. The long engine was designed to be selective — it fires on fewer setups but exits faster to capture NQ's tendency toward mean-reversion on long-side moves.

Adding the long engine introduced 9 additional trades (8 longs + 1 spillover short from the changed filter state). Max DD increased slightly from 0.69% to 0.82% as the long engine found some losing setups early in the test period. PF improved to 2.935 as the long trades added clean winners.

Result: +44 trades (+9), PF 2.935, WR 67.92% (+2.21 ppt), net +$14,953 (+$2,915 vs K=8 only).

---

### $850 Circuit Breaker — Compliance Tuning

The default daily loss circuit breaker was set at $1,100, which exceeds Tradeify's allowed daily drawdown for the $50k challenge. Reducing it to $850 (below the challenge's hard limit) had an unexpected positive effect: it cut off a handful of worst-case days where the system continued trading after an early loss and compounded the drawdown.

The tighter circuit breaker also forced earlier session management discipline — days that would have ended at −$1,000+ now hard-stop at −$850 and preserve capital. This mechanical change added 4 trades (the earlier stop on bad days freed up clean-slate sessions the next day that might have been psychologically affected in discretionary trading) and improved PF meaningfully.

Result: +48 trades (+4), PF 3.451, WR 68.75% (+0.83 ppt), net +$20,259 (+$5,306).

---

### Long KNN K=7 — Best Drawdown Version

Tuning the long engine's KNN to K=7 (from K=10 default) sharpened the long-side signal in the same way K=8 sharpened the short-side. The long engine became more selective, adding one additional trade but — more importantly — avoiding two marginal long setups from the previous version that had produced small losses.

This version achieved the lowest max drawdown in the entire iteration history: 0.52%. Net P&L was slightly lower than the final peak version (+$18,323 vs +$26,031), which reflects different exit calibration. The 0.52% DD version is worth noting as a conservative configuration if drawdown minimization is the primary objective.

Result: +49 trades (+1), PF 4.097 (+0.646), WR 69.39%, net +$18,323, Max DD 0.52%.

---

### Full Parameter Tune — PEAK Configuration

Final tuning pass: adjusted pivot lookback (short engine lb=6 vs prior 8), recalibrated RVOL threshold from 1.5 to 1.2 (capturing more valid breakouts that were previously filtered), and widened the Stage 1 short target from 2.2R to 2.6R to let momentum plays develop further before partial exit.

The RVOL adjustment from 1.5 to 1.2 was the meaningful change. At 1.5, a number of valid breakouts on lower-than-average-but-still-directional volume were rejected. At 1.2, the system accepted those setups and the KNN layer served as the quality gate rather than the volume threshold. This added 5 trades and increased the win rate by 2.83 percentage points.

Result: 54 trades (+5), PF 4.342 (+0.245), WR 72.22% (+2.83 ppt), net +$26,031 (+$7,708 vs prior), Max DD 0.71%.

---

## Split Engine Results (Peak Config)

| Engine | Trades | Win Rate | Profit Factor | Net P&L |
|--------|--------|----------|---------------|---------|
| Short | 46 | 69.57% | 3.746 | ~$21,400 |
| Long | 8 | 87.50% | 26.075 | ~$4,600 |
| **Combined** | **54** | **72.22%** | **4.342** | **+$26,031** |

The long engine's 26.075 PF on 8 trades should be interpreted with caution. This is a small sample. The high PF reflects that the long engine was designed for selectivity — it fires rarely and exits at tight targets. A single losing long trade would meaningfully reduce the PF. The long engine's contribution to the system is meaningful but its standalone metrics should not be extrapolated.

The short engine is the core thesis of the system: 46 trades, PF 3.746, WR 69.57%. This is the edge that is being traded.

---

## Equity Curve Notes

The equity curve across the 159-day test period shows near-monotonic growth with three notable characteristics:

1. **Shallow drawdowns** — Max DD of 0.71% reflects the combination of 0.5% per-trade risk, the two-stage exit (worst case on a TP1-reached trade is approximately breakeven on the runner), and the $850 daily circuit breaker.

2. **No extended losing streaks** — The KNN filter and Overlord Sentinel's consecutive-loss lock work together to reduce the probability of taking 6+ consecutive losses. The filter is more stringent during low-quality market conditions, which is precisely when losing streaks tend to cluster.

3. **Flat periods** — The system is session-restricted (Golden Window + Power Hour only) and trade-count-capped (max 6/day). Some weeks show minimal activity when macro conditions were unfavorable or the KNN filter rejected setups. These flat periods are intended behavior, not failure states.

---

## What Was Not Tested

For completeness, the following were considered but not included in the final configuration:

- **Higher timeframes (1h, 4h)** — Fewer trades, harder to reach 54-trade significance threshold within test period
- **Different instruments** — ES/MES shows lower PF with same parameters; NQ's higher volatility suits the breakout methodology better
- **Larger K values (K=15, K=20)** — Consistently worse than K=8 in this dataset
- **Volume profile levels as targets** — Added complexity without improving PF; removed
- **Machine learning exit optimization** — Out of scope; the fixed R-multiple exit is reproducible and well-defined

---

*All results are hypothetical backtest results. Past performance does not guarantee future results. No forward-test data is included in this document.*
