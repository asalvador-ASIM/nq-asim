# Resume Section — NQ-ASIM Algorithmic Trading System

Copy-paste ready. Adjust username placeholder before use.

---

## Experience / Projects Block

**NQ-ASIM Algorithmic Trading System** | *Personal Project*
Jan 2026 — Present | github.com/[username]/nq-asim

- Built and validated a dual-engine algorithmic futures trading strategy on NQ/MNQ using Pine Script v6, achieving a profit factor of 4.342 and 72.22% win rate across 54 backtested trades targeting a Tradeify $50k EOD prop account
- Engineered a native K-Nearest Neighbors classifier in Pine Script scanning four market features (RVOL, ADX, EMA distance, VIX), improving profit factor 119% from 1.979 to 4.342 through systematic parameter optimization across six configuration iterations
- Developed a seven-process Python intelligence pipeline integrating the FRED API, NewsAPI, and yfinance to generate daily macro regime scores (NORMAL / CAUTION / RISK-OFF) that gate live trade execution based on VIX level, yield curve inversion, HY credit spreads, and news sentiment
- Built SENTINEL PRIME, a Plotly Dash real-time command dashboard featuring live arc gauge charts for six macro indicators, 30-day VIX trend visualization, rolling news sentiment analysis, economic calendar, and automated morning trading recommendations
- Implemented a full prop firm compliance layer including an $850 daily loss circuit breaker, profit lock thresholds, six-trade-per-day limits, and Overlord Sentinel risk gates covering VIX shocks, rolling profit factor decay, and consecutive loss streaks
- Deployed a production-grade system with Pushover mobile push alerts, a Flask webhook server receiving TradingView signals, automated daily morning briefings, and a health monitoring watchdog across seven concurrent processes

---

## Skills Block

Add these to your resume skills section:

**Languages**
Python, Pine Script v6

**Libraries & Frameworks**
Plotly Dash, pandas, yfinance, fredapi, newsapi-python, feedparser, python-dotenv, Flask

**APIs & Integrations**
FRED (Federal Reserve Economic Data), NewsAPI, Pushover, TradingView webhooks

**Concepts & Domains**
K-Nearest Neighbors classification, algorithmic trading strategy development, quantitative backtesting, risk management systems, prop trading compliance, technical analysis, macro regime analysis, time-series feature engineering

---

## Formatting Notes

- For a one-page resume, use 3 bullets instead of 6 — keep bullets 1, 2, and 3 (lead with the result, the algorithm, and the data pipeline)
- If the role is software engineering: emphasize bullets 3, 4, and 6 (Python pipeline, Dash dashboard, production deployment)
- If the role is quant/trading: emphasize bullets 1, 2, and 5 (backtest results, KNN discovery, risk architecture)
- The GitHub link is the proof point — make sure the repo is public and the README renders cleanly before submitting any application that references it
