# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Run the bot (from repo root)
.venv/bin/python main.py --mode paper          # paper trading
.venv/bin/python main.py --mode live           # live trading (requires MT5 + DWX EA)
.venv/bin/python main.py --mode backtest       # backtest using config.yaml dates

# Run all tests
.venv/bin/pytest tests/ -v

# Run a single test file
.venv/bin/pytest tests/test_market_structure.py -v

# Test broker connection end-to-end
.venv/bin/python scripts/test_trade.py

# Start the FastAPI control backend
cd backend && ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8443

# Start the Streamlit UI
.venv/bin/streamlit run ui/app.py --server.port 8502

# Start everything (used in production via systemd)
bash scripts/start_all.sh

# Backup / migration
bash scripts/backup.sh
bash scripts/export.sh           # creates full migration bundle
bash scripts/restore.sh /path/to/bundle.tar.gz
bash scripts/validate.sh         # PASS/FAIL health check after migration
```

## Architecture Overview

The system has four independent layers that communicate via files and HTTP:

### 1. Trading Engine (`main.py` + `xau_bot/`)

`main.py` is the single entry point. It runs three loops depending on mode:

- **`run_backtest(cfg)`** — feeds historical CSV candle-by-candle to `Backtester`
- **`run_paper(cfg)`** — polls Yahoo Finance (`GC=F`) on a tick loop, places simulated orders via `PaperBroker`
- **`run_live(cfg)`** — same tick loop as paper but routes orders to `DWXBroker`; falls back to paper if broker unavailable

Key helper functions in `main.py`:
- `_yf_params(cfg)` — derives `(interval, warmup_period, fresh_period, poll_ticks, bias_key_len)` from `bot.timeframe`. For 5M: `("5m", "60d", "2d", 2, 13)`. Yahoo Finance only keeps 60 days of 5M history.
- `_htf_bias_for_df(df, cfg)` — resamples the base DataFrame to the HTF (e.g., 5M→1H), runs `MarketStructureEngine` on it, and returns a `{timestamp_key: Trend}` map. The key length is 13 chars for 1H (hour-level), 10 for daily.
- `load_config(path)` — reads YAML then expands `${VAR:-default}` placeholders from environment variables before parsing.

**Pipeline per candle** (same in both paper and live):
```
_fetch_ohlc → DataHandler.enrich → MarketStructureEngine.update
→ StrategyEngine.evaluate → RiskManager.size_position
→ PsychologyLayer.filter → ExecutionEngine.submit → BrokerBase.place_order
```

The `StrategyEngine` holds `_htf_bias` (private — access as `strategy._htf_bias`, not `strategy.htf_bias`). Bias is injected via `strategy.set_htf_bias(trend)` before each bar.

### 2. Broker Abstraction (`xau_bot/broker.py`)

Four adapters all implement `BrokerBase`: `PaperBroker`, `DWXBroker`, `MetaApiBroker`, `OANDABroker`. `build_broker(cfg)` returns the right one based on `broker.type` in config.

**DWX file bridge** — the production path:
- Python writes `XAU_Orders.json` → MT5 EA (`XAU_Bridge.mq5`) reads it, executes, clears the file
- EA writes `XAU_Accounts.json` and `XAU_Positions.json` → Python reads them
- **JSON must be compact** — no spaces after separators. The EA's `ParseStr` looks for `"key":"` without a space. Always use `json.dumps(payload, separators=(',', ':'))`.
- The EA requires `req.deviation = 50` on all market orders or MT5 rejects the order silently.
- Broker symbol is `XAUUSD!` (with `!`) on OpoFinance.

### 3. FastAPI Control Backend (`backend/`)

Completely separate Python process from the trading engine. It reads the same `data/` and `logs/` directories that the trading engine writes to.

- Auth: JWT access token + refresh token; optional TOTP 2FA (`pyotp`)
- All routers mount under `/api/v1` — see `backend/app/routers/`
- WebSocket at `/ws/live` broadcasts dashboard snapshots every 1s and trade updates every 5s
- DB: async SQLite via SQLAlchemy (`aiosqlite`) — this is the backend's own DB, separate from the learning engine's `data/learning.db`
- Config via `pydantic-settings` (`backend/app/config.py`) — reads from environment variables

### 4. iOS App (`iOS/XAUBot/`)

SwiftUI + MVVM. Every screen follows the `*View` / `*ViewModel` pattern.

- `Network/APIClient.swift` — single async/await HTTP client with JWT refresh and certificate pinning
- `Network/Endpoints.swift` — all API routes as a typed enum
- `Network/WebSocketClient.swift` — connects to `/ws/live`, drives real-time dashboard
- `Services/AuthService.swift` — manages token storage in Keychain; `BiometricService` wraps Face ID / Touch ID
- The app stores the server base URL in settings and derives all endpoints from it

### 5. Self-Learning Engine (`xau_bot/learning/`)

Optional module (disabled by default: `learning.enabled: false`). `LearningEngine` orchestrates 7 sub-modules. Its only output is a `confidence_score` that can gate entries — it cannot override risk rules, stop losses, or drawdown limits.

## Configuration

`config.yaml` is the single source of truth for the trading engine. Deployment-specific values use `${VAR:-default}` so they can be overridden via a `.env` file (sourced by `scripts/start_all.sh`). Copy `.env.example` to `.env` and fill in VPS-specific values.

Key config sections and gotchas:
- `bot.timeframe` drives `_yf_params()` — changing it changes warmup period, poll interval, and HTF key format
- `market_structure.swing_lookback: 3` is tuned for 5M; increase to 5+ for 1H
- `broker.dwx.mt4_files_path` must exactly match the MQL5/Files path inside the Wine prefix
- `broker.dwx.magic` must match the Magic Number in the EA's MT5 input settings

## Systemd Service

In production, all processes run under `xaubot.service` (installed from `scripts/xaubot.service`). `start_all.sh` launches: Xvfb → MT5 under Wine → x11vnc with `-forever` flag → noVNC websockify → uvicorn backend → streamlit UI → bot. All are wrapped in `nohup` so they survive SSH session close.
