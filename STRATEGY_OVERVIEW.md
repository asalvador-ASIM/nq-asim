# NQ-ASIM Strategy Overview

> Technical deep dive into the Pine Script v6 implementation.

---

## Table of Contents

1. [Parameter Reference](#parameter-reference)
2. [KNN Algorithm](#knn-algorithm)
3. [Entry Logic Flow](#entry-logic-flow)
4. [Exit Architecture](#exit-architecture)
5. [Session Kill Zones](#session-kill-zones)
6. [Overlord Sentinel](#overlord-sentinel)
7. [HUD Panel Descriptions](#hud-panel-descriptions)

---

## Parameter Reference

The following 17 parameters were changed from their defaults during development. Everything not listed here runs at Pine Script defaults.

| Group | Parameter | Default | Final Value | Effect |
|-------|-----------|---------|-------------|--------|
| Pivot | `i_piv_lb` (short) | 10 | 6 | Shorter pivot lookback — more breakout candidates |
| Pivot | `i_piv_lb_long` | 10 | 10 | Long pivot lookback (unchanged — longer pivots for long bias) |
| Filters | `i_rvol_thresh` | 1.5 | 1.2 | Slightly lower RVOL gate — captures more valid breakouts |
| Filters | `i_adx_min` | 25 | 20 | Lower ADX floor — NQ often trends at ADX 20–25 |
| Filters | `i_ema_period` | 200 | 200 | Unchanged |
| KNN Short | `i_knn_k` | 10 | 8 | Key: fewer neighbors = sharper regime specificity |
| KNN Short | `i_knn_lookback` | 200 | 200 | Rolling window for neighbor search |
| KNN Short | `i_knn_thresh` | 0.55 | 0.50 | Minimum win rate among K neighbors to allow entry |
| KNN Long | `i_knn_k_long` | 10 | 7 | Tighter pool for long engine selectivity |
| KNN Long | `i_knn_lookback_long` | 200 | 200 | Same lookback for long pool |
| KNN Long | `i_knn_thresh_long` | 0.55 | 0.50 | Same threshold, applied to long pool |
| Exit Short | `i_tp1_r` | 2.0 | 2.6 | Stage 1 target — further out to let momentum play |
| Exit Short | `i_atr_trail_mult` | 2.5 | 2.0 | Tighter ATR trail on runner |
| Exit Long | `i_tp1_r_long` | 2.0 | 1.7 | Stage 1 target — tighter for mean-reversion captures |
| Exit Long | `i_atr_trail_mult_long` | 2.5 | 1.25 | Much tighter trail on long runners |
| Risk | `i_risk_pct` | 1.0 | 0.5 | Half-position risk per trade |
| Circuit Breaker | `i_cb_daily_loss` | 1100 | 850 | Tradeify compliance — matches challenge daily drawdown |

---

## KNN Algorithm

### Concept

KNN (K-Nearest Neighbors) in this context is a pattern-matching classifier that runs on every bar. It does not predict price direction directly. It answers a narrower question: *do the current market conditions resemble historical bars that led to winning trades?*

The classifier stores a rolling window of the last N bars. For each stored bar it has two pieces of information: the feature vector (what the market looked like) and the label (did the subsequent trade win or lose). On each new bar it measures distance to every stored bar, selects the K closest, and counts votes. If the winning fraction among those K neighbors exceeds the threshold, the classifier outputs `true` — the signal is approved.

### Feature Vector

Each bar is described by four normalized features:

```pine
// Feature 1: Relative Volume
f_rvol = volume / ta.sma(volume, 20)

// Feature 2: ADX (directional strength)
[diPlus, diMinus, adxVal] = ta.dmi(14, 14)
f_adx = adxVal / 100.0

// Feature 3: EMA distance normalized by ATR
f_emadist = math.abs(close - ta.ema(close, 200)) / ta.atr(14)

// Feature 4: VIX proxy (security call or manual input)
f_vix = i_vix_value / 50.0
```

Features are normalized to comparable scales before distance calculation. Without normalization, a raw ADX of 35 would dominate a normalized RVOL of 1.4 simply because of scale difference.

### Distance and Voting

```pine
// Euclidean distance between current bar and stored bar i
dist = math.sqrt(
    math.pow(f_rvol  - stored_rvol[i],   2) +
    math.pow(f_adx   - stored_adx[i],    2) +
    math.pow(f_emad  - stored_emad[i],   2) +
    math.pow(f_vix   - stored_vix[i],    2)
)

// After finding K nearest neighbors:
win_votes  = count of neighbors where trade_result == WIN
knn_signal = (win_votes / K) >= i_knn_thresh
```

### The K=8 Discovery

During development, K was swept from 150 down to 5:

| K | Short PF | Notes |
|---|----------|-------|
| 150 | ~2.0 | Averaging over too many regimes |
| 50 | ~2.2 | Marginal improvement |
| 20 | ~2.4 | Improving, still diluted |
| 10 | ~2.5 | Getting sharper |
| **8** | **2.67 → 3.7+** | Step-change improvement |
| 5 | ~2.6 | Slightly overfit, too few neighbors |

K=8 finds eight bars in the lookback window that are genuinely similar to current conditions. If seven of those eight bars produced winning trades, that is a meaningful prior. K=150 averages over setups from calm days, high-volatility days, trend days, and chop days simultaneously — the signal becomes the historical base rate of the system, not a condition-sensitive filter.

### Separate Short and Long Pools

The short and long KNN classifiers operate on independent stored windows. They do not share neighbors. This is intentional: the conditions that produce winning short setups (e.g., high ADX, elevated VIX, extended EMA distance) are not the same conditions that produce winning long setups (lower VIX, moderate trend, less extension). A shared pool would blur both signals. Two independent pools means each engine gets a classifier calibrated to its own trade type.

---

## Entry Logic Flow

### Short Engine

```
Bar closes →
  1. Is price below 200 EMA?                       → NO: skip
  2. Did a pivot low break occur (N-bar lookback)?  → NO: skip
  3. Is RVOL ≥ threshold (1.2x)?                   → NO: skip
  4. Is ADX ≥ minimum (20)?                         → NO: skip
  5. Is current session in Golden Window or
     Power Hour kill zone?                          → NO: skip
  6. KNN vote: win_pct among 8 neighbors ≥ 50%?   → NO: skip
  7. Is Overlord Sentinel unlocked?                 → NO: skip
  8. Is daily trade count < 6?                      → NO: skip
  9. ENTER SHORT
     Stop = pivot high + ATR buffer
     TP1  = entry - (stop_dist × 2.6)
     Size = (account × 0.5%) / stop_dist_in_dollars
```

### Long Engine

```
Bar closes →
  1. Is price above 200 EMA?                        → NO: skip
  2. Did a pivot high break occur (N-bar lookback)? → NO: skip
  3. Is RVOL ≥ threshold?                           → NO: skip
  4. Is ADX ≥ minimum?                              → NO: skip
  5. Is current session in kill zone?               → NO: skip
  6. KNN long pool vote ≥ 50%?                      → NO: skip
  7. Is i_long_engine_on = true?                    → NO: skip
  8. Overlord and count checks (same as short)      → NO: skip
  9. ENTER LONG
     Stop = pivot low - ATR buffer
     TP1  = entry + (stop_dist × 1.7)
     Size = (account × 0.5%) / stop_dist_in_dollars
```

---

## Exit Architecture

### Two-Stage Exit

Every trade enters with a full position. On the bar that TP1 is hit:

1. **Stage 1**: Close 50% of position at TP1 price, move stop to breakeven on remaining 50%
2. **Stage 2**: The runner (remaining 50%) is managed by an ATR trailing stop

The ATR trail is calculated as:
```pine
// Short runner trail
trail_stop = high - (ta.atr(14) × i_atr_trail_mult)  // 2.0 for short

// Long runner trail  
trail_stop = low  + (ta.atr(14) × i_atr_trail_mult_long)  // 1.25 for long
```

The trail only moves in the favorable direction (ratchets). Once Stage 1 is hit and the stop moves to breakeven, the worst case on the full trade is approximately breakeven (minus slippage on the runner half).

### EOD Flatten

At 15:45 ET, all open positions are closed at market regardless of P&L. This is a hard rule aligned with the Tradeify EOD drawdown model. The daily closing balance is what counts — intrabar excursions below the closing balance do not trigger the prop challenge drawdown rule. Flattening before 4 PM ET guarantees the closing balance reflects the day's actual P&L.

---

## Session Kill Zones

Only two sessions are eligible for new entries:

| Session | Name | Hours (ET) | Rationale |
|---------|------|-----------|-----------|
| Morning | Golden Window | 09:45 — 12:00 | Post-open momentum, volume, and directional conviction are highest in this window. Avoids the erratic first 15 minutes of the open. |
| Afternoon | Power Hour | 14:30 — 15:30 | Late-session directional moves driven by institutional positioning into the close. Volume picks back up after the midday lull. |

New entries are blocked outside these windows. Open positions continue to be managed (trail stops still move) but no new signals fire. This eliminates most of the choppy midday noise between 12:00 and 14:30 ET.

The EOD flatten at 15:30 ET (last entry allowed) ensures no positions are held into the final minutes of the session. The exact flatten time (15:45 ET) is set conservatively to close any position opened during Power Hour before the 4 PM close.

---

## Overlord Sentinel

The Overlord Sentinel is a meta-layer that sits above all entry logic. When any Overlord condition trips, `overlord_locked = true` and no new entries fire until the condition clears or is manually reset.

### Circuit Breakers

```pine
// VIX hard lock — macro fear too elevated
ov_cb_vix_lock = i_ov_vix_on and (i_vix_value >= i_ov_vix_hard)

// Rolling PF decay — recent trades underperforming
ov_cb_decay_lock = i_ov_decay_on and (rolling_pf < i_ov_pf_floor)

// Consecutive loss counter — tilt prevention
ov_cb_consec_lock = i_ov_consec_on and (consec_losses >= i_ov_max_consec)

// Macro regime gate — external Python input
macro_locked = i_macro_regime == "RISK-OFF"

// Master lock — any one trips it
overlord_locked = ov_cb_vix_lock or ov_cb_decay_lock
               or ov_cb_consec_lock or macro_locked
```

### Lock State Display

When locked, the Stark HUD displays the active reason in the regime row. The chart background turns red. A label appears at the current bar with the lock reason.

### Daily Loss Circuit Breaker

Separate from Overlord — a simple P&L check at the start of each new bar:

```pine
daily_pnl = strategy.netprofit - pnl_at_day_open
cb_triggered = daily_pnl <= -i_cb_daily_loss  // -$850
```

When triggered, `cb_fired = true` for the remainder of the trading day. Resets at midnight UTC (next session open).

---

## HUD Panel Descriptions

The Stark HUD is a `table.new()` panel in the top-right corner of the chart. It has 7 panels (groups of rows) covering different aspects of system state.

| Panel | Rows | Content |
|-------|------|---------|
| 1 — Engine Status | 1–6 | Long/short engine on/off, KNN enabled, daily trade count, session state, Overlord lock status |
| 2 — Current Trade | 7–12 | Entry price, stop, TP1, current P&L, R-multiple, stage (1 or 2) |
| 3 — Daily Stats | 13–18 | Day open balance, daily P&L, daily high/low P&L, trades today, CB status |
| 4 — Session Stats | 19–24 | GW trades/WR, PH trades/WR, total session P&L |
| 5 — KNN State | 25–30 | Short vote pct, long vote pct, neighbor distance, last signal bar |
| 6 — Overlord | 31–37 | VIX value, rolling PF, consecutive losses, macro regime, all 4 lock flags |
| 7 — Config Audit | 38–44 | All key parameter values displayed live for confirmation |

Color coding throughout:
- `#00ffbb` (mint) — healthy/positive
- `#EF9F27` (amber) — warning/caution
- `#E24B4A` (red) — locked/danger
- `#00e5ff` (cyan) — neutral/informational
- `#4a5568` (muted) — inactive/off
