# Setup Guide — NQ-ASIM Python Intelligence Layer

This guide covers setting up the Python system (SENTINEL PRIME dashboard, macro intelligence, webhook server, and notifications). The Pine Script strategy is installed separately in TradingView.

---

## Prerequisites

- Python 3.10 or later (developed on 3.14)
- Windows 10/11 (the `.bat` launchers are Windows — adapt for macOS/Linux if needed)
- A TradingView account with the NQ ASIM strategy loaded
- Internet connection for live API calls

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/your-username/nq-asim.git
cd nq-asim/asim1
```

Or download as ZIP and extract to a folder of your choice.

---

## Step 2 — Install Dependencies

There are two requirements files. The base file covers the webhook server and dashboard; the macro file covers the intelligence layer.

```bash
pip install -r requirements.txt
pip install -r requirements_macro.txt
```

Key packages installed:

| Package | Purpose |
|---------|---------|
| `dash` | Dashboard framework |
| `plotly` | Charts and gauges |
| `flask` | Webhook server |
| `fredapi` | FRED economic data |
| `newsapi-python` | News headline fetching |
| `yfinance` | Pre-market futures data |
| `feedparser` | RSS feed parsing |
| `python-dotenv` | .env file loading |
| `pushover2` | Push notifications |
| `pytz` | Timezone handling |

---

## Step 3 — Get Free API Keys

Two APIs are required. Both have free tiers that cover this use case.

### FRED API (Federal Reserve Economic Data)
1. Go to [https://fred.stlouisfed.org/](https://fred.stlouisfed.org/)
2. Create a free account
3. Navigate to **My Account → API Keys**
4. Request an API key (instant, free)
5. Copy the 32-character key

Used for: VIX (VIXCLS), yield curve (T10Y2Y), HY credit spreads (BAMLH0A0HYM2), Fed Funds rate (DFF), Dollar Index (DTWEXBGS)

### NewsAPI
1. Go to [https://newsapi.org/](https://newsapi.org/)
2. Create a free developer account
3. Your API key is shown on the dashboard
4. Free tier: 100 requests/day — sufficient for daily macro pulls

Used for: headline sentiment scoring (bearish/bullish keyword scan across top financial news)

### Optional: Pushover (mobile notifications)
1. Go to [https://pushover.net/](https://pushover.net/)
2. One-time $5 purchase for the mobile app
3. Create an application to get an app token
4. Your user key is on the dashboard

Used for: trade alerts, daily briefing push, system health warnings

---

## Step 4 — Configure .env File

Copy the template and fill in your keys:

```bash
cp env.template .env
```

Edit `.env`:

```env
# FRED API
FRED_API_KEY=your_fred_key_here

# NewsAPI
NEWS_API_KEY=your_newsapi_key_here

# Pushover (optional — notifications will be disabled if not set)
PUSHOVER_TOKEN=your_app_token_here
PUSHOVER_USER=your_user_key_here

# Webhook server port (default 5000)
WEBHOOK_PORT=5000

# Dashboard port (default 8050)
DASH_PORT=8050
```

The `.env` file is in `.gitignore` — it will not be committed to version control.

---

## Step 5 — Run the System

### Option A — One-Click Launcher (Windows)

```bat
start_system.bat
```

This opens four separate terminal windows:
1. `webhook_server.py` — listens for TradingView alerts on port 5000
2. `health_monitor.py` — monitors system components every 60 seconds
3. `macro_intelligence.py` — runs an initial macro pull and caches to `data/macro_regime.json`
4. `dashboard.py` — starts the SENTINEL PRIME dashboard on port 8050

### Option B — Manual Launch

Run each component in a separate terminal:

```bash
# Terminal 1 — Webhook server
python webhook_server.py

# Terminal 2 — Health monitor
python health_monitor.py

# Terminal 3 — Pull macro data (run each morning)
python macro_intelligence.py

# Terminal 4 — Dashboard
python dashboard.py
```

---

## Step 6 — Open the Dashboard

Navigate to:

```
http://localhost:8050
```

**Tab 1 — SENTINEL PRIME**
- Live ET clock and session state
- Scrolling macro ticker
- Regime banner (green/amber/red animation based on current macro)
- Six Plotly gauges: VIX, Yield Curve, HY Spread, Dollar Index, NQ Gap, News Score
- 30-day VIX history chart
- 14-day news sentiment history
- Top headlines with risk badges
- Policy keyword tracker
- Economic calendar
- Trading recommendation card

**Tab 2 — ALERT MONITOR**
- Live trade alerts from TradingView webhooks
- System health status
- Account stats

---

## Step 7 — Morning Workflow

Each trading morning before 9:30 AM ET:

```bash
python morning_brief.py
```

This generates a text brief covering:
- Macro regime assessment (NORMAL / CAUTION / RISK-OFF)
- VIX level and trend
- Yield curve state
- NQ pre-market gap and direction
- News sentiment score
- Any high-impact economic events today
- Trading recommendation (contracts, go/no-go)

The output is printed to terminal and pushed via Pushover if configured.

After running `morning_brief.py`, check `data/macro_regime.json` and update the `i_macro_regime` input in TradingView to match the Python output.

---

## TradingView Setup

1. Open TradingView Desktop
2. Load the `NQ ASIM.pine` strategy on MNQ1! 15-minute chart
3. In strategy settings, find **Group 8 — Overlord Sentinel**
4. Set `Macro Regime` to match today's Python output (NORMAL / CAUTION / RISK-OFF)
5. Configure TradingView webhook alerts to point at `http://your-ip:5000/webhook`

---

## File Structure Reference

```
asim1/
├── NQ ASIM.pine              # Pine Script strategy
├── dashboard.py              # SENTINEL PRIME Dash app
├── macro_intelligence.py     # Macro data engine
├── morning_brief.py          # Daily briefing
├── webhook_server.py         # Alert receiver (Flask)
├── health_monitor.py         # Watchdog process
├── notifications.py          # Pushover wrapper
├── analytics.py              # Trade analytics
├── trade_journal.py          # Trade log processor
├── requirements.txt          # Core dependencies
├── requirements_macro.txt    # Macro layer dependencies
├── env.template              # .env example (no keys)
├── start_system.bat          # Windows launcher
├── assets/
│   └── sentinel.css          # Dashboard CSS
└── data/
    ├── macro_regime.json     # Live macro output (auto-generated)
    └── sentiment_history.json # 14-day sentiment log (auto-generated)
```

---

## Troubleshooting

**Dashboard shows stale data**  
Run `python macro_intelligence.py` to force a fresh pull. The cache TTL is 60 minutes — if the JSON is older than that, the dashboard will note the timestamp.

**FRED API returns empty**  
FRED rate-limits free keys to ~120 requests/minute. The macro module batches all series in one session. If you see empty fields, wait a minute and retry.

**NewsAPI 426 error**  
The free developer tier is limited to 100 requests/day and cannot query older than 24 hours. Staying within that limit is straightforward with once-daily morning pulls.

**Webhook not receiving alerts**  
Check that port 5000 is open in your firewall. If running locally (not a server), TradingView webhooks require a publicly accessible URL — use ngrok or a similar tunnel during development.

**Port 8050 already in use**  
Another Dash instance is running. Kill it:
```bash
# Windows — find the PID
netstat -ano | findstr :8050
# Then kill it
taskkill /PID <pid> /F
```
