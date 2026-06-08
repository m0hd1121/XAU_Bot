# 🏆 XAU Bot — Institutional-Grade XAU/USD Trading Bot

An automated gold trading bot with a complete iPhone control center, built on institutional price-action methodology — market structure, order blocks, liquidity sweeps, and a self-learning AI layer.

---

## 📖 Full Setup Guide

**➡️ [Read the complete step-by-step setup guide here](SETUP.md)**

The guide explains everything from zero — renting a VPS, installing the bot, building the iPhone app in Xcode, and making your first trade — written so anyone can follow it.

---

## 🏗️ What's Inside

```
XAU_Bot/
├── xau_bot/              # Core trading engine (Python)
│   ├── market_structure/ # BOS, CHoCH, order blocks, liquidity
│   ├── strategy/         # Entry/exit logic
│   ├── risk/             # Position sizing, drawdown protection
│   ├── execution/        # Order placement, fill simulation
│   ├── backtester.py     # Full backtesting engine
│   └── learning/         # Self-learning AI (8 modules)
│
├── backend/              # FastAPI control API (Python)
│   ├── app/              # API source code
│   ├── systemd/          # Linux service files
│   └── scripts/          # setup.sh, deploy.sh
│
├── iOS/XAUBot/           # iPhone app (Swift / SwiftUI)
│   ├── Dashboard/        # Real-time balance, equity, PnL
│   ├── BotControl/       # Start, stop, emergency stop
│   ├── Trades/           # Live trades + history
│   ├── Analytics/        # Swift Charts — equity, drawdown
│   ├── Learning/         # AI dashboard
│   ├── Configuration/    # Edit all bot settings remotely
│   ├── VPS/              # Server health monitoring
│   ├── Logs/             # Live log viewer
│   ├── Backup/           # Create, restore, export
│   └── Account/          # Broker account management
│
├── tests/                # 60 unit tests for the learning engine
├── config.yaml           # Main bot configuration
└── SETUP.md              # 👈 Full setup guide
```

---

## ⚡ Key Features

### Trading Engine
- **Market Structure Analysis** — Swing highs/lows, BOS, CHoCH detection
- **Order Block Detection** — Institutional supply/demand zones with impulse validation
- **Liquidity Analysis** — Equal highs/lows, inducement detection, sweep confirmation
- **Multi-Session Awareness** — London, New York, Overlap — each weighted by quality
- **Risk Management** — Per-trade sizing, daily loss limit, drawdown kill switch
- **Psychology Layer** — Loss streak detection, cooldown periods, revenge trade blocking

### Self-Learning AI (8 Modules)
- **TradeDatabase** — Records every trade with 30+ features
- **FeatureExtractor** — Extracts market context from each setup
- **PatternAnalyzer** — Finds statistically significant patterns (Wilson CI)
- **ConfidenceModel** — Bayesian EMA updates per feature
- **RegimeDetector** — Classifies market regime (trending/ranging/volatile)
- **ValidationEngine** — OOS + walk-forward validation, overfit detection
- **ExplainabilityEngine** — Human-readable explanation for every decision
- **LearningEngine** — Central orchestrator with safety constraints

### iPhone App (iOS 17+, SwiftUI)
- Real-time WebSocket dashboard (updates every second)
- Face ID / Touch ID login
- All destructive actions require explicit confirmation
- Swift Charts analytics (equity curve, drawdown, returns)
- Push notifications via APNs
- Complete offline-capable architecture

### Backend API (FastAPI)
- JWT authentication + TOTP 2FA
- Sliding-window rate limiting
- Full audit logging
- WebSocket live data feed
- systemd service integration

---

## 🛡️ Safety Guarantees

The learning engine **never**:
- Disables stop losses
- Increases account risk above configured limits
- Ignores the daily loss limit
- Ignores the drawdown kill switch
- Chases losses
- Optimizes win rate at the expense of expectancy

These constraints are hard-coded and cannot be overridden by the learning process.

---

## 🚀 Quick Start

```bash
# 1. Clone the repo on your VPS
git clone https://github.com/m0hd1121/xau_bot.git
cd xau_bot
git checkout claude/xauusd-price-action-bot-T80IJ

# 2. Run the automatic setup
sudo bash backend/scripts/setup.sh

# 3. Build the iPhone app in Xcode (on your Mac)
# See SETUP.md for detailed instructions

# 4. Log into the app and start in paper mode
```

---

## ⚠️ Risk Disclaimer

This software is for educational and research purposes. Trading financial instruments including gold (XAU/USD) carries significant risk of loss. Past performance of any strategy does not guarantee future results. Never trade with money you cannot afford to lose. Always test thoroughly in paper/backtest mode before using real capital.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) file for details.
