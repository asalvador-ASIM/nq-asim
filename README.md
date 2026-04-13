# NQ-ASIM — Dual Engine Algorithmic Trading System

> KNN-powered futures strategy for NQ/MNQ | Tradeify $50k prop account | Pine Script v6 + Python

![Pine Script v6](https://img.shields.io/badge/Pine_Script-v6-blue?style=flat-square)
![Python 3.14](https://img.shields.io/badge/Python-3.14-blue?style=flat-square&logo=python)
![Profit Factor](https://img.shields.io/badge/Backtest_PF-4.342-brightgreen?style=flat-square)
![Win Rate](https://img.shields.io/badge/Win_Rate-72.22%25-brightgreen?style=flat-square)
![Max Drawdown](https://img.shields.io/badge/Max_DD-0.71%25-green?style=flat-square)
![Status](https://img.shields.io/badge/Status-Live_Trading-brightgreen?style=flat-square)

---

## Performance Summary

| Metric | Value |
|--------|-------|
| Net P&L (backtest) | +$26,031 |
| Profit Factor | 4.342 |
| Win Rate | 72.22% (39/54) |
| Max Drawdown | 0.71% |
| Total Trades | 54 |
| Test Period | Nov 2 2025 — Apr 10 2026 |
| Timeframe | 15m MNQ1! |
| Account | Tradeify $50k EOD |

![Equity Curve](assets/equity_curve.png)

*Equity curve shows near-monotonic growth with minimal retracement — a consequence of the strict EOD flatten rule and per-trade risk capping at 0.5%.*

---

## System Architecture

```
┌─────────────────────────────────────────────┐
│              NQ-ASIM SYSTEM STACK            │
├─────────────────────────────────────────────┤
│  TradingView (Pine Script v6)               │
│  ├── Short Engine  (KNN classifier)         │
│  ├── Long Engine   (separate KNN pool)      │
│  ├── Overlord Sentinel  (risk gates)        │
│  └── Stark HUD  (live performance panel)   │
├─────────────────────────────────────────────┤
│  Python Intelligence Layer                  │
│  ├── macro_intelligence.py  (FRED+NewsAPI)  │
│  ├── morning_brief.py  (daily briefing)     │
│  ├── webhook_server.py  (alert receiver)    │
│  ├── dashboard.py  (SENTINEL PRIME HUD)     │
│  ├── notifications.py  (Pushover alerts)    │
│  └── health_monitor.py  (system watchdog)  │
├─────────────────────────────────────────────┤
│  Data Sources                               │
│  ├── FRED API  (VIX, yield curve, HY spread)│
│  ├── NewsAPI   (sentiment scoring)          │
│  ├── yfinance  (pre-market futures)         │
│  └── CBOE:VIX  (TradingView feed)          │
└─────────────────────────────────────────────┘
```

---

## How It Works

### KNN Intelligence Filter

K-Nearest Neighbors (KNN) is a classification algorithm that answers one question: given current market conditions, do the most similar historical setups tend to win or lose? Rather than fitting a curve to data, it stores examples and votes at inference time. There is no training phase — it looks up its neighbors on every bar.

NQ-ASIM uses four features to describe the current market state: RVOL (relative volume ratio against a 20-bar average), ADX (directional strength 0–100), EMA distance normalized by ATR (how extended price is from the 200 EMA), and VIX (macro fear index). Each feature captures a different dimension of market quality. RVOL filters low-participation moves. ADX filters choppy, non-trending bars. EMA distance identifies overextension risk. VIX captures macro regime.

The key discovery during development was the effect of K — the number of neighbors used in the vote. At K=150, the classifier was averaging over 150 historical setups spanning multiple different market regimes. The vote became a slow-moving consensus that barely changed bar to bar. At K=8, the classifier only considers the eight most similar historical bars. That specificity is what gives it edge: if the current bar looks like eight previous bars that all resolved in the same direction, that is a meaningful signal. If you dilute it with 142 more neighbors from different conditions, the signal disappears into noise.

Short and long engines run entirely separate KNN pools. The short engine uses its own lookback window and vote threshold. The long engine runs independently with its own parameter set. This matters because short and long setups in NQ do not occur in the same market conditions — forcing them to share a classifier would blur both signals.

### Dual Engine Design

**Short Engine** — the primary edge in the system:
- Profit Factor: 3.746 | Win Rate: 69.57% | Trades: 46
- Entry: N-bar pivot low breakout, price below 200 EMA, RVOL ≥ 1.2x, ADX ≥ 20
- KNN vote: K=8, lookback=200 bars, threshold=50% win rate among neighbors
- Stage 1 exit: 50% of position at 2.6R
- Stage 2 exit: ATR trailing stop on the runner (multiplier 2.0x)

**Long Engine** — secondary, mean-reversion oriented:
- Profit Factor: 26.075 | Win Rate: 87.50% | Trades: 8
- Entry: N-bar pivot high breakout, price above 200 EMA, same RVOL/ADX gates
- KNN runs a separate vote pool with K=7
- Stage 1 exit tightened to 1.7R (faster profit lock on mean-reversion tendencies)
- ATR trail multiplier tightened to 1.25x
- Lower trade frequency by design — only fires on high-confidence long setups

The long engine's high PF (26.075) on 8 trades should be read with appropriate caution. The sample size is small. The design intention for the long engine is selectivity, not volume. It fires rarely and exits quickly when it does.

### Risk Management

**Two-Stage Exit Architecture**  
Every trade splits position into two halves at entry. Stage 1 targets a fixed R-multiple (2.6R short / 1.7R long), books half the position, and moves the stop to breakeven on the runner. Stage 2 rides the runner with an ATR trailing stop. This structure locks in a minimum winning outcome on all Stage-1-reached trades while allowing outsized runners when momentum continues.

**Overlord Sentinel — Circuit Breakers**  
A dedicated risk module sits above the entry logic and can halt all new entries:

| Trigger | Threshold | Action |
|---------|-----------|--------|
| VIX hard lock | VIX ≥ 35 | No new entries |
| VIX warning | VIX ≥ 28 | Reduced size flag |
| Rolling PF decay | Last N trades PF < 0.50 | Lock |
| Consecutive losses | 6 in a row | Lock |
| Daily loss limit | −$850 | Circuit breaker |
| Macro regime | RISK-OFF | Full lock |

**Tradeify EOD Compliance**  
The account model is end-of-day drawdown: only the 4 PM ET closing balance counts, not intrabar excursions. This allows the strategy to run with tighter intraday stops without triggering the prop challenge drawdown rule. Hard rules enforced in code:
- Max 6 trades per day
- Mandatory EOD flatten at 15:45 ET
- Daily loss circuit breaker at −$850
- Profit lock above +$7,000 day (scale down after)

**Macro Regime Gate**  
Each morning, `macro_intelligence.py` pulls FRED data (VIX, yield curve, HY spreads, dollar index), NewsAPI headlines (scored for bearish/bullish sentiment), and NQ pre-market futures gap. It outputs a regime label — NORMAL, CAUTION, or RISK-OFF — which feeds into the `i_macro_regime` input on the Pine Script strategy. RISK-OFF locks all entries. CAUTION reduces to 1 contract.

### SENTINEL PRIME Dashboard

The Python layer includes a full Plotly Dash dashboard (`dashboard.py`) running at `localhost:8050`. It was designed as a Jarvis-style dark HUD — dark background (#050a0f), cyan/mint accent colors, CSS animations for regime state.

**Seven sections on the SENTINEL PRIME tab:**

1. **Header bar** — live ET clock, session state (Golden Window / Power Hour / Off-Hours), GW countdown timer, ONLINE indicator
2. **Ticker strip** — scrolling feed of VIX, NQ gap %, DXY, yield curve, HY spread, news score
3. **Regime banner** — animated border (green pulse / amber pulse / red rapid flash) based on current macro regime
4. **Vital signs row** — six Plotly gauge charts: VIX, Yield Curve, HY Spread, Dollar Index, NQ Pre-Market Gap, News Risk Score
5. **VIX history + Sentiment history** — 30-day VIX line chart with danger zones, 14-day rolling news sentiment bar chart
6. **News feed + Policy tracker** — live headlines from NewsAPI with risk badges, policy keyword detection (tariff/Fed/rate terms)
7. **Economic calendar + Trading recommendation** — week's high-impact events with impact rating, actionable morning recommendation card

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Strategy | Pine Script v6 (TradingView) |
| Dashboard | Python 3.14 + Plotly Dash |
| Macro data | FRED API (fredapi) |
| News sentiment | NewsAPI (newsapi-python) |
| Pre-market data | yfinance |
| Notifications | Pushover |
| Charts | Plotly |
| Styling | Custom CSS animations |

---

## Development Journey

The strategy started as a basic N-bar pivot breakout with a 200 EMA filter and session kill zones. At that stage it was functional but not differentiated — the PF on short-only was around 2.0, which is a reasonable baseline but not compelling enough to trade at size.

Adding the KNN classifier was the single largest improvement. The initial implementation used K=150 with a lookback of 200 bars. Results improved modestly. The insight came from systematically stepping K downward: K=50 was better, K=20 was better still, and K=8 produced a step-change improvement to PF 2.67. The mechanism is signal specificity — smaller K means the classifier only considers the closest matches, making it genuinely sensitive to current conditions rather than computing a long-run average.

Introducing the long engine as a separate module (with its own KNN pool and tighter exit parameters) added 8 additional trades over the backtest window, all high-confidence, and brought aggregate PF above 4.0. The dual-engine design respects the fact that short and long setups in NQ arise from fundamentally different conditions.

Final parameter tuning — adjusting the daily circuit breaker from the default $1,100 to $850 to match Tradeify's challenge requirements, tightening the long engine exits, and calibrating pivot lookback periods — brought the system to its peak configuration: PF 4.342, 72.22% WR, +$26,031 over 159 trading days.

The macro intelligence layer (SENTINEL PRIME) was added last, as a risk overlay rather than a signal source. It does not generate entries. It gates them — pulling the plug on live trading days when macro conditions fall outside the conditions the strategy was built for.

---

## Disclaimer

*Past performance does not guarantee future results. All backtest results are hypothetical and do not account for slippage, commissions, or execution differences between simulation and live trading. This repository is for educational and research purposes only. Nothing here constitutes financial advice. Futures trading involves substantial risk of loss. Only trade with capital you can afford to lose.*

---

## Repository Structure

```
asim1/
├── NQ ASIM.pine              # Main strategy (Pine Script v6)
├── dashboard.py              # SENTINEL PRIME dashboard
├── macro_intelligence.py     # FRED + NewsAPI macro engine
├── morning_brief.py          # Daily briefing generator
├── webhook_server.py         # TradingView alert receiver
├── health_monitor.py         # System watchdog
├── notifications.py          # Pushover push alerts
├── analytics.py              # Trade analytics engine
├── trade_journal.py          # Trade log processor
├── requirements.txt          # Python dependencies
├── requirements_macro.txt    # Macro layer dependencies
├── start_system.bat          # One-click system launcher
├── assets/
│   └── sentinel.css          # Dashboard CSS animations
├── data/
│   └── macro_regime.json     # Live macro regime output
└── github/
    ├── README.md             # This file
    ├── STRATEGY_OVERVIEW.md  # Pine Script deep dive
    ├── SETUP.md              # Installation guide
    ├── BACKTEST_RESULTS.md   # Full iteration history
    └── TWITTER_THREAD_1.md   # Launch thread
```
