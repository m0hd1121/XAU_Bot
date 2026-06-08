"""
charts.py
─────────
Plotly chart builders for the XAU Bot dashboard.
All charts use a dark trading-terminal aesthetic.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Theme
# ─────────────────────────────────────────────────────────────────────────────

THEME = {
    "bg":          "#0d1117",
    "surface":     "#161b22",
    "surface2":    "#21262d",
    "border":      "#30363d",
    "text":        "#e6edf3",
    "text_muted":  "#8b949e",
    "green":       "#3fb950",
    "red":         "#f85149",
    "yellow":      "#d29922",
    "blue":        "#58a6ff",
    "purple":      "#bc8cff",
    "orange":      "#ffa657",
    "gold":        "#f0c040",
}

LAYOUT_DEFAULTS = dict(
    paper_bgcolor=THEME["bg"],
    plot_bgcolor=THEME["surface"],
    font=dict(color=THEME["text"], family="Inter, system-ui, sans-serif", size=12),
    margin=dict(l=12, r=12, t=36, b=12),
    xaxis=dict(
        gridcolor=THEME["border"], gridwidth=1,
        zerolinecolor=THEME["border"],
        tickfont=dict(color=THEME["text_muted"], size=11),
    ),
    yaxis=dict(
        gridcolor=THEME["border"], gridwidth=1,
        zerolinecolor=THEME["border"],
        tickfont=dict(color=THEME["text_muted"], size=11),
    ),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        bordercolor=THEME["border"],
        font=dict(color=THEME["text_muted"], size=11),
    ),
)


def _apply_layout(fig: go.Figure, title: str = "", height: int = 400) -> go.Figure:
    fig.update_layout(**LAYOUT_DEFAULTS, title=dict(
        text=title, font=dict(color=THEME["text_muted"], size=13), x=0.01
    ), height=height)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Equity Curve + Drawdown
# ─────────────────────────────────────────────────────────────────────────────

def equity_curve_chart(equity: list[float], initial: float,
                        title: str = "Equity Curve & Drawdown") -> go.Figure:
    eq  = np.array(equity)
    peak = np.maximum.accumulate(eq)
    dd   = (peak - eq) / (peak + 1e-10) * 100

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.04,
    )

    # ── Equity line ──────────────────────────────────────────────────────────
    color = THEME["green"] if eq[-1] >= initial else THEME["red"]
    fig.add_trace(go.Scatter(
        x=list(range(len(eq))), y=eq,
        mode="lines", name="Equity",
        line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor=f"rgba({'63,185,80' if color == THEME['green'] else '248,81,73'},0.08)",
    ), row=1, col=1)

    # Initial capital reference line
    fig.add_hline(y=initial, line=dict(color=THEME["border"], dash="dash", width=1),
                  row=1, col=1)

    # ── Drawdown ──────────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=list(range(len(dd))), y=-dd,
        mode="lines", name="Drawdown %",
        line=dict(color=THEME["red"], width=1.5),
        fill="tozeroy",
        fillcolor="rgba(248,81,73,0.15)",
    ), row=2, col=1)

    fig.update_yaxes(title_text="Equity ($)", title_font=dict(size=11, color=THEME["text_muted"]),
                     row=1, col=1)
    fig.update_yaxes(title_text="Drawdown %", title_font=dict(size=11, color=THEME["text_muted"]),
                     row=2, col=1)

    _apply_layout(fig, title, height=460)
    fig.update_layout(showlegend=False)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# OHLC + Trades Overlay
# ─────────────────────────────────────────────────────────────────────────────

def price_chart_with_trades(df: pd.DataFrame, trades: list[dict],
                             max_bars: int = 500) -> go.Figure:
    """Candlestick with long/short trade markers, SL/TP levels."""
    plot_df = df.tail(max_bars).copy()

    fig = go.Figure()

    # ── Candlesticks ──────────────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=plot_df.index,
        open=plot_df["open"], high=plot_df["high"],
        low=plot_df["low"],   close=plot_df["close"],
        name="XAUUSD",
        increasing=dict(line=dict(color=THEME["green"], width=1),
                        fillcolor="rgba(63,185,80,0.7)"),
        decreasing=dict(line=dict(color=THEME["red"], width=1),
                        fillcolor="rgba(248,81,73,0.7)"),
    ))

    # ── Trade markers ─────────────────────────────────────────────────────────
    long_entries  = [t for t in trades if t["direction"] == "long"]
    short_entries = [t for t in trades if t["direction"] == "short"]

    if long_entries:
        fig.add_trace(go.Scatter(
            x=[t["open_time"] for t in long_entries],
            y=[t["entry_price"] for t in long_entries],
            mode="markers+text",
            name="Long",
            marker=dict(symbol="triangle-up", size=12, color=THEME["green"],
                        line=dict(color="white", width=1)),
            text=["▲" for _ in long_entries],
            textposition="bottom center",
            textfont=dict(size=8, color=THEME["green"]),
        ))

    if short_entries:
        fig.add_trace(go.Scatter(
            x=[t["open_time"] for t in short_entries],
            y=[t["entry_price"] for t in short_entries],
            mode="markers",
            name="Short",
            marker=dict(symbol="triangle-down", size=12, color=THEME["red"],
                        line=dict(color="white", width=1)),
        ))

    _apply_layout(fig, "Price Chart — Last 500 Bars with Trades", height=420)
    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Monthly Returns Heatmap
# ─────────────────────────────────────────────────────────────────────────────

def monthly_returns_heatmap(monthly_pnl: dict, initial_capital: float) -> go.Figure:
    if not monthly_pnl:
        return go.Figure()

    rows: dict[str, dict[str, float]] = {}
    for ym, pnl in monthly_pnl.items():
        try:
            year, month = ym.split("-")
            pct = pnl / initial_capital * 100
            rows.setdefault(year, {})[month] = pct
        except Exception:
            continue

    years  = sorted(rows.keys())
    months = [f"{m:02d}" for m in range(1, 13)]
    month_labels = ["Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"]

    z     = []
    text  = []
    for year in years:
        row_z    = []
        row_text = []
        for m in months:
            val = rows[year].get(m, None)
            row_z.append(val)
            row_text.append(f"{val:+.2f}%" if val is not None else "")
        z.append(row_z)
        text.append(row_text)

    fig = go.Figure(go.Heatmap(
        z=z, x=month_labels, y=years,
        text=text, texttemplate="%{text}",
        textfont=dict(size=10, color="white"),
        colorscale=[
            [0.0,  THEME["red"]],
            [0.5,  THEME["surface2"]],
            [1.0,  THEME["green"]],
        ],
        zmid=0,
        showscale=True,
        colorbar=dict(
            tickfont=dict(color=THEME["text_muted"], size=10),
            title=dict(text="%", font=dict(color=THEME["text_muted"], size=11)),
            thickness=12,
        ),
        xgap=3, ygap=3,
    ))
    _apply_layout(fig, "Monthly Returns (%)", height=max(200, 60 + len(years) * 40))
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# R-Multiple Distribution
# ─────────────────────────────────────────────────────────────────────────────

def r_distribution_chart(trades: list[dict]) -> go.Figure:
    r_vals = [t.get("pnl_r", 0.0) for t in trades]
    if not r_vals:
        return go.Figure()

    colors = [THEME["green"] if r > 0 else THEME["red"] for r in r_vals]

    fig = go.Figure(go.Bar(
        x=list(range(1, len(r_vals) + 1)),
        y=r_vals,
        marker_color=colors,
        name="R-Multiple",
        hovertemplate="Trade #%{x}<br>R: %{y:.2f}<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color=THEME["border"], width=1))
    _apply_layout(fig, "R-Multiple per Trade", height=280)
    fig.update_yaxes(title_text="R", title_font=dict(size=11, color=THEME["text_muted"]))
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Session Performance
# ─────────────────────────────────────────────────────────────────────────────

def session_performance_chart(by_session: dict) -> go.Figure:
    if not by_session:
        return go.Figure()

    sessions = list(by_session.keys())
    pnls     = [by_session[s]["total_pnl"] for s in sessions]
    win_rates = [by_session[s]["win_rate"] for s in sessions]
    trade_counts = [by_session[s]["trades"] for s in sessions]
    colors = [THEME["green"] if p >= 0 else THEME["red"] for p in pnls]

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Bar(
        x=sessions, y=pnls, name="Total PnL ($)",
        marker_color=colors,
        text=[f"${p:,.0f}" for p in pnls],
        textposition="outside",
        textfont=dict(size=10, color=THEME["text"]),
        hovertemplate="%{x}<br>PnL: $%{y:,.2f}<extra></extra>",
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=sessions, y=win_rates, name="Win Rate %",
        mode="lines+markers",
        line=dict(color=THEME["gold"], width=2),
        marker=dict(size=8, color=THEME["gold"]),
        hovertemplate="%{x}<br>Win Rate: %{y:.1f}%<extra></extra>",
    ), secondary_y=True)

    _apply_layout(fig, "Performance by Session", height=300)
    fig.update_yaxes(title_text="P&L ($)", secondary_y=False,
                     title_font=dict(size=11, color=THEME["text_muted"]))
    fig.update_yaxes(title_text="Win Rate %", secondary_y=True,
                     title_font=dict(size=11, color=THEME["text_muted"]))
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Win Rate Donut
# ─────────────────────────────────────────────────────────────────────────────

def win_rate_donut(winners: int, losers: int) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=["Winners", "Losers"],
        values=[winners, losers],
        hole=0.65,
        marker_colors=[THEME["green"], THEME["red"]],
        textinfo="none",
        hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
    ))
    win_pct = winners / (winners + losers) * 100 if (winners + losers) > 0 else 0
    fig.add_annotation(
        text=f"<b>{win_pct:.1f}%</b><br><span style='font-size:10px;color:#8b949e'>Win Rate</span>",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=18, color=THEME["text"]),
        align="center",
    )
    _apply_layout(fig, "", height=220)
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5),
        margin=dict(l=0, r=0, t=20, b=40),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# PnL Distribution Histogram
# ─────────────────────────────────────────────────────────────────────────────

def pnl_histogram(trades: list[dict]) -> go.Figure:
    pnls = [t["pnl"] for t in trades]
    if not pnls:
        return go.Figure()

    fig = go.Figure(go.Histogram(
        x=pnls,
        nbinsx=20,
        marker_color=[THEME["green"] if p > 0 else THEME["red"] for p in pnls],
        name="P&L Distribution",
        opacity=0.85,
        hovertemplate="$%{x:.0f}: %{y} trades<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color=THEME["border"], dash="dash", width=1))
    mean_pnl = np.mean(pnls)
    fig.add_vline(
        x=mean_pnl,
        line=dict(color=THEME["gold"], dash="dot", width=1.5),
        annotation_text=f"Mean ${mean_pnl:+.0f}",
        annotation_font=dict(color=THEME["gold"], size=10),
    )
    _apply_layout(fig, "P&L Distribution", height=260)
    fig.update_xaxes(title_text="P&L ($)", title_font=dict(size=11, color=THEME["text_muted"]))
    fig.update_yaxes(title_text="Trades", title_font=dict(size=11, color=THEME["text_muted"]))
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Direction Breakdown
# ─────────────────────────────────────────────────────────────────────────────

def direction_breakdown_chart(by_direction: dict) -> go.Figure:
    if not by_direction:
        return go.Figure()

    directions = list(by_direction.keys())
    pnls = [by_direction[d]["total_pnl"] for d in directions]
    win_rates = [by_direction[d]["win_rate"] for d in directions]

    dir_colors = {"long": THEME["green"], "short": THEME["red"]}
    colors = [dir_colors.get(d, THEME["blue"]) for d in directions]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=directions, y=pnls, name="P&L",
        marker_color=colors,
        text=[f"${p:,.0f}" for p in pnls],
        textposition="outside",
        textfont=dict(size=11, color=THEME["text"]),
    ))

    for i, (d, wr) in enumerate(zip(directions, win_rates)):
        fig.add_annotation(
            x=d, y=min(pnls) - abs(min(pnls)) * 0.3,
            text=f"{wr:.0f}% WR", showarrow=False,
            font=dict(size=10, color=THEME["text_muted"]),
        )

    _apply_layout(fig, "Long vs Short", height=260)
    return fig
