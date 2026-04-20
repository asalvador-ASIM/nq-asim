"""
NQ-ASIM v1.1 — Performance Chart Generator
Generates docs/performance.png (1200×600px) for README and LinkedIn.

Output: professional equity curve with Bloomberg-terminal aesthetic.
  - Dark background (#0a0f1e)
  - Combined system vs short-only baseline
  - Shaded region showing ATLAS long engine contribution
  - Key stat annotations
  - Cyan/teal color scheme

Usage:
    python docs/generate_chart.py
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── DATA ────────────────────────────────────────────────────────────────────
months_label = ['Nov\n2025', 'Dec\n2025', 'Jan\n2026', 'Feb\n2026',
                'Mar\n2026', 'Apr\n2026']
x = np.arange(len(months_label))

combined_pnl  = [0,  4200,  9800, 14500, 19000, 26268]
short_only    = [0,  3900,  8900, 12600, 17200, 20815]

# ── STYLE ────────────────────────────────────────────────────────────────────
BG       = '#0a0f1e'
BG2      = '#0d1525'
CYAN     = '#00e5ff'
MINT     = '#00ffbb'
GRAY     = '#4a6070'
GOLD     = '#f1c40f'
TEXT     = '#c8d8e8'
DIM      = '#4a6070'

plt.rcParams.update({
    'font.family':       'monospace',
    'font.size':         11,
    'axes.facecolor':    BG,
    'figure.facecolor':  BG,
    'axes.edgecolor':    '#1a2f45',
    'axes.labelcolor':   TEXT,
    'xtick.color':       DIM,
    'ytick.color':       DIM,
    'grid.color':        '#0d2035',
    'grid.linewidth':    0.8,
    'legend.framealpha': 0,
    'legend.labelcolor': TEXT,
    'text.color':        TEXT,
})

fig, ax = plt.subplots(figsize=(12, 6), dpi=100)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

# ── INTERPOLATED CURVES ──────────────────────────────────────────────────────
xi  = np.linspace(0, len(months_label) - 1, 300)
c_i = np.interp(xi, x, combined_pnl)
s_i = np.interp(xi, x, short_only)

# ── SHADED AREA — ATLAS long engine contribution ─────────────────────────────
ax.fill_between(xi, s_i, c_i,
                color=MINT, alpha=0.10,
                label='_nolegend_')

# Highlight the Apr 2026 ATLAS surge (x >= 4.5)
mask = xi >= 4.5
ax.fill_between(xi[mask], s_i[mask], c_i[mask],
                color=MINT, alpha=0.22,
                label='_nolegend_')

# ── LINES ────────────────────────────────────────────────────────────────────
ax.plot(xi, c_i, color=CYAN, linewidth=2.4, label='Combined System (NQ-ASIM v1.1)', zorder=5)
ax.plot(xi, s_i, color=GRAY, linewidth=1.4, linestyle='--',
        label='Short Engine Only (baseline)', zorder=4)

# ── DATA POINTS ──────────────────────────────────────────────────────────────
ax.scatter(x, combined_pnl, color=CYAN, s=50, zorder=6)
ax.scatter(x, short_only,   color=GRAY, s=30, zorder=5)

# ── ANNOTATIONS ──────────────────────────────────────────────────────────────
# Final combined P&L
ax.annotate('+$26,268',
            xy=(5, 26268), xytext=(4.35, 24600),
            fontsize=10, color=CYAN, fontweight='bold',
            arrowprops=dict(arrowstyle='->', color=CYAN, lw=1.2),
            bbox=dict(boxstyle='round,pad=0.3', fc=BG2, ec=CYAN, alpha=0.9))

# Short baseline final
ax.annotate('+$20,815\n(short only)',
            xy=(5, 20815), xytext=(4.0, 18500),
            fontsize=9, color=GRAY,
            arrowprops=dict(arrowstyle='->', color=GRAY, lw=1.0),
            bbox=dict(boxstyle='round,pad=0.3', fc=BG2, ec=GRAY, alpha=0.9))

# ATLAS v12 activation arrow
ax.annotate('ATLAS v12\nLong Engine\nActivates',
            xy=(5, 22541), xytext=(3.9, 23500),
            fontsize=8, color=MINT,
            arrowprops=dict(arrowstyle='->', color=MINT, lw=1.0),
            bbox=dict(boxstyle='round,pad=0.3', fc=BG2, ec=MINT, alpha=0.85))

# Apr surge bracket annotation
ax.axvline(x=4.5, color=MINT, linewidth=0.6, linestyle=':', alpha=0.5)

# Key stats box
stats_text = (
    'PF: 4.049    WR: 68.97%    DD: 0.91%\n'
    'Trades: 58   Sharpe: 1.006\n'
    'Short: 46 trades  ·  Long (ATLAS v12): 12 trades'
)
ax.text(0.02, 0.97, stats_text,
        transform=ax.transAxes,
        fontsize=9, color=DIM,
        verticalalignment='top',
        bbox=dict(boxstyle='round,pad=0.5', fc=BG2, ec='#1a2f45', alpha=0.9))

# ── AXES ─────────────────────────────────────────────────────────────────────
ax.set_xticks(x)
ax.set_xticklabels(months_label, fontsize=9)
ax.set_ylabel('Cumulative Net P&L ($)', fontsize=10, labelpad=10)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'${int(v):,}'))
ax.grid(True, axis='y', alpha=0.4)
ax.grid(True, axis='x', alpha=0.2)
ax.set_xlim(-0.3, 5.5)
ax.set_ylim(-1500, 30000)

# ── LEGEND ───────────────────────────────────────────────────────────────────
combined_patch = mpatches.Patch(color=CYAN,  label='Combined System (NQ-ASIM v1.1)')
short_patch    = mpatches.Patch(color=GRAY,  label='Short Engine Only (baseline)')
atlas_patch    = mpatches.Patch(color=MINT,  alpha=0.5, label='ATLAS Long Engine Contribution')
ax.legend(handles=[combined_patch, short_patch, atlas_patch],
          loc='upper left', fontsize=9, frameon=True,
          framealpha=0.85, facecolor=BG2, edgecolor='#1a2f45',
          bbox_to_anchor=(0.02, 0.82))

# ── TITLE / LABELS ───────────────────────────────────────────────────────────
ax.set_title(
    'NQ-ASIM v1.1 — Equity Curve\n'
    'Nov 2025 – Apr 2026  ·  Combined PF 4.049  ·  +$26,268  ·  Tradeify $50k',
    fontsize=13, color=TEXT, pad=14,
    fontweight='bold'
)

# Cyan top border line
fig.add_artist(plt.Line2D([0, 1], [1, 1], transform=fig.transFigure,
                           color=CYAN, linewidth=1.5, alpha=0.6))

# ── EXPORT ───────────────────────────────────────────────────────────────────
import os
out_path = os.path.join(os.path.dirname(__file__), 'performance.png')
plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig(out_path, dpi=100, bbox_inches='tight',
            facecolor=BG, edgecolor='none')
plt.close()
print(f'Saved: {out_path}')
