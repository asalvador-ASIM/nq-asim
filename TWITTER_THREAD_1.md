# Twitter Thread 1 — NQ ASIM Launch

Post as a thread. One tweet per block. Keep each under 280 characters.

---

**Tweet 1 (Hook)**
Built a futures algo on NQ/MNQ. 15-minute chart, dual engine, no indicators stacked on indicators. Backtest: PF 4.342, 72% WR, 54 trades, max DD 0.71%. Building this in public. Here is how it works.

---

**Tweet 2 (What It Is)**
NQ ASIM is a breakout system with a KNN intelligence layer. It identifies pivot-based breakouts, filters by trend, volume, and session, then asks a nearest-neighbors classifier whether current market conditions match historical winning setups.

---

**Tweet 3 (Short Engine)**
Short engine: pivot low breaks, price below 200 EMA, RVOL above 1.2x, ADX above 20. If those pass, 8 nearest historical neighbors vote. If win rate among those 8 is above 50%, trade fires. Two-stage exit: partial at 2.6R, trail the runner.

---

**Tweet 4 (KNN Discovery)**
The biggest edge came from reducing KNN K from 150 to 8. 150 neighbors averages out regime. 8 neighbors finds setups that actually match what is happening now. Smaller K, sharper signal selection. This was not obvious until I tested it.

---

**Tweet 5 (Long Engine)**
Long engine runs separately with tighter parameters. Stage 1 exit at 1.7R instead of 2.6R — locks profit faster on mean-reversion tendencies. ATR trail multiplier tightened to 1.25. Long KNN runs its own vote pool independent of short engine.

---

**Tweet 6 (Risk Management)**
Risk rules: 0.5% per trade, $850 daily loss hard stop, max 6 trades per day, only trade Golden Window and Power Hour sessions. Overlord layer halts all trading if VIX exceeds 35, rolling PF drops below 0.50, or 6 consecutive losses occur.

---

**Tweet 7 (CTA)**
System trades a $50k Tradeify prop account. Posting every significant result, every param change, and every loss. No filtered highlights. If you are building systematic futures strategies, follow along. Thread updates as the equity curve develops.
