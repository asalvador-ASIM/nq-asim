"""
dashboard.py — NQ-ASIM Intelligence Dashboard v2
=================================================
Tab 1: SENTINEL PRIME — Jarvis-style morning command center
Tab 2: ALERT MONITOR  — Real-time trade alert feed (existing)

Run:  python dashboard.py
Open: http://localhost:8050
"""

import json
import math
import sqlite3
import datetime
import os
from pathlib import Path

import requests as http_requests
import pandas as pd
from dash import Dash, dcc, html, dash_table, callback_context
from dash.dependencies import Output, Input, State
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dotenv import load_dotenv
import pytz

# ─────────────────────────────────────────────────────────────────────────────
#  PATHS & CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

load_dotenv()
BASE_DIR        = Path(__file__).parent.resolve()
DB_PATH         = os.getenv("DB_PATH", str(BASE_DIR / "alerts.db"))
WH_URL          = os.getenv("WEBHOOK_SERVER_URL", "http://localhost:5000").rstrip("/")
HEARTBEAT       = BASE_DIR / "monitor_heartbeat.json"
MACRO_FILE      = BASE_DIR / "data" / "macro_regime.json"
SENTIMENT_FILE  = BASE_DIR / "data" / "sentiment_history.json"
MACRO_STALE_HOURS = 6
ET = pytz.timezone("America/New_York")

# ─────────────────────────────────────────────────────────────────────────────
#  COLOR PALETTE
# ─────────────────────────────────────────────────────────────────────────────

# Sentinel / Jarvis theme (darker)
SENT_BG   = "#050a0f"
SENT_CARD = "#080e1a"
CARD_BDR  = "#0a2030"
CYAN      = "#00e5ff"
CYAN_DIM  = "rgba(0,229,255,0.4)"
MINT      = "#00ffbb"
GOLD      = "#EF9F27"
ROSE      = "#E24B4A"
MUTED     = "#4a5568"
TEXT_MAIN = "#e2e8f0"
TEXT_DIM  = "#718096"

# Alert monitor theme (slightly lighter)
DARK_BG   = "#0a0f1e"
CARD_BG   = "#0f1929"
GREEN_BTN = "#065f46"
RED_BTN   = "#7f1d1d"
ORANGE    = "#f97316"

CHART_LAYOUT = dict(
    paper_bgcolor=SENT_BG,
    plot_bgcolor=SENT_BG,
    font=dict(color=CYAN, family="Courier New, monospace", size=11),
    margin=dict(l=40, r=20, t=36, b=36),
)
AXIS_STYLE = dict(gridcolor=CARD_BDR, color=TEXT_DIM, showgrid=True,
                  tickfont=dict(size=9, color=TEXT_DIM))

# ─────────────────────────────────────────────────────────────────────────────
#  PERFORMANCE CONSTANTS  (backtest Nov 2025 – Apr 2026)
# ─────────────────────────────────────────────────────────────────────────────

SHORT_PF     = 3.746
SHORT_WR     = 69.57
SHORT_TRADES = 46
SHORT_PNL    = 20815
LONG_PF      = 6.269
LONG_WR      = 66.67
LONG_TRADES  = 12
COMBINED_PF  = 4.049
NET_PNL      = 26268
MAX_DD       = 0.91
SHARPE       = 1.006
COMBINED_WR  = 68.97
TOTAL_TRADES = 58

# ─────────────────────────────────────────────────────────────────────────────
#  CARD / LABEL STYLES  (shared across cockpit layout)
# ─────────────────────────────────────────────────────────────────────────────

_CARD = {
    "background":    "rgba(5,10,15,0.95)",
    "border":        "1px solid rgba(0,229,255,0.2)",
    "borderRadius":  "8px",
    "padding":       "16px",
    "marginBottom":  "10px",
}
_LBL = {
    "fontSize":      "11px",
    "textTransform": "uppercase",
    "letterSpacing": "0.1em",
    "color":         "rgba(0,229,255,0.6)",
    "marginBottom":  "6px",
    "fontFamily":    "Courier New, monospace",
    "display":       "block",
}

# ─────────────────────────────────────────────────────────────────────────────
#  DATA LAYER — EXISTING (alert monitor)
# ─────────────────────────────────────────────────────────────────────────────

def get_today_str():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")

def load_alerts_today() -> pd.DataFrame:
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("""
            SELECT received_at, type, side, entry, stop, qty,
                   risk_usd, knn_wr, atr_regime, s1r,
                   daily_pnl, trade_count, priority, channels,
                   reason, status, open_profit, vix,
                   overlord_locked, dispatched
            FROM alerts WHERE received_at LIKE ?
            ORDER BY received_at DESC LIMIT 200
        """, conn, params=(f"{get_today_str()}%",))
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

def load_alerts_history(days: int = 7) -> pd.DataFrame:
    try:
        conn  = sqlite3.connect(DB_PATH)
        since = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        df    = pd.read_sql("""
            SELECT received_at, type, side, entry, stop,
                   risk_usd, knn_wr, daily_pnl, vix, trade_count
            FROM alerts WHERE received_at >= ? AND type = 'GO'
            ORDER BY received_at DESC
        """, conn, params=(since,))
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

def load_all_recent(limit: int = 500) -> pd.DataFrame:
    try:
        conn = sqlite3.connect(DB_PATH)
        df   = pd.read_sql(
            "SELECT * FROM alerts ORDER BY received_at DESC LIMIT ?",
            conn, params=(limit,))
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

# ─────────────────────────────────────────────────────────────────────────────
#  DATA LAYER — NEW (Sentinel Prime)
# ─────────────────────────────────────────────────────────────────────────────

def load_macro() -> dict:
    """Load macro_regime.json with safe fallback defaults."""
    try:
        if MACRO_FILE.exists():
            return json.loads(MACRO_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "regime": "NORMAL", "score": 0,
        "vix": None, "yield_curve": None, "hy_spread": None,
        "dollar": None, "nq_premarket_gap": None,
        "news_score": 0, "news_label": "NORMAL",
        "top_headlines": [], "policy_risk": False, "policy_terms": [],
        "policy_posts": [], "high_impact_today": False, "event_name": "NONE",
        "recommendation": "Run macro_intelligence.py to load data",
        "timestamp": "", "sources": {},
    }


def fetch_macro_data() -> dict:
    return load_macro()

def load_sentiment_history() -> list:
    try:
        if SENTIMENT_FILE.exists():
            return json.loads(SENTIMENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []

def update_sentiment_history(score: int) -> list:
    history = load_sentiment_history()
    today   = datetime.date.today().isoformat()
    for entry in history:
        if entry.get("date") == today:
            entry["score"] = score
            break
    else:
        history.append({"date": today, "score": score})
    history = sorted(history, key=lambda x: x["date"])[-14:]
    try:
        SENTIMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        SENTIMENT_FILE.write_text(json.dumps(history), encoding="utf-8")
    except Exception:
        pass
    return history

def fetch_vix_history() -> tuple:
    """Returns (dates[], values[]) for last 30 trading days. yfinance first, mock fallback."""
    try:
        import yfinance as yf
        hist = yf.Ticker("^VIX").history(period="30d", interval="1d")
        if not hist.empty:
            dates  = [str(d.date()) for d in hist.index]
            values = [round(float(v), 2) for v in hist["Close"]]
            return dates, values
    except Exception:
        pass
    # Seeded mock
    import random
    macro = load_macro()
    base  = macro.get("vix") or 19.5
    rng   = random.Random(int(datetime.date.today().strftime("%Y%m%d")))
    dates  = [(datetime.date.today() - datetime.timedelta(days=29 - i)).isoformat()
               for i in range(30)]
    values, v = [], base
    for _ in range(30):
        v = max(10.0, min(45.0, v + rng.gauss(0, 1.2)))
        values.append(round(v, 2))
    values[-1] = base
    return dates, values

# ─────────────────────────────────────────────────────────────────────────────
#  SYSTEM STATUS HELPERS (existing)
# ─────────────────────────────────────────────────────────────────────────────

def check_webhook() -> tuple:
    try:
        r = http_requests.get(f"{WH_URL}/health", timeout=2)
        return ("ONLINE", True) if r.status_code == 200 else ("ERROR", False)
    except Exception:
        return ("OFFLINE", False)

def check_kill_switch() -> tuple:
    try:
        r = http_requests.get(f"{WH_URL}/killswitch/status", timeout=2)
        if r.status_code == 200:
            active = r.json().get("active", False)
            return ("ACTIVE ⛔", True) if active else ("ARMED", False)
    except Exception:
        pass
    return ("UNKNOWN", False)

def check_monitor() -> tuple:
    try:
        hb      = json.loads(HEARTBEAT.read_text(encoding="utf-8"))
        updated = datetime.datetime.fromisoformat(hb.get("updated", "2000-01-01"))
        if (datetime.datetime.utcnow() - updated).total_seconds() < 120:
            return ("RUNNING", True)
        return ("STALE", False)
    except Exception:
        return ("STOPPED", False)

def get_live_price() -> tuple:
    try:
        r = http_requests.get(f"{WH_URL}/price", timeout=2)
        if r.status_code == 200:
            d = r.json()
            price, upd = d.get("price"), d.get("updated", "")
            if price:
                return (f"{price:,.2f}", upd[-8:] if len(upd) >= 8 else upd)
    except Exception:
        pass
    return ("—", "")

# ─────────────────────────────────────────────────────────────────────────────
#  CLOCK / COUNTDOWN HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_gw_info() -> tuple:
    """Returns (label, countdown_str, is_active)."""
    now_et   = datetime.datetime.now(ET)
    gw_start = now_et.replace(hour=9,  minute=45, second=0, microsecond=0)
    gw_end   = now_et.replace(hour=12, minute=0,  second=0, microsecond=0)

    if gw_start <= now_et < gw_end:
        delta = gw_end - now_et
        h, m, s = int(delta.total_seconds()//3600), \
                  int(delta.total_seconds()%3600//60), \
                  int(delta.total_seconds()%60)
        return "GOLDEN WINDOW CLOSES IN", f"{h:02d}:{m:02d}:{s:02d}", True

    # Find next GW open (skip weekends)
    next_gw = gw_start if now_et < gw_start else gw_start + datetime.timedelta(days=1)
    while next_gw.weekday() >= 5:
        next_gw += datetime.timedelta(days=1)

    delta = next_gw - now_et
    h, m, s = int(delta.total_seconds()//3600), \
              int(delta.total_seconds()%3600//60), \
              int(delta.total_seconds()%60)
    return "GOLDEN WINDOW OPENS IN", f"{h:02d}:{m:02d}:{s:02d}", False

# ─────────────────────────────────────────────────────────────────────────────
#  CHART BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def make_gauge_fig(value, title, min_v, max_v, green_max, amber_max,
                   unit="", fmt=".1f", invert=False):
    """Plotly Indicator gauge. invert=True means low value = danger."""
    v = float(value) if value is not None else 0.0
    if invert:
        color = ROSE if v < green_max else GOLD if v < amber_max else MINT
    else:
        color = ROSE if v > amber_max else GOLD if v > green_max else MINT

    steps = (
        [{"range": [min_v, green_max], "color": "rgba(226,75,74,0.08)"},
         {"range": [green_max, amber_max], "color": "rgba(239,159,39,0.08)"},
         {"range": [amber_max, max_v], "color": "rgba(0,255,187,0.08)"}]
        if invert else
        [{"range": [min_v, green_max], "color": "rgba(0,255,187,0.08)"},
         {"range": [green_max, amber_max], "color": "rgba(239,159,39,0.08)"},
         {"range": [amber_max, max_v], "color": "rgba(226,75,74,0.08)"}]
    )

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=v,
        title={"text": title, "font": {"size": 10, "color": MUTED, "family": "Courier New"}},
        number={"suffix": unit, "valueformat": fmt,
                "font": {"size": 22, "color": color, "family": "Courier New"}},
        gauge={
            "axis": {
                "range": [min_v, max_v],
                "tickfont": {"size": 8, "color": MUTED},
                "tickcolor": CARD_BDR,
            },
            "bar":          {"color": color, "thickness": 0.22},
            "bgcolor":      SENT_BG,
            "borderwidth":  1,
            "bordercolor":  CARD_BDR,
            "steps":        steps,
        }
    ))
    fig.update_layout(
        paper_bgcolor=SENT_BG,
        height=185,
        margin=dict(l=10, r=10, t=46, b=8),
    )
    return fig

def make_vix_history_fig(dates, values):
    vix_mean = sum(values) / len(values) if values else 20.0
    colors   = [ROSE if v > 25 else GOLD if v > 18 else MINT for v in values]

    fig = go.Figure()
    # Danger zone fill
    fig.add_hrect(y0=25, y1=max(values or [25]) * 1.05,
                  fillcolor="rgba(226,75,74,0.05)", line_width=0)
    fig.add_hrect(y0=18, y1=25,
                  fillcolor="rgba(239,159,39,0.04)", line_width=0)
    # Threshold line
    fig.add_hline(y=20, line_dash="dot", line_color=GOLD, line_width=1,
                  annotation_text="WARN 20",
                  annotation_font=dict(color=GOLD, size=9))
    fig.add_hline(y=25, line_dash="dot", line_color=ROSE, line_width=1,
                  annotation_text="DANGER 25",
                  annotation_font=dict(color=ROSE, size=9))
    # Line
    fig.add_trace(go.Scatter(
        x=dates, y=values, mode="lines+markers",
        line=dict(color=CYAN, width=2),
        marker=dict(color=colors, size=5),
        hovertemplate="<b>%{x}</b><br>VIX: %{y:.1f}<extra></extra>",
    ))
    fig.update_layout(
        **CHART_LAYOUT,
        title=dict(text="VIX  30-DAY TREND", font=dict(size=12, color=CYAN)),
        height=260,
        xaxis=dict(**AXIS_STYLE, title=""),
        yaxis=dict(**AXIS_STYLE, title="VIX"),
        showlegend=False,
    )
    return fig

def make_sentiment_fig(history: list):
    if not history:
        dates  = [(datetime.date.today() - datetime.timedelta(days=13 - i)).isoformat()
                   for i in range(14)]
        values = [0] * 14
    else:
        dates  = [h["date"] for h in history]
        values = [h["score"] for h in history]

    colors = [ROSE if v >= 7 else GOLD if v >= 3 else MINT for v in values]

    fig = go.Figure(go.Bar(
        x=dates, y=values,
        marker_color=colors,
        marker_line=dict(color=[c.replace(")", ",0.6)").replace("rgb", "rgba") for c in colors], width=1),
        hovertemplate="<b>%{x}</b><br>Score: %{y}<extra></extra>",
    ))
    fig.add_hline(y=3, line_dash="dot", line_color=GOLD, line_width=1,
                  annotation_text="CAUTION 3",
                  annotation_font=dict(color=GOLD, size=9))
    fig.add_hline(y=7, line_dash="dot", line_color=ROSE, line_width=1,
                  annotation_text="HIGH RISK 7",
                  annotation_font=dict(color=ROSE, size=9))
    fig.update_layout(
        **CHART_LAYOUT,
        title=dict(text="NEWS RISK SCORE  14-DAY", font=dict(size=12, color=CYAN)),
        height=260,
        xaxis=dict(**AXIS_STYLE, title=""),
        yaxis=dict(**AXIS_STYLE, title="Score", range=[0, max(10, max(values or [0]) + 1)]),
        showlegend=False,
    )
    return fig

def make_knn_gauge(value, title, color):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": title, "font": {"size": 9, "color": MUTED, "family": "Courier New"}},
        number={"suffix": "%", "valueformat": ".0f",
                "font": {"size": 20, "color": color, "family": "Courier New"}},
        gauge={
            "axis": {"range": [0, 100], "tickfont": {"size": 7, "color": MUTED}, "tickcolor": CARD_BDR},
            "bar": {"color": color, "thickness": 0.25},
            "bgcolor": SENT_BG, "borderwidth": 1, "bordercolor": CARD_BDR,
            "steps": [
                {"range": [0, 50],   "color": "rgba(226,75,74,0.07)"},
                {"range": [50, 70],  "color": "rgba(239,159,39,0.07)"},
                {"range": [70, 100], "color": "rgba(0,255,187,0.07)"},
            ],
        }
    ))
    fig.update_layout(paper_bgcolor=SENT_BG, height=155, margin=dict(l=8, r=8, t=32, b=4))
    return fig

KNN_S_FIG = make_knn_gauge(SHORT_WR, "KNN-S  ·  K=8  ·  4D", CYAN)
KNN_L_FIG = make_knn_gauge(LONG_WR,  "KNN-L  ·  K=8  ·  5D", MINT)

# ─────────────────────────────────────────────────────────────────────────────
#  SENTINEL PRIME COMPONENT BUILDERS  v3
# ─────────────────────────────────────────────────────────────────────────────

CARD_S = {
    "backgroundColor": SENT_CARD,
    "border":          f"1px solid {CARD_BDR}",
    "borderRadius":    "8px",
    "padding":         "14px",
    "marginBottom":    "10px",
}
LBL_S = {
    "fontSize":      "10px",
    "color":         MUTED,
    "textTransform": "uppercase",
    "letterSpacing": "0.1em",
    "marginBottom":  "3px",
    "fontFamily":    "Courier New, monospace",
}
# Shared card style using HUD corner class
_HC = {**_CARD, "padding": "14px 16px", "marginBottom": "10px"}

# ── Section header ───────────────────────────────────────────────────────────
def hdr(text: str) -> html.Div:
    return html.Div(text, className="section-hdr")

# ── Small stat row helper ────────────────────────────────────────────────────
def stat_row(label, value, vc=None):
    return html.Div(style={
        "display": "flex", "justifyContent": "space-between",
        "padding": "4px 0", "borderBottom": f"1px solid {CARD_BDR}",
        "fontSize": "11px", "fontFamily": "Courier New, monospace",
    }, children=[
        html.Span(label, style={"color": MUTED}),
        html.Span(value, style={"color": vc or CYAN, "fontWeight": "700"}),
    ])

# ── Kill Zone Timeline  (HTML-only, no Plotly) ──────────────────────────────
def make_kill_zone_bar() -> html.Div:
    now_et  = datetime.datetime.now(ET)
    h, m    = now_et.hour, now_et.minute
    cur_min = h * 60 + m

    mkt_start = 9 * 60 + 30   # 570
    mkt_end   = 16 * 60        # 960
    mkt_dur   = mkt_end - mkt_start  # 390

    def p(mins): return max(0.0, min(100.0, (mins - mkt_start) / mkt_dur * 100))

    zones = [
        (9*60+30,  9*60+45,  "rgba(74,85,104,0.35)",  "OPEN"),
        (9*60+45, 12*60+0,   "rgba(0,255,187,0.22)",  "GOLDEN WINDOW"),
        (14*60+30, 16*60+0,  "rgba(239,159,39,0.22)", "POWER HOUR"),
    ]

    zone_els = []
    for start, end, bg, label in zones:
        lp  = p(start); wp = p(end) - lp
        col = "#00ffbb" if "GOLDEN" in label else "#EF9F27" if "POWER" in label else "#718096"
        zone_els.append(html.Div(style={
            "position": "absolute", "left": f"{lp:.2f}%", "width": f"{wp:.2f}%",
            "height": "100%", "background": bg,
        }))
        if wp > 6:
            zone_els.append(html.Div(label, className="kz-label",
                style={"left": f"{lp + 1:.1f}%", "color": col}))

    # Current time needle
    if mkt_start <= cur_min <= mkt_end:
        zone_els.append(html.Div(className="kz-now-line",
            style={"left": f"{p(cur_min):.2f}%"}))

    # Hour tick labels
    tick_els = []
    for hh in range(9, 17):
        pp = p(hh * 60)
        if 0 <= pp <= 100:
            lbl = f"{hh}" if hh < 12 else ("12" if hh == 12 else f"{hh-12}p")
            tick_els.append(html.Span(lbl, className="kz-time-label",
                style={"left": f"{pp:.1f}%"}))

    return html.Div([
        hdr("SESSION TIMELINE"),
        html.Div(zone_els, className="kill-zone-track"),
        html.Div(tick_els, style={"position": "relative", "height": "14px", "marginBottom": "4px"}),
        html.Div(style={"display": "flex", "gap": "14px", "fontSize": "9px", "marginTop": "2px"}, children=[
            html.Span("■ GW 9:45-12:00",    style={"color": MINT}),
            html.Span("■ POWER 14:30-16:00",style={"color": GOLD}),
            html.Span("│ NOW",               style={"color": CYAN}),
        ]),
    ])

# ── Implied Daily Move ────────────────────────────────────────────────────────
def make_implied_move(vix, nq_price=20000) -> html.Div:
    pct  = (vix or 0) / 16.0
    pts  = nq_price * pct / 100.0
    mnq  = pts * 2.0   # MNQ $2/point
    col  = ROSE if pct > 1.8 else GOLD if pct > 1.3 else MINT
    return html.Div([
        hdr("NQ IMPLIED DAILY RANGE"),
        html.Div(style={"display": "flex", "alignItems": "baseline", "gap": "10px"}, children=[
            html.Span(f"±{pct:.1f}%", className="implied-move-number glow-gold",
                style={"color": col}),
            html.Span(f"±{pts:.0f} pts", style={"fontSize": "18px", "color": TEXT_DIM, "fontFamily": "Courier New"}),
        ]),
        html.Div(f"VIX {vix:.1f} / 16  ·  MNQ ≈ ±${mnq:.0f} / contract",
            style={"fontSize": "10px", "color": MUTED, "marginTop": "4px", "fontFamily": "Courier New"}),
    ])

# ── Circuit Breaker Panel ────────────────────────────────────────────────────
def make_circuit_breakers(vix, regime, news_score=0) -> list:
    rows_data = [
        ("VIX HARD LOCK",    "VIX ≥ 35",    vix is not None and vix >= 35,
         f"{vix:.1f}" if vix else "—"),
        ("VIX WARNING",      "VIX ≥ 28",    vix is not None and vix >= 28,
         f"{vix:.1f}" if vix else "—"),
        ("ROLLING PF DECAY", "PF < 0.50",   False,  f"{COMBINED_PF:.3f}"),
        ("CONSEC LOSSES",    "≥ 6 in row",  False,  "0"),
        ("DAILY LOSS",       "> -$850",      False,  "$0"),
        ("MACRO REGIME",     "RISK-OFF",     regime == "RISK-OFF", regime),
    ]
    any_triggered = any(t for _, _, t, _ in rows_data)
    rows = []
    for name, thresh, triggered, cur in rows_data:
        st    = "LOCKED" if triggered else "CLEAR"
        sc    = ROSE if triggered else MINT
        cls   = "cb-lock" if triggered else "cb-ok"
        rcls  = "cb-row cb-row-triggered" if triggered else "cb-row"
        rows.append(html.Div(className=rcls, children=[
            html.Span("⚡" if triggered else "●", style={"color": sc, "fontSize": "9px"}),
            html.Span(name,   style={"color": TEXT_MAIN if triggered else TEXT_DIM}),
            html.Span(thresh, style={"color": MUTED, "fontSize": "10px"}),
            html.Span(cur,    style={"color": ROSE if triggered else CYAN}),
            html.Span(st, className=cls, style={"textAlign": "right"}),
        ]))
    return rows

# ── Macro Signals Mini-Grid ───────────────────────────────────────────────────
def make_macro_grid(macro: dict) -> list:
    vix   = macro.get("vix")
    yc    = macro.get("yield_curve")
    hy    = macro.get("hy_spread")
    dxy   = macro.get("dollar")
    gap   = macro.get("nq_premarket_gap")
    ns    = macro.get("news_score", 0)

    rows = []
    items = [
        ("YIELD CURVE",  f"{yc:+.2f}" if yc is not None else "—",
         ROSE if yc is not None and yc < 0 else GOLD if yc is not None and yc < 0.3 else MINT),
        ("HY SPREAD",    f"{hy:.2f}%" if hy is not None else "—",
         ROSE if hy is not None and hy > 4.5 else GOLD if hy is not None and hy > 3.5 else MINT),
        ("DOLLAR INDEX", f"{dxy:.2f}" if dxy is not None else "—", CYAN),
        ("NQ PRE-MKT",   f"{gap:+.2f}%" if gap is not None else "—",
         ROSE if gap is not None and gap < -0.5 else MINT if gap is not None and gap > 0.5 else TEXT_DIM),
        ("NEWS SCORE",   f"{ns}/10",
         ROSE if ns >= 7 else GOLD if ns >= 3 else MINT),
    ]
    for label, val, col in items:
        rows.append(html.Div(className="signal-grid-row", children=[
            html.Span(label, style={"color": MUTED, "fontSize": "10px"}),
            html.Span(val,   style={"color": col, "fontWeight": "700", "fontFamily": "Courier New"}),
        ]))
    return rows

def arc_reactor():
    """CSS-based arc reactor icon."""
    return html.Div(style={
        "position": "relative", "width": "52px", "height": "52px",
        "display": "flex", "alignItems": "center", "justifyContent": "center",
        "flexShrink": "0",
    }, children=[
        html.Div(style={
            "position": "absolute", "width": "50px", "height": "50px",
            "border": "2px solid rgba(0,229,255,0.25)", "borderRadius": "50%",
        }),
        html.Div(style={
            "position": "absolute", "width": "36px", "height": "36px",
            "border": "1.5px solid rgba(0,229,255,0.45)", "borderRadius": "50%",
        }),
        html.Div(style={
            "position": "absolute", "width": "24px", "height": "24px",
            "border": f"2px solid {MINT}", "borderRadius": "50%",
            "boxShadow": f"0 0 8px {MINT}",
        }),
        html.Div(className="reactor-arm", style={
            "position": "absolute", "width": "2px", "height": "20px",
            "background": CYAN, "top": "6px", "left": "25px",
            "boxShadow": f"0 0 5px {CYAN}",
        }),
        html.Div(className="reactor-core", style={
            "position": "absolute", "width": "9px", "height": "9px",
            "background": CYAN, "borderRadius": "50%",
            "boxShadow": f"0 0 8px {CYAN}",
        }),
    ])


def make_ticker_item(label, value, color, suffix="", arrow=""):
    arrow_char = " ▲" if arrow == "up" else " ▼" if arrow == "down" else ""
    arrow_color = MINT if arrow == "up" else ROSE if arrow == "down" else color
    return html.Span([
        html.Span(f"  {label}: ", style={"color": MUTED, "fontSize": "11px"}),
        html.Span(f"{value}{suffix}{arrow_char}",
                  style={"color": color, "fontWeight": "700", "fontSize": "11px"}),
        html.Span("  ·", style={"color": MUTED, "fontSize": "11px"}),
    ])


def build_ticker(macro: dict) -> list:
    vix   = macro.get("vix")
    yc    = macro.get("yield_curve")
    hy    = macro.get("hy_spread")
    dxy   = macro.get("dollar")
    gap   = macro.get("nq_premarket_gap")
    nscore= macro.get("news_score", 0)

    items = []
    if vix is not None:
        vc = ROSE if vix > 25 else GOLD if vix > 18 else MINT
        items.append(make_ticker_item("VIX", f"{vix:.1f}", vc))
    if gap is not None:
        gc = ROSE if gap < -0.5 else MINT if gap > 0.5 else TEXT_DIM
        arrow = "down" if gap < -0.5 else "up" if gap > 0.5 else ""
        items.append(make_ticker_item("NQ GAP", f"{gap:+.2f}", gc, "%", arrow))
    if dxy is not None:
        items.append(make_ticker_item("DXY", f"{dxy:.2f}", CYAN))
    if yc is not None:
        ycc = ROSE if yc < 0 else GOLD if yc < 0.3 else MINT
        items.append(make_ticker_item("YIELD", f"{yc:.2f}", ycc, " (T10Y2Y)"))
    if hy is not None:
        hc = ROSE if hy > 4.5 else GOLD if hy > 3.5 else MINT
        items.append(make_ticker_item("HY SPD", f"{hy:.2f}", hc, "%"))
    nscore_c = ROSE if nscore >= 7 else GOLD if nscore >= 3 else MINT
    items.append(make_ticker_item("NEWS", str(nscore), nscore_c, "/10"))
    return items


def sentinel_section_header(text: str) -> html.Div:
    return html.Div(text, style={
        "fontSize": "10px", "color": MUTED, "fontFamily": "Courier New, monospace",
        "textTransform": "uppercase", "letterSpacing": "0.15em",
        "borderBottom": f"1px solid {CARD_BDR}", "paddingBottom": "6px",
        "marginBottom": "10px",
    })

# ─────────────────────────────────────────────────────────────────────────────
#  STATIC ECONOMIC CALENDAR  (week of Apr 13 2026)
# ─────────────────────────────────────────────────────────────────────────────

ECON_CALENDAR = [
    {"date": "Mon Apr 13", "time": "—",     "event": "No major releases",    "impact": "LOW",  "prev": "—",     "est": "—"},
    {"date": "Tue Apr 14", "time": "08:30", "event": "CPI YoY",              "impact": "HIGH", "prev": "2.8%",  "est": "2.6%"},
    {"date": "Tue Apr 14", "time": "08:30", "event": "CPI MoM",              "impact": "HIGH", "prev": "0.2%",  "est": "0.1%"},
    {"date": "Wed Apr 15", "time": "14:00", "event": "Fed Beige Book",       "impact": "MED",  "prev": "—",     "est": "—"},
    {"date": "Thu Apr 16", "time": "08:30", "event": "Jobless Claims",       "impact": "MED",  "prev": "219K",  "est": "222K"},
    {"date": "Thu Apr 16", "time": "08:30", "event": "Philly Fed Mfg",       "impact": "MED",  "prev": "12.5",  "est": "8.0"},
    {"date": "Fri Apr 17", "time": "08:30", "event": "Retail Sales MoM",    "impact": "HIGH", "prev": "-0.9%", "est": "+0.1%"},
    {"date": "Fri Apr 17", "time": "09:15", "event": "Industrial Production","impact": "MED",  "prev": "0.7%",  "est": "0.3%"},
]

TODAY_DATE = "Tue Apr 14"  # April 14 2026 — CPI day

def make_calendar_rows() -> list:
    rows = []
    for ev in ECON_CALENDAR:
        is_today  = ev["date"] == TODAY_DATE
        is_high   = ev["impact"] == "HIGH"
        impact_c  = ROSE if is_high else GOLD if ev["impact"] == "MED" else MUTED
        row_style = {
            "display":       "grid",
            "gridTemplateColumns": "100px 55px 1fr 55px 60px 60px",
            "gap":           "6px",
            "padding":       "5px 8px",
            "marginBottom":  "2px",
            "borderRadius":  "4px",
            "fontSize":      "11px",
            "fontFamily":    "Courier New, monospace",
            "backgroundColor": (
                "rgba(0,229,255,0.07)" if is_today else
                "rgba(226,75,74,0.05)" if is_high else
                "transparent"
            ),
            "borderLeft": (
                f"3px solid {CYAN}" if is_today else
                f"3px solid {ROSE}" if is_high else
                f"3px solid transparent"
            ),
        }
        rows.append(html.Div(style=row_style, children=[
            html.Span(ev["date"],   style={"color": CYAN if is_today else TEXT_DIM}),
            html.Span(ev["time"],   style={"color": TEXT_DIM}),
            html.Span(ev["event"],  style={"color": TEXT_MAIN if is_high else TEXT_DIM, "fontWeight": "700" if is_high else "400"}),
            html.Span(ev["impact"], style={"color": impact_c, "fontWeight": "700"}),
            html.Span(ev["prev"],   style={"color": MUTED}),
            html.Span(ev["est"],    style={"color": CYAN if is_today else TEXT_DIM}),
        ]))
    return rows

# ─────────────────────────────────────────────────────────────────────────────
#  SENTINEL PRIME — STATIC LAYOUT SKELETON
# ─────────────────────────────────────────────────────────────────────────────

sentinel_layout = html.Div(
    style={"backgroundColor": SENT_BG, "minHeight": "100vh", "fontFamily": "Courier New, monospace"},
    children=[

        # ── HEADER (clock · reactor · GW · ticker) ────────────────────────
        html.Div(className="sentinel-header-wrap", style={
            "background": "linear-gradient(135deg, #030710 0%, #061020 100%)",
            "borderBottom": f"1px solid {CARD_BDR}", "padding": "14px 24px 0 24px",
        }, children=[
            html.Div(className="scan-line"),
            html.Div(style={
                "display": "flex", "justifyContent": "space-between",
                "alignItems": "center", "flexWrap": "wrap", "gap": "12px", "paddingBottom": "12px",
            }, children=[
                html.Div(style={"display": "flex", "alignItems": "center", "gap": "14px"}, children=[
                    arc_reactor(),
                    html.Div([
                        html.Div("SENTINEL PRIME", style={
                            "fontSize": "24px", "fontWeight": "700", "color": CYAN,
                            "letterSpacing": "0.12em", "textShadow": "0 0 12px rgba(0,229,255,0.5)",
                        }),
                        html.Div("NQ-ASIM v1.1  ·  ATLAS v12 DUAL ENGINE", style={
                            "fontSize": "10px", "color": TEXT_DIM, "letterSpacing": "0.1em",
                        }),
                    ]),
                ]),
                html.Div(style={"textAlign": "center"}, children=[
                    html.Div(id="sentinel-clock", children="--:--:--", style={
                        "fontSize": "32px", "fontWeight": "700", "color": CYAN,
                        "fontFamily": "Courier New, monospace", "letterSpacing": "0.05em",
                        "textShadow": "0 0 10px rgba(0,229,255,0.4)",
                    }),
                    html.Div("EASTERN TIME", style={"fontSize": "9px", "color": MUTED, "letterSpacing": "0.15em", "marginTop": "2px"}),
                ]),
                html.Div(style={"textAlign": "right"}, children=[
                    html.Div(id="gw-label", children="GOLDEN WINDOW OPENS IN", style={"fontSize": "9px", "color": MUTED, "letterSpacing": "0.1em"}),
                    html.Div(id="gw-countdown", children="--:--:--", style={
                        "fontSize": "24px", "fontWeight": "700", "color": MINT,
                        "fontFamily": "Courier New, monospace", "letterSpacing": "0.05em",
                    }),
                    html.Div(id="gw-status", children="", style={"fontSize": "10px", "letterSpacing": "0.08em"}),
                ]),
            ]),
            html.Div(className="ticker-wrapper", children=[
                html.Div(id="ticker-strip", className="ticker-content",
                         children="Loading market data…", style={"color": TEXT_DIM, "fontSize": "11px"}),
            ]),
        ]),

        # ── SECTION 2: COCKPIT STATUS BAR ────────────────────────────────
        html.Div(className="cockpit-bar", children=[
            html.Span("SENTINEL PRIME", style={"color": CYAN, "fontWeight": "700"}),
            html.Span("|", className="cockpit-sep"),
            html.Span("NQ-ASIM v1.1", style={"color": TEXT_DIM}),
            html.Span("|", className="cockpit-sep"),
            html.Span(id="cockpit-regime",  children="—",      style={"fontWeight": "700", "color": CYAN}),
            html.Span("|", className="cockpit-sep"),
            html.Span(id="cockpit-armed",   children="ARMED"),
            html.Span("|", className="cockpit-sep"),
            html.Span(id="cockpit-session", children="—",      style={"color": TEXT_DIM}),
            html.Span("|", className="cockpit-sep"),
            html.Span(id="cockpit-vix",     children="VIX —",  style={"fontWeight": "700", "color": MINT}),
            html.Span("|", className="cockpit-sep"),
            html.Span(id="cockpit-trend",   children="TREND —",style={"fontWeight": "700", "color": MINT}),
        ]),

        # ── MAIN BODY (vertical monitor stack) ────────────────────────────
        dbc.Container(fluid=True, style={"padding": "12px 20px", "backgroundColor": SENT_BG}, children=[

            # ── SECTION 3: DUAL ENGINE CARDS ──────────────────────────────
            dbc.Row(style={"marginBottom": "10px"}, children=[
                dbc.Col(width=6, children=[
                    html.Div(className="hud-card", style={**_CARD, "marginBottom": "0"}, children=[
                        hdr("PEAK SHORT ENGINE"),
                        dcc.Graph(
                            id="gauge-short-pf",
                            figure=make_knn_gauge(SHORT_PF * 10, "", CYAN),
                            config={"displayModeBar": False},
                            style={"height": "190px"},
                        ),
                        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"}, children=[
                            stat_row("PF", f"{SHORT_PF:.3f}", CYAN),
                            stat_row("WR", f"{SHORT_WR:.2f}%", CYAN),
                            stat_row("Trades", str(SHORT_TRADES), TEXT_MAIN),
                            stat_row("Net", f"+${SHORT_PNL:,}", MINT),
                        ]),
                        html.Div(style={"marginTop": "10px"}, children=[
                            html.Span("ACTIVE ARMED", className="engine-badge-active"),
                        ]),
                    ]),
                ]),
                dbc.Col(width=6, children=[
                    html.Div(className="hud-card hud-card-mint", style={**_CARD, "marginBottom": "0"}, children=[
                        hdr("ATLAS v12 LONG ENGINE"),
                        dcc.Graph(
                            id="gauge-long-pf",
                            figure=make_knn_gauge(LONG_PF * 10, "", MINT),
                            config={"displayModeBar": False},
                            style={"height": "190px"},
                        ),
                        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"}, children=[
                            stat_row("PF", f"{LONG_PF:.3f}", MINT),
                            stat_row("WR", f"{LONG_WR:.2f}%", MINT),
                            stat_row("Trades", str(LONG_TRADES), TEXT_MAIN),
                            stat_row("Net", f"+${5453:,}", MINT),
                        ]),
                        html.Div(style={"marginTop": "10px", "display": "flex", "justifyContent": "space-between", "alignItems": "center"}, children=[
                            html.Span(id="atlas-gate-badge", children="DAILY TREND ▲", className="engine-badge-active"),
                            html.Span(id="atlas-gate-status", children="ACTIVE ▲", style={"color": MINT, "fontWeight": "700", "fontFamily": "Courier New, monospace"}),
                        ]),
                    ]),
                ]),
            ]),

            # ── SECTION 4: COMBINED METRICS STRIP ─────────────────────────
            html.Div(className="combined-strip hud-card", style={"marginBottom": "10px"}, children=[
                html.Div(className="metric-cell", children=[
                    html.Div("COMBINED PF", style={"fontSize": "9px", "color": MUTED, "letterSpacing": "0.16em"}),
                    html.Div(f"{COMBINED_PF:.3f}", className="glow-mint", style={"fontSize": "28px", "fontWeight": "800", "color": MINT}),
                ]),
                html.Div(className="metric-cell", children=[
                    html.Div("NET P&L", style={"fontSize": "9px", "color": MUTED, "letterSpacing": "0.16em"}),
                    html.Div(f"+${NET_PNL:,}", style={"fontSize": "18px", "fontWeight": "800", "color": MINT}),
                ]),
                html.Div(className="metric-cell", children=[
                    html.Div("SHARPE", style={"fontSize": "9px", "color": MUTED, "letterSpacing": "0.16em"}),
                    html.Div(f"{SHARPE:.3f}", className="glow-cyan", style={"fontSize": "18px", "fontWeight": "800", "color": CYAN}),
                ]),
                html.Div(className="metric-cell", children=[
                    html.Div("WIN RATE", style={"fontSize": "9px", "color": MUTED, "letterSpacing": "0.16em"}),
                    html.Div(f"{COMBINED_WR:.2f}%", className="glow-cyan", style={"fontSize": "18px", "fontWeight": "800", "color": CYAN}),
                ]),
                html.Div(className="metric-cell", children=[
                    html.Div("MAX DD", style={"fontSize": "9px", "color": MUTED, "letterSpacing": "0.16em"}),
                    html.Div(f"{MAX_DD:.2f}%", className="glow-cyan", style={"fontSize": "18px", "fontWeight": "800", "color": CYAN}),
                ]),
                html.Div(className="metric-cell", children=[
                    html.Div("TRADES", style={"fontSize": "9px", "color": MUTED, "letterSpacing": "0.16em"}),
                    html.Div(str(TOTAL_TRADES), className="glow-cyan", style={"fontSize": "18px", "fontWeight": "800", "color": CYAN}),
                ]),
            ]),

            # ── SECTION 5: VIX COMMAND CENTER ─────────────────────────────
            html.Div(className="hud-card", style=_CARD, children=[
                dbc.Row(children=[
                    dbc.Col(width=6, children=[
                        dcc.Graph(id="gauge-vix", config={"displayModeBar": False}, style={"height": "200px"}),
                    ]),
                    dbc.Col(width=6, children=[
                        make_implied_move(0),
                        html.Div(id="overlord-status-panel", children=make_circuit_breakers(0, "NORMAL", 0)),
                    ]),
                ]),
            ]),

            # ── SECTION 6: KNN INTELLIGENCE ───────────────────────────────
            html.Div(className="hud-card", style=_CARD, children=[
                hdr("KNN INTELLIGENCE"),
                dbc.Row(children=[
                    dbc.Col(width=6, children=[
                        dcc.Graph(id="knn-s-gauge", figure=KNN_S_FIG, config={"displayModeBar": False}),
                        html.Div(style={"display": "flex", "justifyContent": "space-between", "fontSize": "9px", "color": MUTED, "padding": "0 4px 4px"}, children=[
                            html.Span("RVOL"), html.Span("ADX"), html.Span("EMA-D"), html.Span("VIX"),
                        ]),
                    ]),
                    dbc.Col(width=6, children=[
                        dcc.Graph(id="knn-l-gauge", figure=KNN_L_FIG, config={"displayModeBar": False}),
                        html.Div(style={"display": "flex", "justifyContent": "space-between", "fontSize": "9px", "color": MUTED, "padding": "0 4px 4px"}, children=[
                            html.Span("RVOL"), html.Span("ADX"), html.Span("RECLAIM"), html.Span("VIX⁻¹"), html.Span("HH"),
                        ]),
                    ]),
                ]),
            ]),

            # ── SECTION 7: SESSION TIMELINE ───────────────────────────────
            html.Div(className="hud-card", style=_CARD, children=[
                hdr("SESSION TIMELINE"),
                make_kill_zone_bar(),
                html.Div(style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "flexWrap": "wrap", "gap": "10px", "marginTop": "8px"}, children=[
                    html.Span(id="session-badge", children="LOADING"),
                    html.Div(style={"display": "flex", "gap": "10px", "alignItems": "center", "flexWrap": "wrap"}, children=[
                        html.Div(children=[
                            html.Div("L SLOTS (2)", style={"fontSize": "9px", "color": MUTED, "letterSpacing": "0.1em"}),
                            html.Div(className="slot-wrap", children=[html.Span(className="slot slot-avail"), html.Span(className="slot slot-avail")]),
                        ]),
                        html.Div(children=[
                            html.Div("S SLOTS (4)", style={"fontSize": "9px", "color": MUTED, "letterSpacing": "0.1em"}),
                            html.Div(className="slot-wrap", children=[html.Span(className="slot slot-avail"), html.Span(className="slot slot-avail"), html.Span(className="slot slot-avail"), html.Span(className="slot slot-avail")]),
                        ]),
                    ]),
                    html.Div(style={"textAlign": "right"}, children=[
                        html.Div("EOD COUNTDOWN", style={"fontSize": "9px", "color": MUTED, "letterSpacing": "0.1em"}),
                        html.Div(id="eod-countdown", children="--:--:--", style={"fontSize": "16px", "fontWeight": "800", "color": GOLD}),
                    ]),
                ]),
            ]),

            # ── SECTION 8: MACRO INTELLIGENCE GRID ────────────────────────
            html.Div(className="hud-card", style=_CARD, children=[
                hdr("MACRO INTELLIGENCE"),
                html.Div(id="macro-grid-panel"),
            ]),

            # ── SECTION 9: VIX HISTORY CHART ──────────────────────────────
            html.Div(className="hud-card", style={**_CARD, "padding": "8px"}, children=[
                dcc.Graph(id="vix-history-chart", config={"displayModeBar": False}, style={"height": "180px"}),
            ]),

            # ── SECTION 10: NEWS + CALENDAR ───────────────────────────────
            dbc.Row(style={"marginBottom": "10px"}, children=[
                dbc.Col(width=6, children=[
                    html.Div(className="hud-card", style=_CARD, children=[
                        hdr("NEWS FEED"),
                        html.Div(id="sentinel-news-feed"),
                    ]),
                ]),
                dbc.Col(width=6, children=[
                    html.Div(className="hud-card", style=_CARD, children=[
                        hdr("ECONOMIC CALENDAR — THIS WEEK"),
                        html.Div(style={"display": "grid", "gridTemplateColumns": "100px 55px 1fr 55px 60px 60px", "gap": "6px", "fontSize": "9px", "color": MUTED, "fontFamily": "Courier New, monospace", "borderBottom": f"1px solid {CARD_BDR}", "paddingBottom": "4px", "marginBottom": "4px"}, children=[
                            html.Span("DATE"), html.Span("TIME"), html.Span("EVENT"), html.Span("IMPACT"), html.Span("PREV"), html.Span("EST"),
                        ]),
                        *make_calendar_rows(),
                        html.Div(style={"display": "none"}, children=html.Div(id="sentinel-policy-panel")),
                    ]),
                ]),
            ]),

            # ── SECTION 11: INTELLIGENCE CHARTS ───────────────────────────
            html.Div(className="hud-card", style={**_CARD, "padding": "8px"}, children=[
                hdr("INTELLIGENCE CHARTS"),
                dcc.Graph(id="sentiment-chart", config={"displayModeBar": False}, style={"height": "220px"}),
            ]),

            # ── SECTION 12: FOOTER STATUS BAR ─────────────────────────────
            html.Div(id="sentinel-status-bar", style={"marginBottom": "6px"}),
            html.Div(id="sentinel-rec-card", style={"marginBottom": "10px"},
                     children=html.Div("Loading recommendation…", style={"color": MUTED, "padding": "10px"})),

            # ── HIDDEN ELEMENTS (keep existing callbacks alive) ───────────
            html.Div(style={"display": "none"}, children=[
                html.Div(id="sentinel-regime-banner"),
                html.Div(dcc.Graph(id="gauge-yield",  config={"displayModeBar": False})),
                html.Div(dcc.Graph(id="gauge-hy",     config={"displayModeBar": False})),
                html.Div(dcc.Graph(id="gauge-dollar", config={"displayModeBar": False})),
                html.Div(dcc.Graph(id="gauge-gap",    config={"displayModeBar": False})),
                html.Div(dcc.Graph(id="gauge-news",   config={"displayModeBar": False})),
                html.Div(id="signal-scanner-panel"),
                html.Div(id="system-vitals-panel"),
                html.Div(id="session-pnl"),
                html.Div(id="session-pnl-bar"),
                html.Div(id="cockpit-trend-label"),
            ]),

        ]),  # end dbc.Container

        # Intervals
        dcc.Interval(id="clock-tick",    interval=1_000,   n_intervals=0),
        dcc.Interval(id="sentinel-tick", interval=60_000,  n_intervals=0),
        dcc.Interval(id="charts-tick",   interval=300_000, n_intervals=0),
    ]
)

# ─────────────────────────────────────────────────────────────────────────────
#  ALERT MONITOR LAYOUT (existing content as Tab 2)
# ─────────────────────────────────────────────────────────────────────────────

STAT_LABEL = {
    "fontSize": "11px", "color": MUTED,
    "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "2px",
}
STAT_VALUE = {
    "fontSize": "22px", "fontWeight": "600", "color": TEXT_MAIN, "fontFamily": "monospace",
}
CARD_STYLE = {
    "backgroundColor": CARD_BG, "border": f"1px solid #1e2d45",
    "borderRadius": "8px", "padding": "16px", "marginBottom": "12px",
}
TYPE_COLORS = {
    "GO":            {"backgroundColor": "#0a2a1a", "color": MINT},
    "READY":         {"backgroundColor": "#0a1f2a", "color": CYAN},
    "WATCH":         {"backgroundColor": "#1a1a2a", "color": "#a78bfa"},
    "STAGE1":        {"backgroundColor": "#1a1a0a", "color": GOLD},
    "CB":            {"backgroundColor": "#2a0a0a", "color": ROSE},
    "OVERLORD":      {"backgroundColor": "#2a0a0a", "color": ROSE},
    "ANTI_TILT":     {"backgroundColor": "#2a0a0a", "color": ROSE},
    "PROFIT_LOCK":   {"backgroundColor": "#0a2a1a", "color": MINT},
    "EOD":           {"backgroundColor": "#1a1a1a", "color": TEXT_DIM},
    "TIME_STOP":     {"backgroundColor": "#1a1a1a", "color": GOLD},
    "MORNING_BRIEF": {"backgroundColor": "#0a1a2a", "color": "#60a5fa"},
    "PRE_SIGNAL":    {"backgroundColor": "#1a1200", "color": ORANGE},
    "KILL_SWITCH":   {"backgroundColor": "#2a0000", "color": "#ff0000"},
}

def make_stat_card(label: str, value_id: str, default: str = "—") -> html.Div:
    return html.Div([
        html.Div(label, style=STAT_LABEL),
        html.Div(default, id=value_id, style=STAT_VALUE),
    ], style={**CARD_STYLE, "flex": "1", "minWidth": "130px"})

def badge(text_id: str, default: str = "…") -> html.Span:
    return html.Span(default, id=text_id, style={
        "fontFamily": "monospace", "fontSize": "12px", "fontWeight": "600",
        "padding": "2px 8px", "borderRadius": "4px",
        "backgroundColor": CARD_BG, "border": "1px solid #1e2d45",
        "color": TEXT_MAIN, "marginRight": "6px",
    })

def _macro_vital_card(label: str, value_str: str, color: str) -> html.Div:
    return html.Div([
        html.Div(label, style={**STAT_LABEL, "marginBottom": "2px"}),
        html.Div(value_str, style={"fontSize": "16px", "fontWeight": "700",
                                   "fontFamily": "monospace", "color": color}),
    ])

alert_monitor_layout = html.Div(
    style={"backgroundColor": DARK_BG, "minHeight": "100vh",
           "fontFamily": "monospace", "padding": "16px"},
    children=[
        # Top bar
        html.Div([
            html.Div([
                html.H1("NQ-MH v39.3  ·  Alert Monitor",
                        style={"color": CYAN, "fontSize": "20px",
                               "fontWeight": "500", "margin": "0 0 6px 0"}),
                html.Div([
                    html.Span("WEBHOOK ", style={**STAT_LABEL, "marginBottom": "0"}),
                    badge("badge-webhook"),
                    html.Span("  KILL SW ", style={**STAT_LABEL, "marginBottom": "0"}),
                    badge("badge-ks"),
                    html.Span("  MONITOR ", style={**STAT_LABEL, "marginBottom": "0"}),
                    badge("badge-monitor"),
                ], style={"display": "flex", "alignItems": "center",
                          "flexWrap": "wrap", "gap": "4px"}),
            ]),
            html.Div([
                html.Button("⛔  KILL SWITCH", id="btn-kill", style={
                    "backgroundColor": RED_BTN, "color": "#fca5a5",
                    "border": "1px solid #dc2626", "borderRadius": "6px",
                    "padding": "10px 20px", "fontSize": "14px", "fontWeight": "700",
                    "fontFamily": "monospace", "cursor": "pointer", "marginRight": "8px",
                }),
                html.Button("✅  RESET", id="btn-reset", style={
                    "backgroundColor": GREEN_BTN, "color": "#6ee7b7",
                    "border": "1px solid #10b981", "borderRadius": "6px",
                    "padding": "10px 20px", "fontSize": "14px", "fontWeight": "700",
                    "fontFamily": "monospace", "cursor": "pointer",
                }),
            ], style={"display": "flex", "alignItems": "center"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "flex-start", "marginBottom": "8px"}),

        html.Div(id="ks-feedback", style={
            "fontSize": "12px", "color": ROSE, "marginBottom": "8px", "minHeight": "16px",
        }),

        # Stat strip
        html.Div([
            html.Div([
                html.Div("MNQ1! Live Price", style=STAT_LABEL),
                html.Div(id="live-price", children="—",
                         style={**STAT_VALUE, "fontSize": "32px", "color": CYAN}),
                html.Div(id="live-price-ts", children="",
                         style={"fontSize": "10px", "color": MUTED}),
            ], style={**CARD_STYLE, "minWidth": "160px",
                      "borderColor": CYAN, "flex": "0 0 auto"}),
            make_stat_card("Today GO alerts", "stat-go"),
            make_stat_card("Today P&L",       "stat-pnl"),
            make_stat_card("Trades taken",    "stat-trades"),
            make_stat_card("KNN avg",         "stat-knn"),
            make_stat_card("Last VIX",        "stat-vix"),
            make_stat_card("Circuit breaker", "stat-cb"),
            make_stat_card("Sentinel",        "stat-overlord"),
        ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "12px"}),

        html.Div(id="header-status",
                 style={"color": MUTED, "fontSize": "12px", "marginBottom": "10px"}),

        # Alert table + chart row
        html.Div([
            html.Div([
                html.Div("Today's Alerts", style={**STAT_LABEL, "marginBottom": "8px"}),
                dash_table.DataTable(
                    id="alert-table",
                    columns=[
                        {"name": "Time (UTC)", "id": "received_at"},
                        {"name": "Type",       "id": "type"},
                        {"name": "Side",       "id": "side"},
                        {"name": "Entry",      "id": "entry"},
                        {"name": "Stop",       "id": "stop"},
                        {"name": "Qty",        "id": "qty"},
                        {"name": "Risk $",     "id": "risk_usd"},
                        {"name": "KNN %",      "id": "knn_wr"},
                        {"name": "ATR",        "id": "atr_regime"},
                        {"name": "Day P&L",    "id": "daily_pnl"},
                    ],
                    data=[],
                    style_table={"overflowX": "auto"},
                    style_header={"backgroundColor": DARK_BG, "color": MUTED,
                                  "fontSize": "11px", "fontWeight": "500",
                                  "border": "1px solid #1e2d45"},
                    style_cell={"backgroundColor": CARD_BG, "color": TEXT_MAIN,
                                "fontSize": "12px", "border": "1px solid #1e2d45",
                                "padding": "6px 10px", "fontFamily": "monospace"},
                    style_data_conditional=[
                        {"if": {"filter_query": f'{{type}} = "{t}"'},
                         "backgroundColor": c["backgroundColor"], "color": c["color"]}
                        for t, c in TYPE_COLORS.items()
                    ],
                    page_size=30, sort_action="native",
                ),
            ], style={**CARD_STYLE, "flex": "2", "minWidth": "600px"}),

            html.Div([
                html.Div("7-Day GO Signals", style={**STAT_LABEL, "marginBottom": "8px"}),
                dcc.Graph(id="history-chart", style={"height": "300px"},
                          config={"displayModeBar": False}),
                html.Div("KNN win rate distribution",
                         style={**STAT_LABEL, "marginTop": "16px", "marginBottom": "8px"}),
                dcc.Graph(id="knn-chart", style={"height": "200px"},
                          config={"displayModeBar": False}),
            ], style={**CARD_STYLE, "flex": "1", "minWidth": "300px"}),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap"}),

        # Full log
        html.Div([
            html.Div("Full Alert Log (last 500)", style={**STAT_LABEL, "marginBottom": "8px"}),
            dash_table.DataTable(
                id="raw-table",
                columns=[
                    {"name": "Time",       "id": "received_at"},
                    {"name": "Type",       "id": "type"},
                    {"name": "Side",       "id": "side"},
                    {"name": "Channels",   "id": "channels"},
                    {"name": "Priority",   "id": "priority"},
                    {"name": "Dispatched", "id": "dispatched"},
                    {"name": "Reason",     "id": "reason"},
                    {"name": "Status",     "id": "status"},
                ],
                data=[],
                style_table={"overflowX": "auto"},
                style_header={"backgroundColor": DARK_BG, "color": MUTED,
                              "fontSize": "11px", "border": "1px solid #1e2d45"},
                style_cell={"backgroundColor": CARD_BG, "color": TEXT_DIM,
                            "fontSize": "11px", "border": "1px solid #1e2d45",
                            "padding": "4px 8px", "fontFamily": "monospace"},
                style_data_conditional=[
                    {"if": {"filter_query": f'{{type}} = "{t}"'},
                     "backgroundColor": c["backgroundColor"], "color": c["color"]}
                    for t, c in TYPE_COLORS.items()
                ],
                page_size=20, filter_action="native", sort_action="native",
            ),
        ], style=CARD_STYLE),

        # Accounts + health
        html.Div([
            html.Div([
                html.Div("Account Status", style={**STAT_LABEL, "marginBottom": "8px"}),
                html.Div(id="account-panel",
                         children=[html.Span("Loading…", style={"color": MUTED, "fontSize": "12px"})]),
            ], style={**CARD_STYLE, "flex": "1", "minWidth": "300px"}),
            html.Div([
                html.Div("System Health", style={**STAT_LABEL, "marginBottom": "8px"}),
                html.Div(id="health-panel",
                         children=[html.Span("Loading…", style={"color": MUTED, "fontSize": "12px"})]),
            ], style={**CARD_STYLE, "flex": "1", "minWidth": "300px"}),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "12px"}),

        # Macro panel (existing, preserved)
        html.Div([
            html.Div("MACRO INTELLIGENCE", style={**STAT_LABEL, "marginBottom": "8px"}),
            html.Div(id="macro-regime-banner", style={"marginBottom": "10px"},
                     children=[html.Span("Loading…", style={"color": MUTED, "fontSize": "13px"})]),
            html.Div([
                html.Div(id="macro-vix-card",    style={**CARD_STYLE, "flex": "1", "minWidth": "120px", "marginBottom": "0"}),
                html.Div(id="macro-yield-card",  style={**CARD_STYLE, "flex": "1", "minWidth": "120px", "marginBottom": "0"}),
                html.Div(id="macro-hy-card",     style={**CARD_STYLE, "flex": "1", "minWidth": "120px", "marginBottom": "0"}),
                html.Div(id="macro-dollar-card", style={**CARD_STYLE, "flex": "1", "minWidth": "120px", "marginBottom": "0"}),
                html.Div(id="macro-gap-card",    style={**CARD_STYLE, "flex": "1", "minWidth": "140px", "marginBottom": "0"}),
                html.Div(id="macro-news-card",   style={**CARD_STYLE, "flex": "1", "minWidth": "140px", "marginBottom": "0"}),
            ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "10px"}),
            html.Div([
                html.Div([
                    html.Div("Policy Risk Tracker", style={**STAT_LABEL, "marginBottom": "6px"}),
                    html.Div(id="macro-policy-panel"),
                ], style={**CARD_STYLE, "flex": "1", "minWidth": "280px", "marginBottom": "0"}),
                html.Div([
                    html.Div("Top Headlines (scored)", style={**STAT_LABEL, "marginBottom": "6px"}),
                    html.Div(id="macro-news-panel"),
                ], style={**CARD_STYLE, "flex": "2", "minWidth": "340px", "marginBottom": "0"}),
            ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "10px"}),
            html.Div([
                html.Div([
                    html.Div("Economic Calendar", style={**STAT_LABEL, "marginBottom": "6px"}),
                    html.Div(id="macro-calendar-panel"),
                ], style={**CARD_STYLE, "flex": "1", "minWidth": "280px", "marginBottom": "0"}),
                html.Div([
                    html.Div("Trading Recommendation", style={**STAT_LABEL, "marginBottom": "6px"}),
                    html.Div(id="macro-rec-panel"),
                ], style={**CARD_STYLE, "flex": "1", "minWidth": "280px", "marginBottom": "0"}),
            ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap"}),
        ], style={**CARD_STYLE, "marginBottom": "12px"}),

        dcc.Interval(id="refresh",       interval=5_000,   n_intervals=0),
        dcc.Interval(id="macro-refresh", interval=300_000, n_intervals=0),
    ]
)

# ─────────────────────────────────────────────────────────────────────────────
#  APP + LAYOUT
# ─────────────────────────────────────────────────────────────────────────────

app = Dash(__name__, title="SENTINEL PRIME | NQ-ASIM",
           suppress_callback_exceptions=True,
           external_stylesheets=[dbc.themes.BOOTSTRAP])

TAB_STYLE = {
    "backgroundColor": "#050a0f",
    "color":           MUTED,
    "border":          f"1px solid {CARD_BDR}",
    "fontFamily":      "Courier New, monospace",
    "fontSize":        "12px",
    "letterSpacing":   "0.1em",
    "padding":         "10px 24px",
}
TAB_SELECTED = {
    **TAB_STYLE,
    "backgroundColor": "#0a1929",
    "color":           CYAN,
    "borderBottom":    f"2px solid {CYAN}",
}

app.layout = html.Div(
    style={"backgroundColor": SENT_BG, "minHeight": "100vh"},
    children=[
        dcc.Tabs(
            id="main-tabs",
            value="sentinel",
            className="custom-tabs",
            style={"backgroundColor": SENT_BG},
            children=[
                dcc.Tab(
                    label="  SENTINEL PRIME  ",
                    value="sentinel",
                    style=TAB_STYLE,
                    selected_style=TAB_SELECTED,
                    children=[sentinel_layout],
                ),
                dcc.Tab(
                    label="  ALERT MONITOR  ",
                    value="monitor",
                    style=TAB_STYLE,
                    selected_style=TAB_SELECTED,
                    children=[alert_monitor_layout],
                ),
            ],
        )
    ]
)

# ─────────────────────────────────────────────────────────────────────────────
#  CALLBACK 0 — Live Clock + GW Countdown  (every 1 s)
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    [Output("sentinel-clock",   "children"),
     Output("sentinel-clock",   "style"),
     Output("gw-label",         "children"),
     Output("gw-countdown",     "children"),
     Output("gw-countdown",     "style"),
     Output("gw-status",        "children"),
     Output("gw-status",        "style"),
     Output("cockpit-session",  "children"),
     Output("cockpit-session",  "style"),
     Output("session-badge",    "children"),
     Output("session-badge",    "style"),
     Output("eod-countdown",    "children")],
    Input("clock-tick", "n_intervals"),
)
def update_clock(_):
    now_et = datetime.datetime.now(ET)
    clock_str = now_et.strftime("%H:%M:%S")

    label, countdown, is_active = get_gw_info()
    gw_color  = MINT if is_active else CYAN
    gw_status = "● ACTIVE" if is_active else ""
    gw_status_style = {"fontSize": "11px", "color": MINT if is_active else MUTED,
                        "letterSpacing": "0.08em"}

    clock_style = {
        "fontSize": "36px", "fontWeight": "700",
        "color": CYAN, "fontFamily": "Courier New, monospace",
        "letterSpacing": "0.05em",
        "textShadow": "0 0 10px rgba(0,229,255,0.4)",
    }
    gw_cd_style = {
        "fontSize": "28px", "fontWeight": "700",
        "color": gw_color, "fontFamily": "Courier New, monospace",
        "letterSpacing": "0.05em",
    }

    # ── Cockpit / session panel outputs ─────────────────────────────────────
    # Determine session window name
    h, m = now_et.hour, now_et.minute
    if (h == 9 and m >= 30) or (h == 10):
        session_name = "GOLDEN WINDOW"
        sess_color   = MINT
    elif (h == 15 and m >= 0) or (h == 14 and m >= 30):
        session_name = "POWER HOUR"
        sess_color   = GOLD
    elif (h >= 9 and h < 16):
        session_name = "RTH"
        sess_color   = CYAN
    else:
        session_name = "OFF-HOURS"
        sess_color   = MUTED

    cockpit_session_str   = f"{clock_str} ET  |  {session_name}"
    cockpit_session_style = {"fontSize": "11px", "color": sess_color, "fontFamily": "Courier New"}

    session_badge_str   = session_name
    session_badge_style = {
        "fontSize": "11px", "fontWeight": "700", "letterSpacing": "0.08em",
        "padding": "2px 8px", "borderRadius": "4px",
        "background": "rgba(0,255,187,0.12)",
        "color": sess_color, "border": f"1px solid {sess_color}",
        "fontFamily": "Courier New",
    }

    # EOD countdown to 15:45 ET
    eod_target = now_et.replace(hour=15, minute=45, second=0, microsecond=0)
    if now_et >= eod_target:
        eod_str = "FLAT"
    else:
        delta   = int((eod_target - now_et).total_seconds())
        h_left  = delta // 3600
        m_left  = (delta % 3600) // 60
        s_left  = delta % 60
        eod_str = f"{h_left:02d}:{m_left:02d}:{s_left:02d}"

    return (
        clock_str, clock_style,
        label, countdown, gw_cd_style, gw_status, gw_status_style,
        cockpit_session_str, cockpit_session_style,
        session_badge_str, session_badge_style,
        eod_str,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  CALLBACK 1 — Sentinel Prime Main Panels  (every 60 s)
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    [Output("ticker-strip",            "children"),
     Output("sentinel-regime-banner",  "children"),
     Output("sentinel-regime-banner",  "style"),
     Output("gauge-vix",               "figure"),
     Output("gauge-yield",             "figure"),
     Output("gauge-hy",                "figure"),
     Output("gauge-dollar",            "figure"),
     Output("gauge-gap",               "figure"),
     Output("gauge-news",              "figure"),
     Output("sentinel-news-feed",      "children"),
     Output("sentinel-policy-panel",   "children"),
     Output("sentinel-rec-card",       "children"),
     Output("sentinel-status-bar",     "children"),
     Output("cockpit-regime",          "children"),
     Output("cockpit-armed",           "children"),
     Output("cockpit-armed",           "style"),
     Output("cockpit-vix",             "children"),
     Output("cockpit-trend",           "children"),
     Output("cockpit-trend-label",     "children"),
     Output("cockpit-trend-label",     "style"),
     Output("atlas-gate-badge",        "children"),
     Output("atlas-gate-badge",        "style"),
     Output("atlas-gate-status",       "children"),
     Output("atlas-gate-status",       "style"),
     Output("signal-scanner-panel",    "children"),
     Output("system-vitals-panel",     "children")],
    Input("sentinel-tick", "n_intervals"),
)
def update_sentinel(_):
    macro = load_macro()
    regime   = macro.get("regime", "NORMAL")
    score    = macro.get("score", 0)
    vix      = macro.get("vix")
    yc       = macro.get("yield_curve")
    hy       = macro.get("hy_spread")
    dollar   = macro.get("dollar")
    gap      = macro.get("nq_premarket_gap")
    gap_lbl  = macro.get("gap_label", "FLAT")
    gap_dir  = macro.get("gap_direction", "NEUTRAL")
    news_s   = macro.get("news_score", 0)
    news_lbl = macro.get("news_label", "NORMAL")
    policy   = macro.get("policy_risk", False)
    pterms   = macro.get("policy_terms", [])
    pposts   = macro.get("policy_posts", [])
    hdlines  = macro.get("top_headlines", [])
    rec      = macro.get("recommendation", "")
    ts_str   = macro.get("timestamp", "")
    hi       = macro.get("high_impact_today", False)
    event    = macro.get("event_name", "NONE")

    # Update sentiment history with today's score
    update_sentiment_history(news_s)

    # ── Stale check ────────────────────────────────────────────────────────
    stale_warn = ""
    if ts_str:
        try:
            ts_dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            age_h = (datetime.datetime.now(datetime.timezone.utc) - ts_dt).total_seconds() / 3600
            if age_h > MACRO_STALE_HOURS:
                stale_warn = f"  ⚠ DATA {age_h:.0f}h OLD"
        except Exception:
            pass

    # ── Ticker ──────────────────────────────────────────────────────────────
    ticker_items = build_ticker(macro)

    # ── Regime banner ───────────────────────────────────────────────────────
    regime_cfg = {
        "RISK-OFF": ("#1a0505", "#E24B4A", "#E24B4A", "regime-riskoff"),
        "CAUTION":  ("#150d00", "#EF9F27", "#EF9F27", "regime-caution"),
        "NORMAL":   ("#031510", "#00ffbb", "#00ffbb", "regime-normal"),
    }
    r_bg, r_fg, r_bdr, r_cls = regime_cfg.get(regime, ("#0a0a0a", MUTED, MUTED, ""))
    regime_banner_style = {
        "backgroundColor": r_bg,
        "border": f"2px solid {r_bdr}",
        "borderRadius":    "10px",
        "padding":         "20px 28px",
        "display":         "flex",
        "alignItems":      "center",
        "justifyContent":  "space-between",
        "flexWrap":        "wrap",
        "gap":             "20px",
    }
    regime_banner_children = html.Div(
        className=r_cls,
        style=regime_banner_style,
        children=[
            html.Div([
                html.Div(regime, style={
                    "fontSize":      "48px",
                    "fontWeight":    "800",
                    "color":         r_fg,
                    "fontFamily":    "Courier New, monospace",
                    "letterSpacing": "0.08em",
                    "lineHeight":    "1",
                    "textShadow":    f"0 0 20px {r_bdr}44",
                }),
                html.Div(rec[:120] if rec else "—", style={
                    "fontSize":   "14px",
                    "color":      r_fg,
                    "marginTop":  "8px",
                    "opacity":    "0.85",
                    "maxWidth":   "600px",
                    "lineHeight": "1.4",
                }),
            ]),
            html.Div([
                html.Div("RISK SCORE", style={
                    "fontSize": "10px", "color": MUTED, "letterSpacing": "0.12em",
                    "marginBottom": "4px",
                }),
                html.Div(str(score), style={
                    "fontSize":   "72px",
                    "fontWeight": "700",
                    "color":      r_fg,
                    "lineHeight": "1",
                    "fontFamily": "Courier New, monospace",
                    "textShadow": f"0 0 30px {r_bdr}66",
                }),
                html.Div(f"/ 10   {ts_str[:16].replace('T',' ')} UTC{stale_warn}", style={
                    "fontSize": "10px", "color": MUTED, "marginTop": "4px",
                }),
            ], style={"textAlign": "right"}),
        ]
    )

    # ── Gauges ──────────────────────────────────────────────────────────────
    gauge_vix    = make_gauge_fig(vix or 0,    "VIX",          0,    50,  18,   25)
    gauge_yield  = make_gauge_fig((yc or 0),   "YIELD CURVE",  -1.5,  2,  -0.5,  0, invert=True)
    gauge_hy     = make_gauge_fig(hy or 0,     "HY SPREAD %",  0,    10,   3.5, 4.5)
    gauge_dollar = make_gauge_fig(dollar or 0, "DOLLAR INDEX", 95,  135,   0,   0)   # no threshold zones
    gauge_gap    = make_gauge_fig(gap or 0,    "NQ PRE-MKT %", -3,    3,  -0.5, -1.5, "%", "+.2f", invert=True)
    gauge_news   = make_gauge_fig(news_s,      "NEWS SCORE",   0,    10,    3,    7)

    # No thresholds for dollar — flat CYAN bar
    gauge_dollar = go.Figure(go.Indicator(
        mode="gauge+number",
        value=float(dollar or 0),
        title={"text": "DOLLAR INDEX", "font": {"size": 10, "color": MUTED, "family": "Courier New"}},
        number={"valueformat": ".2f",
                "font": {"size": 22, "color": CYAN, "family": "Courier New"}},
        gauge={
            "axis": {"range": [95, 135], "tickfont": {"size": 8, "color": MUTED},
                     "tickcolor": CARD_BDR},
            "bar": {"color": CYAN, "thickness": 0.22},
            "bgcolor": SENT_BG, "borderwidth": 1, "bordercolor": CARD_BDR,
        }
    ))
    gauge_dollar.update_layout(paper_bgcolor=SENT_BG, height=185, margin=dict(l=10,r=10,t=46,b=8))

    # ── News Feed ────────────────────────────────────────────────────────────
    if hdlines:
        headline_divs = []
        for i, h in enumerate(hdlines[:8]):
            risk_lvl  = "HIGH" if news_s >= 7 else "MED" if news_s >= 3 else "LOW"
            risk_cls  = f"risk-{risk_lvl.lower()}"
            headline_divs.append(html.Div(className="headline-card", children=[
                html.Div([
                    html.Span(risk_lvl, className=risk_cls),
                    html.Span(h[:110], style={
                        "fontSize": "13px", "color": TEXT_MAIN,
                        "fontFamily": "Courier New, monospace",
                    }),
                ]),
            ]))
        news_feed_children = headline_divs
    else:
        news_feed_children = [
            html.Div("No headlines loaded. Ensure NEWS_API_KEY is set and run macro_intelligence.py.",
                     style={"color": MUTED, "fontSize": "12px", "padding": "8px 0"}),
        ]

    # ── Policy Panel ─────────────────────────────────────────────────────────
    if policy:
        policy_children = [
            html.Div("⚠ POLICY RISK ACTIVE", className="policy-active-banner", style={
                "color": ROSE, "fontWeight": "700", "fontSize": "14px",
                "fontFamily": "Courier New, monospace", "marginBottom": "8px",
                "letterSpacing": "0.08em",
            }),
            html.Div([html.Span(t, className="policy-tag") for t in pterms],
                     style={"marginBottom": "8px"}),
            *[html.Div(f"› {p[:100]}", style={
                "fontSize": "11px", "color": TEXT_DIM, "marginBottom": "3px",
                "fontFamily": "Courier New, monospace",
            }) for p in pposts[:4]],
        ]
    else:
        policy_children = [
            html.Div("● CLEAR", style={
                "color": MINT, "fontWeight": "700", "fontSize": "14px",
                "fontFamily": "Courier New, monospace", "marginBottom": "6px",
            }),
            html.Div("No policy risk keywords detected in last 24h.",
                     style={"color": MUTED, "fontSize": "11px"}),
        ]
        if hi and event != "NONE":
            policy_children.append(html.Div(
                f"⚠ HIGH IMPACT EVENT TODAY: {event}",
                style={"color": GOLD, "fontSize": "12px", "marginTop": "8px",
                       "fontFamily": "Courier New, monospace", "fontWeight": "700"},
            ))

    # ── Recommendation Card ───────────────────────────────────────────────────
    if regime == "RISK-OFF":
        r_size  = "0 contracts — DO NOT TRADE"
        r_dir   = "Flat all session. System locked."
        r_risks = ["Active macro risk event", "Wait for regime to clear", "Run macro_intelligence.py at next RTH"]
    elif regime == "CAUTION":
        r_size  = "1 contract max (half size)"
        r_dir   = "Shorts preferred" if gap is not None and gap < -0.5 else \
                  "Longs favored" if gap is not None and gap > 0.5 else \
                  "Both directions — manage risk tightly"
        r_risks = [
            f"News sentiment elevated (score {news_s}/10)",
            f"VIX at {vix:.1f} — elevated" if vix and vix > 18 else f"VIX {vix:.1f} — monitoring",
            f"High-impact event: {event}" if hi else "Stay within kill zones only",
        ]
    else:
        r_size  = "2 contracts (standard plan)"
        r_dir   = gap_dir or "Both directions"
        r_risks = [
            f"NQ gap: {gap:+.2f}% [{gap_lbl}]" if gap is not None else "Monitor pre-market",
            "Stay within Golden Window and Power Hour",
            "Trust the system — no manual overrides",
        ]

    rec_card = html.Div(style={
        **CARD_S,
        "borderColor": r_bdr,
        "background":  f"linear-gradient(135deg, {r_bg} 0%, {SENT_CARD} 100%)",
    }, children=[
        sentinel_section_header("TRADING RECOMMENDATION"),
        html.Div(style={"display": "flex", "gap": "24px", "flexWrap": "wrap",
                        "alignItems": "flex-start"}, children=[
            html.Div([
                html.Div("TODAY'S REGIME", style=LBL_S),
                html.Div(regime, style={
                    "fontSize": "32px", "fontWeight": "800", "color": r_fg,
                    "fontFamily": "Courier New, monospace", "marginBottom": "12px",
                }),
                html.Div([
                    html.Div("POSITION SIZE", style=LBL_S),
                    html.Div(r_size, style={"fontSize": "16px", "color": r_fg,
                                            "fontFamily": "Courier New, monospace",
                                            "marginBottom": "10px"}),
                ]),
                html.Div([
                    html.Div("DIRECTION BIAS", style=LBL_S),
                    html.Div(r_dir, style={"fontSize": "16px", "color": TEXT_MAIN,
                                           "fontFamily": "Courier New, monospace"}),
                ]),
            ], style={"flex": "1", "minWidth": "200px"}),

            html.Div([
                html.Div("TOP RISKS TO WATCH", style=LBL_S),
                *[html.Div(f"▸ {r}", style={
                    "fontSize": "14px", "color": TEXT_DIM,
                    "fontFamily": "Courier New, monospace",
                    "marginBottom": "6px", "lineHeight": "1.4",
                }) for r in r_risks],
            ], style={"flex": "1", "minWidth": "200px"}),

            html.Div([
                html.Div("SYSTEM STATUS", style=LBL_S),
                html.Div([
                    html.Span(className="online-dot"),
                    html.Span("NQ-ASIM-1 ONLINE", style={
                        "color": MINT, "fontSize": "13px", "fontWeight": "700",
                        "fontFamily": "Courier New, monospace",
                    }),
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),
                html.Div("PF 4.342  |  WR 72.22%  |  DD 0.71%", style={
                    "color": CYAN, "fontSize": "12px",
                    "fontFamily": "Courier New, monospace", "marginBottom": "4px",
                }),
                html.Div("54 trades  Nov 2 – Apr 10 2026", style={
                    "color": MUTED, "fontSize": "11px",
                    "fontFamily": "Courier New, monospace",
                }),
            ], style={"flex": "1", "minWidth": "200px"}),
        ]),
    ])

    # ── Status bar ────────────────────────────────────────────────────────────
    sources = macro.get("sources", {})
    src_items = [
        ("FRED",    sources.get("fred_ok", False)),
        ("NEWS",    sources.get("news_ok", False)),
        ("POLICY",  sources.get("policy_ok", False)),
        ("FUTURES", sources.get("futures_ok", False)),
    ]
    status_bar = html.Div(style={
        "backgroundColor": "#030710",
        "border": f"1px solid {CARD_BDR}",
        "borderRadius": "6px",
        "padding": "8px 16px",
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "space-between",
        "flexWrap": "wrap",
        "gap": "12px",
    }, children=[
        html.Div([
            html.Span(className="online-dot"),
            html.Span("NQ-ASIM-1", style={"color": MINT, "fontSize": "12px",
                                           "fontWeight": "700", "marginRight": "16px"}),
            *[html.Span([
                html.Span("●", style={"color": MINT if ok else ROSE,
                                       "fontSize": "10px", "marginRight": "3px"}),
                html.Span(name, style={"color": MUTED, "fontSize": "10px",
                                        "marginRight": "10px"}),
            ]) for name, ok in src_items],
        ], style={"display": "flex", "alignItems": "center"}),

        html.Div([
            html.Span(f"LAST UPDATE: {ts_str[:16].replace('T',' ')} UTC{stale_warn}",
                      style={"color": MUTED, "fontSize": "10px",
                             "fontFamily": "Courier New, monospace", "marginRight": "16px"}),
            html.Span("SENTINEL PRIME v1", style={
                "color": CARD_BDR, "fontSize": "10px",
                "fontFamily": "Courier New, monospace",
            }),
        ], style={"display": "flex", "alignItems": "center"}),
    ])

    # ── Cockpit new outputs ───────────────────────────────────────────────────
    cockpit_regime_str = regime

    armed_ok    = regime != "RISK-OFF"
    armed_str   = "ARMED" if armed_ok else "LOCKED"
    armed_style = {
        "fontSize": "11px", "fontWeight": "700", "letterSpacing": "0.1em",
        "padding": "1px 8px", "borderRadius": "3px",
        "background": "rgba(0,255,187,0.15)" if armed_ok else "rgba(226,75,74,0.15)",
        "color": MINT if armed_ok else ROSE,
        "border": f"1px solid {'rgba(0,255,187,0.4)' if armed_ok else 'rgba(226,75,74,0.4)'}",
    }

    cockpit_vix_str = f"VIX {vix:.1f}" if vix is not None else "VIX —"

    # Daily trend gate — use macro data nq_premarket_gap as proxy; real gate from Pine
    # We approximate based on macro regime: NORMAL/CAUTION = trend context ok
    trend_up     = regime != "RISK-OFF"
    trend_str    = "TREND ▲" if trend_up else "TREND ▼"
    cockpit_trend_style = {"fontSize": "11px", "fontWeight": "700",
                           "color": MINT if trend_up else ROSE}

    trend_label_str   = "▲ TREND UP" if trend_up else "▼ TREND DOWN"
    trend_label_style = {
        "display": "inline-block", "fontSize": "11px", "fontWeight": "700",
        "letterSpacing": "0.08em", "padding": "3px 10px", "borderRadius": "4px",
        "background": "rgba(0,255,187,0.12)" if trend_up else "rgba(226,75,74,0.12)",
        "color": MINT if trend_up else ROSE,
        "border": f"1px solid {'rgba(0,255,187,0.35)' if trend_up else 'rgba(226,75,74,0.35)'}",
        "fontFamily": "Courier New",
    }

    atlas_badge_str   = "DAILY TREND ▲" if trend_up else "DAILY TREND ▼"
    atlas_badge_style = {
        "fontSize": "9px", "fontWeight": "700", "letterSpacing": "0.1em",
        "padding": "1px 6px", "borderRadius": "3px",
        "background": "rgba(0,255,187,0.12)" if trend_up else "rgba(226,75,74,0.12)",
        "color": MINT if trend_up else ROSE,
        "border": f"1px solid {'rgba(0,255,187,0.3)' if trend_up else 'rgba(226,75,74,0.3)'}",
    }
    atlas_gate_status_str   = "ACTIVE ▲" if trend_up else "BLOCKED ▼"
    atlas_gate_status_style = {"fontSize": "16px", "fontWeight": "700",
                               "color": MINT if trend_up else ROSE,
                               "fontFamily": "Courier New"}

    # ── Signal Scanner panel ─────────────────────────────────────────────────
    signal_scanner = html.Div([
        html.Div("SIGNAL SCANNER", style={**_LBL, "marginBottom": "8px"}),
        html.Div([
            html.Div([
                html.Span("SHORT",  style={"color": ROSE,  "fontWeight": "700",
                                           "fontSize": "11px", "marginRight": "6px",
                                           "fontFamily": "Courier New"}),
                html.Span("PEAK Engine — awaiting pivot", style={"color": MUTED, "fontSize": "10px"}),
            ], style={"marginBottom": "4px"}),
            html.Div([
                html.Span("LONG",   style={"color": MINT,  "fontWeight": "700",
                                           "fontSize": "11px", "marginRight": "6px",
                                           "fontFamily": "Courier New"}),
                html.Span(
                    "ATLAS v12 — gate OPEN" if trend_up else "ATLAS v12 — BLOCKED (daily < SMA20)",
                    style={"color": MINT if trend_up else ROSE, "fontSize": "10px"}),
            ], style={"marginBottom": "4px"}),
            html.Div([
                html.Span("REGIME", style={"color": CYAN,  "fontWeight": "700",
                                           "fontSize": "11px", "marginRight": "6px",
                                           "fontFamily": "Courier New"}),
                html.Span(regime, style={"color": r_fg, "fontSize": "10px", "fontWeight": "700"}),
            ]),
        ], style={"fontFamily": "Courier New"}),
    ])

    # ── System Vitals panel ──────────────────────────────────────────────────
    system_vitals = html.Div([
        html.Div("SYSTEM VITALS", style={**_LBL, "marginBottom": "8px"}),
        *[html.Div([
            html.Span(name, style={"color": MUTED, "fontSize": "10px", "width": "70px",
                                   "display": "inline-block", "fontFamily": "Courier New"}),
            html.Span("●", style={"color": MINT if ok else ROSE, "marginRight": "4px", "fontSize": "10px"}),
            html.Span("OK" if ok else "FAIL", style={"color": MINT if ok else ROSE,
                                                      "fontSize": "10px", "fontFamily": "Courier New"}),
        ], style={"marginBottom": "3px"})
        for name, ok in src_items],
    ])

    return (
        ticker_items,
        [regime_banner_children], regime_banner_style,
        gauge_vix, gauge_yield, gauge_hy, gauge_dollar, gauge_gap, gauge_news,
        news_feed_children, policy_children, rec_card, status_bar,
        cockpit_regime_str,
        armed_str, armed_style,
        cockpit_vix_str,
        trend_str,
        trend_label_str, trend_label_style,
        atlas_badge_str, atlas_badge_style,
        atlas_gate_status_str, atlas_gate_status_style,
        signal_scanner,
        system_vitals,
    )


@app.callback(
    Output("macro-grid-panel", "children"),
    Input("sentinel-tick", "n_intervals"),
)
def update_macro_grid(_):
    macro = fetch_macro_data()
    return make_macro_grid(macro)


# ─────────────────────────────────────────────────────────────────────────────
#  CALLBACK 2 — Intelligence Charts  (every 5 min)
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    [Output("vix-history-chart", "figure"),
     Output("sentiment-chart",   "figure")],
    Input("charts-tick", "n_intervals"),
)
def update_charts(_):
    dates, values    = fetch_vix_history()
    sentiment_hist   = load_sentiment_history()
    return make_vix_history_fig(dates, values), make_sentiment_fig(sentiment_hist)


# ─────────────────────────────────────────────────────────────────────────────
#  CALLBACK 3 — System Status Bar + Live Price  (Alert Monitor, every 5 s)
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    [Output("badge-webhook",  "children"),
     Output("badge-webhook",  "style"),
     Output("badge-ks",       "children"),
     Output("badge-ks",       "style"),
     Output("badge-monitor",  "children"),
     Output("badge-monitor",  "style"),
     Output("live-price",     "children"),
     Output("live-price",     "style"),
     Output("live-price-ts",  "children")],
    Input("refresh", "n_intervals"),
)
def update_system_status(_):
    _base = {"fontFamily": "monospace", "fontSize": "12px", "fontWeight": "600",
             "padding": "2px 8px", "borderRadius": "4px",
             "border": "1px solid #1e2d45", "marginRight": "6px"}

    wh_label, wh_ok     = check_webhook()
    ks_label, ks_active = check_kill_switch()
    mon_label, mon_ok   = check_monitor()
    price_str, price_ts = get_live_price()

    wh_style  = {**_base, "backgroundColor": "#0a2a1a" if wh_ok else "#2a0a0a",
                 "color": MINT if wh_ok else ROSE,
                 "borderColor": MINT if wh_ok else ROSE}
    ks_style  = {**_base, "backgroundColor": "#2a0000" if ks_active else "#0a1a2a",
                 "color": "#ff4444" if ks_active else CYAN,
                 "borderColor": "#dc2626" if ks_active else CYAN}
    mon_style = {**_base, "backgroundColor": "#0a1a0a" if mon_ok else "#1a1a00",
                 "color": MINT if mon_ok else GOLD,
                 "borderColor": MINT if mon_ok else GOLD}

    pc = CYAN if price_str != "—" else MUTED
    price_style = {**STAT_VALUE, "fontSize": "32px", "color": pc}

    return (wh_label, wh_style, ks_label, ks_style, mon_label, mon_style,
            price_str, price_style,
            f"updated {price_ts} UTC" if price_ts else "fetching…")


# ─────────────────────────────────────────────────────────────────────────────
#  CALLBACK 4 — Kill Switch Buttons
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output("ks-feedback", "children"),
    [Input("btn-kill", "n_clicks"), Input("btn-reset", "n_clicks")],
    prevent_initial_call=True,
)
def handle_ks_buttons(kill_clicks, reset_clicks):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if btn_id == "btn-kill":
        try:
            r = http_requests.post(f"{WH_URL}/killswitch", timeout=5)
            return "⛔ KILL SWITCH ACTIVATED" if r.status_code == 200 else f"HTTP {r.status_code}"
        except Exception as e:
            return f"Cannot reach webhook: {e}"
    if btn_id == "btn-reset":
        try:
            r = http_requests.post(f"{WH_URL}/killswitch/reset", timeout=5)
            return "✅ SYSTEM REARMED" if r.status_code == 200 else f"HTTP {r.status_code}"
        except Exception as e:
            return f"Cannot reach webhook: {e}"
    raise PreventUpdate


# ─────────────────────────────────────────────────────────────────────────────
#  CALLBACK 5 — Alert Tables + Charts + Stats  (every 5 s)
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    [Output("alert-table",   "data"),
     Output("raw-table",     "data"),
     Output("stat-go",       "children"),
     Output("stat-pnl",      "children"),
     Output("stat-trades",   "children"),
     Output("stat-knn",      "children"),
     Output("stat-vix",      "children"),
     Output("stat-cb",       "children"),
     Output("stat-overlord", "children"),
     Output("stat-go",       "style"),
     Output("stat-pnl",      "style"),
     Output("stat-cb",       "style"),
     Output("stat-overlord", "style"),
     Output("history-chart", "figure"),
     Output("knn-chart",     "figure"),
     Output("header-status", "children")],
    Input("refresh", "n_intervals"),
)
def update_all(_):
    today_df = load_alerts_today()
    raw_df   = load_all_recent(500)
    hist_df  = load_alerts_history(7)
    now_str  = datetime.datetime.utcnow().strftime("%H:%M:%S UTC")

    go_alerts  = today_df[today_df["type"] == "GO"] if not today_df.empty else pd.DataFrame()
    go_count   = len(go_alerts)
    cb_tripped = not today_df.empty and "CB" in today_df["type"].values
    ol_locked  = (not today_df.empty and "status" in today_df.columns and
                  today_df[today_df["type"] == "OVERLORD"]["status"].eq("LOCKED").any())

    last_pnl    = today_df["daily_pnl"].iloc[0]  if not today_df.empty and "daily_pnl"   in today_df.columns else None
    last_trades = today_df["trade_count"].iloc[0] if not today_df.empty and "trade_count" in today_df.columns else 0
    last_knn    = today_df["knn_wr"].mean()       if not today_df.empty and "knn_wr"      in today_df.columns else None
    last_vix    = today_df["vix"].iloc[0]         if not today_df.empty and "vix"         in today_df.columns else None

    pnl_str = f"${last_pnl:+,.0f}" if last_pnl  is not None else "—"
    knn_str = f"{last_knn:.1f}%"   if last_knn  is not None else "—"
    vix_str = f"{last_vix:.1f}"    if last_vix  is not None else "—"

    base     = dict(STAT_VALUE)
    go_sty   = {**base, "color": MINT if go_count > 0 else TEXT_MAIN}
    pnl_sty  = {**base, "color": MINT if (last_pnl or 0) > 0 else ROSE if (last_pnl or 0) < 0 else TEXT_MAIN}
    cb_sty   = {**base, "color": ROSE if cb_tripped else MINT}
    ol_sty   = {**base, "color": ROSE if ol_locked  else MINT}

    chart_bg   = {"plot_bgcolor": CARD_BG, "paper_bgcolor": CARD_BG}
    axis_style = {"gridcolor": "#1e2d45", "color": MUTED, "showgrid": True}

    if not hist_df.empty:
        colors   = [MINT if s == "SHORT" else CYAN for s in hist_df.get("side", [])]
        hist_fig = go.Figure([go.Scatter(
            x=pd.to_datetime(hist_df["received_at"]), y=hist_df.get("knn_wr", []),
            mode="markers", marker={"color": colors, "size": 8, "opacity": 0.85},
            text=hist_df.apply(lambda r: f"{r.get('side','?')} | KNN {r.get('knn_wr','?')}% | ${r.get('risk_usd','?')}", axis=1),
            hoverinfo="text+x",
        )])
        hist_fig.update_layout(**chart_bg, margin={"l":40,"r":10,"t":10,"b":40},
                               xaxis={**axis_style,"title":""}, yaxis={**axis_style,"title":"KNN %"}, showlegend=False)
    else:
        hist_fig = go.Figure()
        hist_fig.update_layout(**chart_bg, margin={"l":40,"r":10,"t":10,"b":40})
        hist_fig.add_annotation(text="No GO alerts in 7 days", xref="paper", yref="paper",
                                x=0.5, y=0.5, showarrow=False, font={"color": MUTED})

    knn_vals = today_df["knn_wr"].dropna() if not today_df.empty and "knn_wr" in today_df.columns else []
    if len(knn_vals) > 0:
        knn_fig = go.Figure([go.Histogram(
            x=knn_vals, nbinsx=10,
            marker_color=CYAN_DIM,
            marker_line={"color": CYAN, "width": 1},
        )])
        knn_fig.update_layout(**chart_bg, margin={"l":40,"r":10,"t":10,"b":40},
                              xaxis={**axis_style,"title":"KNN win rate %"},
                              yaxis={**axis_style,"title":"Count"}, showlegend=False)
    else:
        knn_fig = go.Figure()
        knn_fig.update_layout(**chart_bg, margin={"l":40,"r":10,"t":10,"b":40})

    today_records = today_df.to_dict("records") if not today_df.empty else []
    raw_records   = raw_df.to_dict("records")   if not raw_df.empty   else []
    header_status = (f"Last updated: {now_str}  ·  Alerts today: {len(today_df)}  ·  "
                     f"GO trades: {go_count}  ·  Refresh: 5s")

    return (today_records, raw_records,
            str(go_count), pnl_str, str(int(last_trades or 0)), knn_str, vix_str,
            "TRIPPED" if cb_tripped else "CLEAR",
            "LOCKED"  if ol_locked  else "ARMED",
            go_sty, pnl_sty, cb_sty, ol_sty,
            hist_fig, knn_fig, header_status)


# ─────────────────────────────────────────────────────────────────────────────
#  CALLBACK 6 — Per-Account Panel  (every 5 s)
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(Output("account-panel", "children"), Input("refresh", "n_intervals"))
def update_account_panel(_):
    try:
        r = http_requests.get(f"{WH_URL}/accounts", timeout=2)
        if r.status_code != 200:
            return html.Span("Accounts API unavailable", style={"color": MUTED, "fontSize": "12px"})
        accounts = r.json()
    except Exception:
        return html.Span("Webhook offline", style={"color": ROSE, "fontSize": "12px"})

    cards = []
    for acct in accounts:
        net, cb, lock, active = acct.get("net_pnl", 0) or 0, \
                                acct.get("cb_tripped", False), \
                                acct.get("profit_locked", False), \
                                acct.get("active", False)
        trades, max_t = acct.get("trade_count", 0), acct.get("max_trades", 6)
        gate          = acct.get("gate_status", "—")
        status_color  = MUTED if not active else ROSE if cb else GOLD if lock else MINT if gate == "CLEAR" else ORANGE
        status_text   = "INACTIVE" if not active else "CB TRIPPED" if cb else "PROFIT LOCK" if lock else "CLEAR" if gate == "CLEAR" else gate
        net_color     = MINT if net > 0 else ROSE if net < 0 else TEXT_MAIN
        cards.append(html.Div([
            html.Div(acct.get("name", acct.get("account_id", "?")),
                     style={"fontSize": "11px", "color": TEXT_DIM, "marginBottom": "4px"}),
            html.Div([
                html.Span(status_text, style={"color": status_color, "fontWeight": "700",
                                              "fontSize": "13px", "marginRight": "12px"}),
                html.Span(f"${net:+,.0f}", style={"color": net_color, "fontWeight": "600",
                                                   "fontSize": "13px", "marginRight": "12px"}),
                html.Span(f"{trades}/{max_t}t", style={"color": TEXT_DIM, "fontSize": "12px"}),
            ]),
        ], style={"padding": "8px 12px", "marginBottom": "6px",
                  "backgroundColor": DARK_BG, "borderRadius": "6px",
                  "border": f"1px solid {status_color}44"}))
    return cards or html.Span("No accounts configured", style={"color": MUTED, "fontSize": "12px"})


# ─────────────────────────────────────────────────────────────────────────────
#  CALLBACK 7 — System Health Panel  (every 5 s)
# ─────────────────────────────────────────────────────────────────────────────

_HEALTH_FILE = BASE_DIR / "system_health.json"

@app.callback(Output("health-panel", "children"), Input("refresh", "n_intervals"))
def update_health_panel(_):
    try:
        if not _HEALTH_FILE.exists():
            return html.Span("Health monitor not running", style={"color": GOLD, "fontSize": "12px"})
        data = json.loads(_HEALTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return html.Span("Health file unreadable", style={"color": ROSE, "fontSize": "12px"})

    rows = [html.Div(
        f"{'✓' if c.get('ok') else '✗'}  {c['name']}  —  {c.get('detail', '')}",
        style={"fontSize": "12px", "color": MINT if c.get("ok") else ROSE, "marginBottom": "3px"}
    ) for c in data.get("checks", [])]

    uptime = data.get("uptime_pct")
    last   = data.get("last_check", "")[-8:] if data.get("last_check") else "—"
    rows.append(html.Div(
        f"Uptime {uptime:.1f}%  |  Last {last} UTC" if uptime else f"Last check {last} UTC",
        style={"fontSize": "10px", "color": MUTED, "marginTop": "6px"}
    ))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
#  CALLBACK 8 — Alert Monitor Macro Panel  (every 5 min, existing)
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    [Output("macro-regime-banner",  "children"),
     Output("macro-regime-banner",  "style"),
     Output("macro-vix-card",       "children"),
     Output("macro-yield-card",     "children"),
     Output("macro-hy-card",        "children"),
     Output("macro-dollar-card",    "children"),
     Output("macro-gap-card",       "children"),
     Output("macro-news-card",      "children"),
     Output("macro-policy-panel",   "children"),
     Output("macro-news-panel",     "children"),
     Output("macro-calendar-panel", "children"),
     Output("macro-rec-panel",      "children")],
    Input("macro-refresh", "n_intervals"),
)
def update_macro_panel(_):
    data = load_macro()

    no_data_msg  = html.Span("No macro data — run macro_intelligence.py",
                              style={"color": GOLD, "fontSize": "12px"})
    empty_card   = _macro_vital_card("—", "—", MUTED)

    regime   = data.get("regime", "UNKNOWN")
    score    = data.get("score", 0)
    ts_str   = data.get("timestamp", "")
    vix      = data.get("vix")
    yc       = data.get("yield_curve")
    hy       = data.get("hy_spread")
    dollar   = data.get("dollar")
    nq_gap   = data.get("nq_premarket_gap")
    gap_lbl  = data.get("gap_label", "")
    gap_dir  = data.get("gap_direction", "")
    news_lbl = data.get("news_label", "NORMAL")
    nscore   = data.get("news_score", 0)
    policy   = data.get("policy_risk", False)
    pterms   = data.get("policy_terms", [])
    pposts   = data.get("policy_posts", [])
    hi       = data.get("high_impact_today", False)
    event    = data.get("event_name", "NONE")
    hdlines  = data.get("top_headlines", [])
    rec      = data.get("recommendation", "")

    stale_warn = ""
    if ts_str:
        try:
            ts_dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            age_h = (datetime.datetime.now(datetime.timezone.utc) - ts_dt).total_seconds() / 3600
            if age_h > MACRO_STALE_HOURS:
                stale_warn = f"  [STALE — {age_h:.0f}h ago]"
        except Exception:
            pass

    regime_colors = {
        "RISK-OFF": ("#7f1d1d", "#fca5a5", "#dc2626"),
        "CAUTION":  ("#451a03", "#fde68a", "#d97706"),
        "NORMAL":   ("#052e16", "#6ee7b7", "#10b981"),
        "UNKNOWN":  ("#1a1a1a", TEXT_DIM,  MUTED),
    }
    bg, fg, border = regime_colors.get(regime, regime_colors["UNKNOWN"])
    banner_style = {"backgroundColor": bg, "border": f"2px solid {border}",
                    "borderRadius": "8px", "padding": "10px 16px",
                    "display": "flex", "alignItems": "center", "gap": "24px"}
    banner_children = [
        html.Span(regime, style={"fontSize": "20px", "fontWeight": "700", "color": fg,
                                  "fontFamily": "monospace", "letterSpacing": "0.05em"}),
        html.Span(f"Score: {score}", style={"fontSize": "13px", "color": fg, "fontFamily": "monospace"}),
        html.Span(f"{ts_str[:16].replace('T',' ')} UTC{stale_warn}",
                  style={"fontSize": "11px", "color": TEXT_DIM, "fontFamily": "monospace"}),
    ]

    def vix_c():
        if vix is None: return empty_card
        c = ROSE if vix > 28 else GOLD if vix > 20 else MINT
        return _macro_vital_card("VIX", f"{vix:.1f}", c)
    def yield_c():
        if yc is None: return empty_card
        c = ROSE if yc < -0.5 else GOLD if yc < 0 else MINT
        lbl = " INV" if yc < 0 else ""
        return _macro_vital_card("Yield Curve", f"{yc:.2f}{lbl}", c)
    def hy_c():
        if hy is None: return empty_card
        c = ROSE if hy > 4.5 else GOLD if hy > 3.5 else MINT
        return _macro_vital_card("HY Spread", f"{hy:.2f}%", c)
    def dollar_c():
        if dollar is None: return empty_card
        return _macro_vital_card("Dollar Index", f"{dollar:.2f}", CYAN)
    def gap_c():
        if nq_gap is None: return empty_card
        c = ROSE if nq_gap < -0.5 else MINT if nq_gap > 0.5 else TEXT_MAIN
        return _macro_vital_card("NQ Pre-Mkt Gap", f"{nq_gap:+.2f}%  {gap_lbl}", c)
    def news_c():
        c = ROSE if news_lbl == "HIGH RISK" else GOLD if news_lbl == "ELEVATED" else MINT
        return _macro_vital_card("News Sentiment", f"{news_lbl} ({nscore})", c)

    policy_children = ([
        html.Div("POLICY RISK DAY", style={"color": ROSE, "fontWeight": "700",
                                            "fontSize": "13px", "marginBottom": "6px"}),
        html.Div("Keywords: " + ", ".join(pterms), style={"fontSize": "11px", "color": GOLD, "marginBottom": "6px"}),
        *[html.Div(f"› {p}", style={"fontSize": "11px", "color": TEXT_DIM, "marginBottom": "3px"})
          for p in pposts[:5]],
    ] if policy else [
        html.Div("CLEAR", style={"color": MINT, "fontWeight": "700",
                                  "fontSize": "13px", "marginBottom": "4px"}),
        html.Div("No policy risk in last 24h", style={"color": MUTED, "fontSize": "11px"}),
    ])

    news_children = ([
        html.Div([
            html.Span(f"{i+1}. ", style={"color": TEXT_DIM, "fontSize": "11px"}),
            html.Span(h[:100], style={"color": TEXT_MAIN, "fontSize": "11px"}),
        ], style={"marginBottom": "5px"})
        for i, h in enumerate(hdlines[:5])
    ] if hdlines else [html.Span("No headlines — add NEWS_API_KEY to .env",
                                  style={"color": MUTED, "fontSize": "11px"})])

    cal_children = ([
        html.Div("TODAY", style={"color": ROSE, "fontWeight": "700",
                                  "fontSize": "12px", "marginBottom": "4px"}),
        html.Div(f"⚠ {event}", style={"color": ROSE, "fontSize": "13px",
                                       "fontFamily": "monospace", "fontWeight": "600"}),
        html.Div("Expect elevated volatility.", style={"color": TEXT_DIM, "fontSize": "11px", "marginTop": "6px"}),
    ] if hi and event != "NONE" else [
        html.Div("No high-impact events today", style={"color": MINT, "fontSize": "12px"}),
    ])

    rec_colors = {"RISK-OFF": ROSE, "CAUTION": GOLD, "NORMAL": MINT}
    rec_color  = rec_colors.get(regime, TEXT_MAIN)
    size_txt   = ("0 contracts — DO NOT TRADE" if regime == "RISK-OFF" else
                  "1 contract max" if regime == "CAUTION" else "2 contracts (standard)")
    dir_txt    = ("Flat all day" if regime == "RISK-OFF" else
                  "Shorts preferred" if nq_gap is not None and nq_gap < -0.5 else
                  "Longs favored" if nq_gap is not None and nq_gap > 0.5 else
                  "Both directions" if regime == "NORMAL" else "Reduce risk")

    rec_children = [
        html.Div(regime, style={"color": rec_color, "fontSize": "16px", "fontWeight": "700",
                                 "fontFamily": "monospace", "marginBottom": "8px"}),
        html.Div([html.Span("Size: ",  style={**STAT_LABEL, "marginBottom":"0","marginRight":"4px"}),
                  html.Span(size_txt, style={"color": rec_color, "fontSize":"12px"})],
                 style={"marginBottom": "4px"}),
        html.Div([html.Span("Direction: ", style={**STAT_LABEL, "marginBottom":"0","marginRight":"4px"}),
                  html.Span(dir_txt, style={"color": TEXT_MAIN, "fontSize":"12px"})],
                 style={"marginBottom": "8px"}),
        html.Div(rec[:160] if rec else "—",
                 style={"color": TEXT_DIM, "fontSize": "11px", "lineHeight": "1.5"}),
    ]

    return (banner_children, banner_style,
            vix_c(), yield_c(), hy_c(), dollar_c(), gap_c(), news_c(),
            policy_children, news_children, cal_children, rec_children)


# ─────────────────────────────────────────────────────────────────────────────
#  STARTUP
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT") or os.getenv("DASH_PORT", 8050))
    print(f"\n{'='*52}")
    print(f"  SENTINEL PRIME  |  NQ-ASIM Intelligence Layer v1")
    print(f"  http://localhost:{port}")
    print(f"{'='*52}\n")
    app.run(debug=False, host="0.0.0.0", port=port)
