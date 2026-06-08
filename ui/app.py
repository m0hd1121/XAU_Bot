"""
app.py — XAU/USD Price Action Bot Dashboard
────────────────────────────────────────────
Run with:  streamlit run ui/app.py
"""

from __future__ import annotations

import sys
import os
import io
import json
import logging
import time
from copy import deepcopy
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np
import streamlit as st
import yaml

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from ui.charts import (
    equity_curve_chart, monthly_returns_heatmap, r_distribution_chart,
    session_performance_chart, win_rate_donut, pnl_histogram,
    direction_breakdown_chart, price_chart_with_trades, THEME,
)

# ─────────────────────────────────────────────────────────────────────────────
# Page config (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="XAU Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Global CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}
.stApp { background-color: #0d1117; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: #161b22;
    border-right: 1px solid #30363d;
}
[data-testid="stSidebar"] .stRadio label {
    font-size: 14px;
    color: #8b949e;
    padding: 4px 0;
}
[data-testid="stSidebar"] .stRadio label:hover { color: #e6edf3; }

/* ── Metric cards ── */
.metric-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 18px 20px;
    text-align: center;
    transition: border-color 0.2s;
}
.metric-card:hover { border-color: #58a6ff; }
.metric-label {
    font-size: 11px;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
}
.metric-value {
    font-size: 26px;
    font-weight: 700;
    color: #e6edf3;
    line-height: 1.1;
}
.metric-sub {
    font-size: 11px;
    color: #8b949e;
    margin-top: 3px;
}
.metric-pos { color: #3fb950; }
.metric-neg { color: #f85149; }
.metric-neu { color: #58a6ff; }

/* ── Section headers ── */
.section-header {
    font-size: 13px;
    font-weight: 600;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 8px 0 4px;
    border-bottom: 1px solid #21262d;
    margin-bottom: 12px;
}

/* ── Status badge ── */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
}
.badge-green { background: rgba(63,185,80,0.15); color: #3fb950; border: 1px solid rgba(63,185,80,0.3); }
.badge-red   { background: rgba(248,81,73,0.15);  color: #f85149; border: 1px solid rgba(248,81,73,0.3); }
.badge-blue  { background: rgba(88,166,255,0.15); color: #58a6ff; border: 1px solid rgba(88,166,255,0.3); }
.badge-gold  { background: rgba(240,192,64,0.15); color: #f0c040; border: 1px solid rgba(240,192,64,0.3); }

/* ── Tables ── */
.stDataFrame { border-radius: 8px; overflow: hidden; }
[data-testid="stDataFrame"] { border: 1px solid #30363d; border-radius: 8px; }

/* ── Buttons ── */
.stButton > button {
    background: #238636;
    color: white;
    border: 1px solid #2ea043;
    border-radius: 6px;
    font-weight: 600;
    transition: all 0.15s;
}
.stButton > button:hover {
    background: #2ea043;
    border-color: #3fb950;
    transform: translateY(-1px);
}

/* ── Tabs ── */
.stTabs [role="tab"] {
    font-size: 13px;
    color: #8b949e;
    padding: 8px 16px;
}
.stTabs [role="tab"][aria-selected="true"] {
    color: #e6edf3;
    border-bottom-color: #f0c040;
}

/* ── Code / Log box ── */
.log-box {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 12px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 11px;
    color: #8b949e;
    max-height: 220px;
    overflow-y: auto;
    white-space: pre-wrap;
}

/* ── Divider ── */
hr { border-color: #21262d; margin: 16px 0; }

/* ── Expanders ── */
.streamlit-expanderHeader { color: #8b949e; font-size: 13px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_config(path: str = str(ROOT / "config.yaml")) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def save_config(cfg: dict, path: str = str(ROOT / "config.yaml")) -> None:
    with open(path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
    st.cache_data.clear()


def load_trade_log() -> Optional[pd.DataFrame]:
    path = ROOT / "reports" / "trade_log.csv"
    if path.exists():
        df = pd.read_csv(path)
        return df
    return None


def load_equity_curve() -> Optional[list[float]]:
    path = ROOT / "reports" / "equity_curve.csv"
    if path.exists():
        df = pd.read_csv(path)
        return df["equity"].tolist()
    return None


def load_metrics() -> Optional[dict]:
    path = ROOT / "reports" / "metrics.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def load_ohlc() -> Optional[pd.DataFrame]:
    try:
        cfg = load_config()
        csv_path = ROOT / cfg["data"]["csv_path"]
        if csv_path.exists():
            df = pd.read_csv(csv_path, parse_dates=["time"])
            df.set_index("time", inplace=True)
            return df
    except Exception:
        pass
    return None


def metric_card(label: str, value: str, sub: str = "",
                color_class: str = "metric-neu") -> str:
    return f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value {color_class}">{value}</div>
        {"<div class='metric-sub'>" + sub + "</div>" if sub else ""}
    </div>"""


def badge(text: str, style: str = "blue") -> str:
    return f'<span class="badge badge-{style}">{text}</span>'


def run_backtest_with_capture(cfg: dict) -> tuple[Optional[dict], list[float], list[dict], str]:
    """Run backtest and return (metrics, equity_curve, trades, log_output)."""
    log_buffer = io.StringIO()
    handler = logging.StreamHandler(log_buffer)
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s",
                                            datefmt="%H:%M:%S"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    old_level = root_logger.level
    root_logger.setLevel(logging.INFO)

    try:
        from xau_bot.backtester import Backtester
        bt = Backtester(cfg)
        result = bt.run()
        return result.metrics, result.equity_curve, result.trades, log_buffer.getvalue()
    except Exception as e:
        return None, [], [], f"ERROR: {e}\n{log_buffer.getvalue()}"
    finally:
        root_logger.removeHandler(handler)
        root_logger.setLevel(old_level)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar Navigation
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar() -> str:
    with st.sidebar:
        st.markdown(f"""
        <div style="padding: 8px 0 20px;">
            <div style="font-size:22px; font-weight:800; color:#f0c040; letter-spacing:-0.5px;">
                📈 XAU Bot
            </div>
            <div style="font-size:11px; color:#8b949e; margin-top:2px;">
                Price Action Trading System
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-header">Navigation</div>', unsafe_allow_html=True)
        page = st.radio(
            "",
            ["📊  Dashboard", "🔬  Backtest", "⚙️  Configuration", "📋  Trade Log"],
            label_visibility="collapsed",
        )

        st.markdown("---")
        cfg = load_config()
        mode = cfg.get("bot", {}).get("mode", "backtest")
        mode_badge = {"backtest": "gold", "paper": "blue", "live": "green"}.get(mode, "blue")
        st.markdown(
            f'<div class="metric-label">Mode</div>'
            f'{badge(mode.upper(), mode_badge)}',
            unsafe_allow_html=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="metric-label">Symbol</div>', unsafe_allow_html=True)
        st.markdown(
            f'{badge(cfg.get("bot", {}).get("symbol", "XAUUSD"), "gold")}',
            unsafe_allow_html=True,
        )

        # Quick risk overview
        rc = cfg.get("risk", {})
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-header">Risk Parameters</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div style="font-size:12px; color:#8b949e; line-height:1.9;">
            Risk/Trade: <span style="color:#e6edf3;">{rc.get('risk_per_trade',0)*100:.1f}%</span><br>
            Daily Limit: <span style="color:#e6edf3;">{rc.get('daily_loss_limit',0)*100:.1f}%</span><br>
            Kill DD: <span style="color:#e6edf3;">{rc.get('max_drawdown_kill',0)*100:.1f}%</span><br>
            Capital: <span style="color:#e6edf3;">${rc.get('initial_capital',0):,.0f}</span>
        </div>
        """, unsafe_allow_html=True)

    return page.split("  ", 1)[-1].strip()


# ─────────────────────────────────────────────────────────────────────────────
# Page: Dashboard
# ─────────────────────────────────────────────────────────────────────────────

def page_dashboard():
    st.markdown('<h2 style="color:#e6edf3; margin-bottom:4px;">Dashboard</h2>', unsafe_allow_html=True)
    st.markdown('<div style="color:#8b949e; font-size:13px; margin-bottom:20px;">Overview of latest backtest results</div>', unsafe_allow_html=True)

    metrics  = load_metrics()
    equity   = load_equity_curve()
    trades_df = load_trade_log()

    if metrics is None:
        st.markdown("""
        <div style="background:#161b22; border:1px solid #30363d; border-radius:10px;
                    padding:40px; text-align:center; margin:20px 0;">
            <div style="font-size:32px; margin-bottom:12px;">📭</div>
            <div style="color:#e6edf3; font-size:16px; font-weight:600; margin-bottom:8px;">
                No backtest results yet
            </div>
            <div style="color:#8b949e; font-size:13px;">
                Run a backtest from the <strong>Backtest</strong> tab to see results here.
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    initial  = metrics.get("initial_capital", 10000)
    final    = metrics.get("final_equity", initial)
    ret_pct  = metrics.get("total_return_pct", 0)
    win_rate = metrics.get("win_rate_pct", 0)
    pf       = metrics.get("profit_factor", 0)
    sharpe   = metrics.get("sharpe_ratio", 0)
    max_dd   = metrics.get("max_drawdown_pct", 0)
    total_t  = metrics.get("total_trades", 0)
    winners  = metrics.get("winners", 0)
    losers   = metrics.get("losers", 0)

    # ── Metric row ────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        color = "metric-pos" if ret_pct >= 0 else "metric-neg"
        st.markdown(metric_card("Total Return", f"{ret_pct:+.2f}%",
                                f"${final:,.2f} equity", color), unsafe_allow_html=True)
    with c2:
        color = "metric-pos" if pf >= 1.5 else ("metric-neg" if pf < 1.0 else "metric-neu")
        st.markdown(metric_card("Profit Factor", f"{pf:.2f}",
                                "Gross W / Gross L", color), unsafe_allow_html=True)
    with c3:
        color = "metric-pos" if win_rate >= 50 else "metric-neg"
        st.markdown(metric_card("Win Rate", f"{win_rate:.1f}%",
                                f"{winners}W  {losers}L", color), unsafe_allow_html=True)
    with c4:
        color = "metric-pos" if sharpe >= 1.0 else ("metric-neg" if sharpe < 0 else "metric-neu")
        st.markdown(metric_card("Sharpe Ratio", f"{sharpe:.2f}",
                                "Risk-adjusted return", color), unsafe_allow_html=True)
    with c5:
        color = "metric-neg" if max_dd > 10 else ("metric-neu" if max_dd > 5 else "metric-pos")
        st.markdown(metric_card("Max Drawdown", f"{max_dd:.2f}%",
                                f"${metrics.get('max_drawdown_dollar', 0):,.2f}", color), unsafe_allow_html=True)
    with c6:
        exp_r = metrics.get("expectancy_r", 0)
        color = "metric-pos" if exp_r > 0 else "metric-neg"
        st.markdown(metric_card("Expectancy", f"{exp_r:+.3f}R",
                                f"${metrics.get('expectancy_dollar',0):+.2f}/trade", color), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Equity curve ──────────────────────────────────────────────────────────
    if equity:
        st.plotly_chart(equity_curve_chart(equity, initial), use_container_width=True)

    # ── Row 2: Session / Direction / Donut ───────────────────────────────────
    col_a, col_b, col_c = st.columns([2, 1.5, 1.2])

    with col_a:
        by_session = metrics.get("by_session", {})
        if by_session:
            st.plotly_chart(session_performance_chart(by_session), use_container_width=True)

    with col_b:
        by_dir = metrics.get("by_direction", {})
        if by_dir:
            st.plotly_chart(direction_breakdown_chart(by_dir), use_container_width=True)

    with col_c:
        st.plotly_chart(win_rate_donut(winners, losers), use_container_width=True)

    # ── Monthly heatmap ──────────────────────────────────────────────────────
    monthly = metrics.get("monthly_pnl", {})
    if monthly:
        st.plotly_chart(monthly_returns_heatmap(monthly, initial), use_container_width=True)

    # ── Additional stats strip ────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-header">Additional Statistics</div>', unsafe_allow_html=True)
    cols = st.columns(5)
    extra_metrics = [
        ("CAGR", f"{metrics.get('cagr_pct', 0):+.2f}%"),
        ("Calmar Ratio",      f"{metrics.get('calmar_ratio', 0):.3f}"),
        ("Recovery Factor",   f"{metrics.get('recovery_factor', 0):.3f}"),
        ("Max Win Streak",    str(metrics.get("max_consec_wins", 0))),
        ("Max Loss Streak",   str(metrics.get("max_consec_losses", 0))),
    ]
    for col, (label, value) in zip(cols, extra_metrics):
        with col:
            st.markdown(metric_card(label, value), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Backtest
# ─────────────────────────────────────────────────────────────────────────────

def page_backtest():
    st.markdown('<h2 style="color:#e6edf3; margin-bottom:4px;">Backtest Runner</h2>', unsafe_allow_html=True)
    st.markdown('<div style="color:#8b949e; font-size:13px; margin-bottom:20px;">Configure and run a historical simulation</div>', unsafe_allow_html=True)

    cfg = deepcopy(load_config())

    # ── Parameter panel ───────────────────────────────────────────────────────
    with st.expander("⚙️  Backtest Parameters", expanded=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown('<div class="section-header">Date Range</div>', unsafe_allow_html=True)
            start_date = st.date_input("Start Date",
                value=datetime.strptime(cfg["backtest"]["start_date"], "%Y-%m-%d").date(),
                min_value=date(2010, 1, 1), max_value=date(2030, 12, 31))
            end_date = st.date_input("End Date",
                value=datetime.strptime(cfg["backtest"]["end_date"], "%Y-%m-%d").date(),
                min_value=date(2010, 1, 1), max_value=date(2030, 12, 31))

        with col2:
            st.markdown('<div class="section-header">Risk Settings</div>', unsafe_allow_html=True)
            capital = st.number_input("Initial Capital ($)", min_value=1000, max_value=1_000_000,
                                       value=int(cfg["risk"]["initial_capital"]), step=1000)
            risk_pct = st.slider("Risk per Trade (%)", 0.5, 2.0,
                                  float(cfg["risk"]["risk_per_trade"] * 100), 0.1)
            daily_limit = st.slider("Daily Loss Limit (%)", 1.0, 10.0,
                                     float(cfg["risk"]["daily_loss_limit"] * 100), 0.5)

        with col3:
            st.markdown('<div class="section-header">Strategy Settings</div>', unsafe_allow_html=True)
            min_rr = st.slider("Min R:R Ratio", 1.0, 5.0,
                                float(cfg["risk"]["min_reward_to_risk"]), 0.5)
            require_htf = st.checkbox("Require HTF Bias", value=cfg["strategy"]["require_htf_bias"])
            require_session = st.checkbox("Require Session Window",
                                           value=cfg["strategy"]["require_session_window"])
            min_quality = st.slider("Min Setup Quality Score", 0.3, 0.9,
                                     float(cfg["psychology"]["min_setup_quality_score"]), 0.05)

    # ── Apply overrides ───────────────────────────────────────────────────────
    cfg["backtest"]["start_date"]           = str(start_date)
    cfg["backtest"]["end_date"]             = str(end_date)
    cfg["risk"]["initial_capital"]          = float(capital)
    cfg["risk"]["risk_per_trade"]           = risk_pct / 100
    cfg["risk"]["daily_loss_limit"]         = daily_limit / 100
    cfg["risk"]["min_reward_to_risk"]       = float(min_rr)
    cfg["strategy"]["require_htf_bias"]     = require_htf
    cfg["strategy"]["require_session_window"] = require_session
    cfg["psychology"]["min_setup_quality_score"] = float(min_quality)

    # ── Data check ────────────────────────────────────────────────────────────
    csv_path = ROOT / cfg["data"]["csv_path"]
    data_exists = csv_path.exists()

    col_run, col_gen, col_spacer = st.columns([1, 1, 4])
    with col_run:
        run_btn = st.button("▶  Run Backtest", disabled=not data_exists, use_container_width=True)
    with col_gen:
        if st.button("⬇  Generate Sample Data", use_container_width=True):
            with st.spinner("Generating 3 years of synthetic XAUUSD H1 data..."):
                from data.generate_sample_data import generate_and_save
                generate_and_save(str(ROOT / cfg["data"]["csv_path"]))
            st.success("Sample data generated!")
            st.rerun()

    if not data_exists:
        st.warning(f"Data file not found: `{cfg['data']['csv_path']}`. Click **Generate Sample Data** first.")

    # ── Run ───────────────────────────────────────────────────────────────────
    if run_btn:
        with st.spinner("Running backtest… this may take 30–60 seconds for 3 years of H1 data."):
            progress = st.progress(0, text="Initialising…")
            progress.progress(10, text="Loading OHLC data…")
            metrics, equity, trades, log_out = run_backtest_with_capture(cfg)
            progress.progress(100, text="Complete!")

        if metrics is None:
            st.error("Backtest failed. Check the log below.")
            st.text_area("Error Log", log_out, height=200)
            return

        # Persist results
        save_config(cfg)
        st.session_state["last_metrics"] = metrics
        st.session_state["last_equity"]  = equity
        st.session_state["last_trades"]  = trades
        st.session_state["last_log"]     = log_out
        st.success(f"Backtest complete — {metrics.get('total_trades', 0)} trades executed.")

    # ── Results display ───────────────────────────────────────────────────────
    metrics = st.session_state.get("last_metrics", load_metrics())
    equity  = st.session_state.get("last_equity",  load_equity_curve())
    trades  = st.session_state.get("last_trades",  [])
    log_out = st.session_state.get("last_log", "")

    if not trades:
        trades_df = load_trade_log()
        if trades_df is not None:
            trades = trades_df.to_dict("records")

    if metrics is None:
        return

    # ── Metrics strip ─────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-header">Results</div>', unsafe_allow_html=True)

    initial = metrics.get("initial_capital", 10000)
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    summary = [
        ("Return",        f"{metrics.get('total_return_pct',0):+.2f}%",
         "metric-pos" if metrics.get("total_return_pct",0) >= 0 else "metric-neg"),
        ("Trades",        str(metrics.get("total_trades",0)), "metric-neu"),
        ("Win Rate",      f"{metrics.get('win_rate_pct',0):.1f}%",
         "metric-pos" if metrics.get("win_rate_pct",0) >= 50 else "metric-neg"),
        ("Profit Factor", f"{metrics.get('profit_factor',0):.2f}",
         "metric-pos" if metrics.get("profit_factor",0) >= 1.5 else "metric-neg"),
        ("Sharpe",        f"{metrics.get('sharpe_ratio',0):.2f}", "metric-neu"),
        ("Max DD",        f"{metrics.get('max_drawdown_pct',0):.2f}%",
         "metric-neg" if metrics.get("max_drawdown_pct",0) > 8 else "metric-pos"),
        ("Expect. (R)",   f"{metrics.get('expectancy_r',0):+.3f}R",
         "metric-pos" if metrics.get("expectancy_r",0) > 0 else "metric-neg"),
    ]
    for col, (lbl, val, cls) in zip([c1,c2,c3,c4,c5,c6,c7], summary):
        with col:
            st.markdown(metric_card(lbl, val, color_class=cls), unsafe_allow_html=True)

    # ── Charts ────────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["📈 Equity & Drawdown", "📊 Trade Analysis", "📅 Monthly Returns"])

    with t1:
        if equity:
            st.plotly_chart(equity_curve_chart(equity, initial), use_container_width=True)
        if trades:
            st.plotly_chart(r_distribution_chart(trades), use_container_width=True)

    with t2:
        col_l, col_r = st.columns(2)
        with col_l:
            if trades:
                st.plotly_chart(pnl_histogram(trades), use_container_width=True)
        with col_r:
            by_dir = metrics.get("by_direction", {})
            if by_dir:
                st.plotly_chart(direction_breakdown_chart(by_dir), use_container_width=True)

        by_sess = metrics.get("by_session", {})
        if by_sess:
            st.plotly_chart(session_performance_chart(by_sess), use_container_width=True)

    with t3:
        monthly = metrics.get("monthly_pnl", {})
        if monthly:
            st.plotly_chart(monthly_returns_heatmap(monthly, initial), use_container_width=True)
        else:
            st.info("No monthly breakdown available.")

    # ── Trade table ───────────────────────────────────────────────────────────
    if trades:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-header">Trade Log</div>', unsafe_allow_html=True)
        df_trades = pd.DataFrame(trades)

        # Style: colour PnL column
        display_cols = ["trade_id","open_time","direction","entry_price",
                        "close_price","sl_price","lot_size","pnl","pnl_r",
                        "close_reason","session","quality_score"]
        available = [c for c in display_cols if c in df_trades.columns]
        df_display = df_trades[available].copy()
        if "pnl" in df_display.columns:
            df_display["pnl"] = df_display["pnl"].round(2)
        if "pnl_r" in df_display.columns:
            df_display["pnl_r"] = df_display["pnl_r"].round(3)

        st.dataframe(
            df_display,
            use_container_width=True,
            height=min(400, max(200, len(df_display) * 35 + 38)),
        )

        # Download button
        csv_bytes = df_trades.to_csv(index=False).encode()
        st.download_button("⬇  Download Full Trade Log (CSV)", csv_bytes,
                           "trade_log.csv", "text/csv", use_container_width=False)

    # ── Log output ────────────────────────────────────────────────────────────
    if log_out:
        with st.expander("📄  Backtest Log"):
            st.markdown(f'<div class="log-box">{log_out}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Configuration
# ─────────────────────────────────────────────────────────────────────────────

def page_configuration():
    st.markdown('<h2 style="color:#e6edf3; margin-bottom:4px;">Configuration</h2>', unsafe_allow_html=True)
    st.markdown('<div style="color:#8b949e; font-size:13px; margin-bottom:20px;">Edit bot settings — changes are saved to <code>config.yaml</code></div>', unsafe_allow_html=True)

    cfg = deepcopy(load_config())

    tab_bot, tab_risk, tab_strat, tab_sess, tab_psych, tab_exec, tab_raw = st.tabs([
        "🤖 Bot", "💰 Risk", "📐 Strategy", "🕐 Sessions",
        "🧠 Psychology", "⚡ Execution", "📄 Raw YAML"
    ])

    # ── Bot settings ──────────────────────────────────────────────────────────
    with tab_bot:
        st.markdown('<div class="section-header">Bot Settings</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            cfg["bot"]["mode"]      = st.selectbox("Mode", ["backtest","paper","live"],
                                                     index=["backtest","paper","live"].index(cfg["bot"]["mode"]))
            cfg["bot"]["symbol"]    = st.text_input("Symbol", cfg["bot"]["symbol"])
            cfg["bot"]["timeframe"] = st.selectbox("Timeframe", ["1H","4H","1D","15min"],
                                                     index=["1H","4H","1D","15min"].index(cfg["bot"]["timeframe"]))
        with c2:
            cfg["bot"]["htf_timeframe"] = st.selectbox("HTF Timeframe", ["4H","1D","1H"],
                                                         index=["4H","1D","1H"].index(cfg["bot"]["htf_timeframe"]))
            cfg["data"]["csv_path"] = st.text_input("Data CSV Path", cfg["data"]["csv_path"])

    # ── Risk settings ─────────────────────────────────────────────────────────
    with tab_risk:
        st.markdown('<div class="section-header">Capital & Risk</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        rc = cfg["risk"]
        with c1:
            rc["initial_capital"]    = st.number_input("Initial Capital ($)", 1000, 10_000_000,
                                                         int(rc["initial_capital"]), 1000)
            rc["risk_per_trade"]     = st.slider("Risk per Trade (%)", 0.5, 2.0,
                                                   rc["risk_per_trade"]*100, 0.1) / 100
            rc["max_risk_per_trade"] = st.slider("Max Risk per Trade (%)", 0.5, 5.0,
                                                   rc["max_risk_per_trade"]*100, 0.1) / 100
        with c2:
            rc["daily_loss_limit"]     = st.slider("Daily Loss Limit (%)", 1.0, 10.0,
                                                     rc["daily_loss_limit"]*100, 0.5) / 100
            rc["max_drawdown_kill"]    = st.slider("Drawdown Kill-Switch (%)", 5.0, 25.0,
                                                    rc["max_drawdown_kill"]*100, 1.0) / 100
            rc["min_reward_to_risk"]   = st.slider("Min R:R Ratio", 1.0, 5.0,
                                                     float(rc["min_reward_to_risk"]), 0.5)
            rc["max_open_trades"]      = st.number_input("Max Open Trades", 1, 10,
                                                           int(rc["max_open_trades"]))

    # ── Strategy settings ─────────────────────────────────────────────────────
    with tab_strat:
        st.markdown('<div class="section-header">Entry & Exit Logic</div>', unsafe_allow_html=True)
        sc = cfg["strategy"]
        c1, c2 = st.columns(2)
        with c1:
            sc["require_htf_bias"]        = st.checkbox("Require HTF Bias",          sc["require_htf_bias"])
            sc["require_session_window"]  = st.checkbox("Require Session Window",     sc["require_session_window"])
            sc["use_break_even"]          = st.checkbox("Use Break-Even",             sc["use_break_even"])
            sc["trail_after_be"]          = st.checkbox("Trail After Break-Even",     sc["trail_after_be"])
            sc["entry_type"]              = st.selectbox("Entry Type", ["limit","market"],
                                                          index=["limit","market"].index(sc["entry_type"]))
        with c2:
            sc["tp1_rr"]            = st.slider("TP1 R:R", 1.0, 5.0, float(sc["tp1_rr"]), 0.5)
            sc["tp2_rr"]            = st.slider("TP2 R:R", 1.0, 8.0, float(sc["tp2_rr"]), 0.5)
            sc["partial_tp_pct"]    = st.slider("Partial Close at TP1 (%)", 0.25, 0.75,
                                                  float(sc["partial_tp_pct"]), 0.05)
            sc["sl_buffer_pips"]    = st.number_input("SL Buffer (price units)",
                                                        0.0, 20.0, float(sc["sl_buffer_pips"]), 0.5)
            sc["trail_step_pct"]    = st.number_input("Trail Step (%)", 0.001, 0.02,
                                                        float(sc["trail_step_pct"]), 0.001,
                                                        format="%.3f")

        st.markdown('<div class="section-header" style="margin-top:16px;">Market Structure</div>',
                    unsafe_allow_html=True)
        msc = cfg["market_structure"]
        c1, c2 = st.columns(2)
        with c1:
            msc["swing_lookback"] = st.number_input("Swing Lookback (bars)", 2, 20,
                                                      int(msc["swing_lookback"]))
            msc["zone_max_age_candles"] = st.number_input("Zone Max Age (bars)", 50, 500,
                                                            int(msc["zone_max_age_candles"]))
        with c2:
            msc["choch_require_sweep"] = st.checkbox("CHoCH Requires Sweep",
                                                       msc["choch_require_sweep"])
            msc["min_zone_impulse_ratio"] = st.number_input("Min Impulse Ratio", 1.0, 5.0,
                                                              float(msc["min_zone_impulse_ratio"]), 0.1)

    # ── Session settings ──────────────────────────────────────────────────────
    with tab_sess:
        st.markdown('<div class="section-header">Trading Sessions (UTC)</div>', unsafe_allow_html=True)
        for sess_name in ["london", "new_york", "overlap", "asian"]:
            s = cfg["sessions"].get(sess_name, {})
            with st.expander(f"🕐  {sess_name.replace('_',' ').title()}"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    s["start"] = st.text_input("Start (HH:MM)", s.get("start","00:00"),
                                                key=f"start_{sess_name}")
                with c2:
                    s["end"]   = st.text_input("End (HH:MM)", s.get("end","00:00"),
                                               key=f"end_{sess_name}")
                with c3:
                    s["weight"] = st.slider("Quality Weight", 0.0, 2.0,
                                             float(s.get("weight",1.0)), 0.1,
                                             key=f"weight_{sess_name}")

    # ── Psychology settings ───────────────────────────────────────────────────
    with tab_psych:
        st.markdown('<div class="section-header">Behavioural Rules</div>', unsafe_allow_html=True)
        pc = cfg["psychology"]
        c1, c2 = st.columns(2)
        with c1:
            pc["max_consecutive_losses"]   = st.number_input("Max Consecutive Losses",
                                                               1, 10, int(pc["max_consecutive_losses"]))
            pc["loss_streak_size_reduction"] = st.slider("Size After Streak (%)", 0.1, 1.0,
                                                           float(pc["loss_streak_size_reduction"]), 0.05)
            pc["cooldown_candles_after_loss"] = st.number_input("Cooldown After Loss (bars)",
                                                                  0, 50, int(pc["cooldown_candles_after_loss"]))
        with c2:
            pc["min_setup_quality_score"]  = st.slider("Min Setup Quality (0–1)", 0.1, 0.95,
                                                         float(pc["min_setup_quality_score"]), 0.05)
            pc["max_trades_per_session"]   = st.number_input("Max Trades per Session",
                                                               1, 10, int(pc["max_trades_per_session"]))
            pc["revenge_trade_detection"]  = st.checkbox("Revenge Trade Detection",
                                                           pc["revenge_trade_detection"])

    # ── Execution settings ────────────────────────────────────────────────────
    with tab_exec:
        st.markdown('<div class="section-header">Execution & Costs</div>', unsafe_allow_html=True)
        ec = cfg["execution"]
        c1, c2 = st.columns(2)
        with c1:
            ec["spread_pips"]    = st.number_input("Spread (price units)", 0.0, 20.0,
                                                     float(ec["spread_pips"]), 0.5)
            ec["slippage_pips"]  = st.number_input("Max Slippage (price units)", 0.0, 10.0,
                                                     float(ec["slippage_pips"]), 0.5)
            ec["slippage_model"] = st.selectbox("Slippage Model", ["random","fixed","volatility_scaled"],
                                                  index=["random","fixed","volatility_scaled"].index(
                                                      ec["slippage_model"]))
        with c2:
            ec["commission_per_lot"] = st.number_input("Commission per Lot ($)", 0.0, 50.0,
                                                         float(ec["commission_per_lot"]), 0.5)
            ec["min_lot"]  = st.number_input("Min Lot Size", 0.01, 1.0, float(ec["min_lot"]), 0.01,
                                               format="%.2f")
            ec["max_lot"]  = st.number_input("Max Lot Size", 0.1, 50.0, float(ec["max_lot"]), 0.1)

    # ── Raw YAML ──────────────────────────────────────────────────────────────
    with tab_raw:
        st.markdown('<div class="section-header">Raw YAML Preview</div>', unsafe_allow_html=True)
        raw_yaml = yaml.dump(cfg, default_flow_style=False, sort_keys=False)
        st.code(raw_yaml, language="yaml")
        st.download_button("⬇  Download config.yaml", raw_yaml.encode(),
                           "config.yaml", "text/yaml")

    # ── Save button ───────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    col_save, col_reset, _ = st.columns([1, 1, 5])
    with col_save:
        if st.button("💾  Save Configuration", use_container_width=True):
            save_config(cfg)
            st.success("Configuration saved to `config.yaml`")
    with col_reset:
        if st.button("↩  Reload from File", use_container_width=True):
            st.cache_data.clear()
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Page: Trade Log
# ─────────────────────────────────────────────────────────────────────────────

def page_trade_log():
    st.markdown('<h2 style="color:#e6edf3; margin-bottom:4px;">Trade Log</h2>', unsafe_allow_html=True)
    st.markdown('<div style="color:#8b949e; font-size:13px; margin-bottom:20px;">Analyse individual trades from the last backtest</div>', unsafe_allow_html=True)

    df = load_trade_log()
    if df is None or df.empty:
        st.info("No trade log found. Run a backtest first.")
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    with st.expander("🔍  Filters", expanded=True):
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            all_dirs = ["All"] + sorted(df["direction"].unique().tolist())
            dir_filter = st.selectbox("Direction", all_dirs)
        with fc2:
            all_sess = ["All"] + sorted(df["session"].unique().tolist()) if "session" in df else ["All"]
            sess_filter = st.selectbox("Session", all_sess)
        with fc3:
            outcome_filter = st.selectbox("Outcome", ["All", "Winners", "Losers"])
        with fc4:
            reason_opts = ["All"] + sorted(df["close_reason"].unique().tolist()) if "close_reason" in df else ["All"]
            reason_filter = st.selectbox("Close Reason", reason_opts)

    fdf = df.copy()
    if dir_filter != "All":
        fdf = fdf[fdf["direction"] == dir_filter]
    if sess_filter != "All" and "session" in fdf:
        fdf = fdf[fdf["session"] == sess_filter]
    if outcome_filter == "Winners":
        fdf = fdf[fdf["pnl"] > 0]
    elif outcome_filter == "Losers":
        fdf = fdf[fdf["pnl"] <= 0]
    if reason_filter != "All" and "close_reason" in fdf:
        fdf = fdf[fdf["close_reason"] == reason_filter]

    if fdf.empty:
        st.warning("No trades match the current filters.")
        return

    # ── Summary strip ─────────────────────────────────────────────────────────
    winners = (fdf["pnl"] > 0).sum()
    losers  = len(fdf) - winners
    total_pnl = fdf["pnl"].sum()
    avg_pnl   = fdf["pnl"].mean()
    wr        = winners / len(fdf) * 100

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(metric_card("Filtered Trades", str(len(fdf))), unsafe_allow_html=True)
    with c2:
        c = "metric-pos" if wr >= 50 else "metric-neg"
        st.markdown(metric_card("Win Rate", f"{wr:.1f}%", f"{winners}W  {losers}L", c),
                    unsafe_allow_html=True)
    with c3:
        c = "metric-pos" if total_pnl >= 0 else "metric-neg"
        st.markdown(metric_card("Total P&L", f"${total_pnl:+,.2f}", "", c),
                    unsafe_allow_html=True)
    with c4:
        c = "metric-pos" if avg_pnl >= 0 else "metric-neg"
        st.markdown(metric_card("Avg P&L / Trade", f"${avg_pnl:+,.2f}", "", c),
                    unsafe_allow_html=True)
    with c5:
        avg_r = fdf["pnl_r"].mean() if "pnl_r" in fdf else 0
        c = "metric-pos" if avg_r > 0 else "metric-neg"
        st.markdown(metric_card("Avg R", f"{avg_r:+.3f}R", "", c), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts ────────────────────────────────────────────────────────────────
    col_l, col_r = st.columns(2)
    with col_l:
        st.plotly_chart(pnl_histogram(fdf.to_dict("records")), use_container_width=True)
    with col_r:
        st.plotly_chart(r_distribution_chart(fdf.to_dict("records")), use_container_width=True)

    # ── Table ─────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Trades</div>', unsafe_allow_html=True)

    display_cols = [c for c in [
        "trade_id","open_time","direction","entry_price","close_price",
        "sl_price","lot_size","pnl","pnl_r","close_reason","session",
        "quality_score","tp1_hit","mae","mfe","equity_after",
    ] if c in fdf.columns]

    st.dataframe(
        fdf[display_cols].style.applymap(
            lambda v: f"color: {'#3fb950' if v > 0 else '#f85149'}" if isinstance(v, (int, float)) and not pd.isna(v) else "",
            subset=["pnl"] if "pnl" in display_cols else [],
        ),
        use_container_width=True,
        height=min(600, max(200, len(fdf) * 35 + 38)),
    )

    # ── Export ────────────────────────────────────────────────────────────────
    csv_bytes = fdf.to_csv(index=False).encode()
    st.download_button("⬇  Export Filtered Trades (CSV)", csv_bytes,
                       f"trades_filtered_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    page = render_sidebar()

    if page == "Dashboard":
        page_dashboard()
    elif page == "Backtest":
        page_backtest()
    elif page == "Configuration":
        page_configuration()
    elif page == "Trade Log":
        page_trade_log()


if __name__ == "__main__":
    main()
