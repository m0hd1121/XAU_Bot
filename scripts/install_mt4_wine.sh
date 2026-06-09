#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install_mt4_wine.sh
# Installs Wine + MT4 + DWX Connect on Ubuntu 24.04 VPS (headless)
#
# Usage:
#   1. Download your broker's MT4 installer first:
#      wget -O ~/mt4setup.exe "https://download.mql5.com/cdn/web/your-broker/mt4/mt4setup.exe"
#      (Get the real URL from your broker's Download page)
#
#   2. Run this script:
#      bash scripts/install_mt4_wine.sh
#
#   3. After install, open MT4, log in to your demo account, attach
#      DWX_Server EA to a XAUUSD chart, and enable AutoTrading.
# ─────────────────────────────────────────────────────────────────────────────
set -e

WINE_PREFIX="$HOME/.wine-mt4"
MT4_SETUP="$HOME/mt4setup.exe"
DWX_EA="$HOME/DWX_Server.ex4"
DISPLAY_NUM=":99"

echo "==> XAU Bot — MT4 + Wine Setup"
echo "    Wine prefix : $WINE_PREFIX"
echo "    Display     : $DISPLAY_NUM"
echo ""

# ── Step 1: Swap ──────────────────────────────────────────────────────────────
if ! swapon --show | grep -q swapfile; then
    echo "==> Adding 2GB swap…"
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "    Swap added."
else
    echo "==> Swap already configured — skipping."
fi

# ── Step 2: Wine repository ───────────────────────────────────────────────────
echo ""
echo "==> Installing Wine (WineHQ stable)…"
sudo dpkg --add-architecture i386
sudo mkdir -pm755 /etc/apt/keyrings
sudo wget -qO /etc/apt/keyrings/winehq-archive.key \
    https://dl.winehq.org/wine-builds/winehq.key
# Ubuntu 24.04 = noble
sudo wget -qNP /etc/apt/sources.list.d/ \
    https://dl.winehq.org/wine-builds/ubuntu/dists/noble/winehq-noble.sources
sudo apt-get update -qq
sudo apt-get install --install-recommends winehq-stable -y -qq
echo "    Wine $(wine --version) installed."

# ── Step 3: Virtual display ───────────────────────────────────────────────────
echo ""
echo "==> Installing Xvfb (virtual display)…"
sudo apt-get install -y -qq xvfb x11-utils
echo "    Xvfb installed."

# ── Step 4: Start virtual display ────────────────────────────────────────────
echo ""
echo "==> Starting virtual display on $DISPLAY_NUM…"
pkill -f "Xvfb $DISPLAY_NUM" 2>/dev/null || true
Xvfb "$DISPLAY_NUM" -screen 0 1024x768x16 &
sleep 2
export DISPLAY="$DISPLAY_NUM"
echo "    Display started (PID $!)."

# ── Step 5: Wine prefix setup ─────────────────────────────────────────────────
echo ""
echo "==> Configuring Wine prefix (win32)…"
export WINEPREFIX="$WINE_PREFIX"
export WINEARCH="win32"
export WINEDEBUG="-all"
# Initialise silently
wineboot --init 2>/dev/null
sleep 3
echo "    Wine prefix ready at $WINE_PREFIX"

# ── Step 6: Install MT4 ───────────────────────────────────────────────────────
echo ""
if [ ! -f "$MT4_SETUP" ]; then
    echo "==> ERROR: MT4 installer not found at $MT4_SETUP"
    echo "    Download it from your broker's website and save it to ~/mt4setup.exe"
    echo "    Then re-run this script."
    exit 1
fi

echo "==> Installing MT4 (this takes ~2 minutes)…"
WINEDEBUG="-all" wine "$MT4_SETUP" /S 2>/dev/null
sleep 10
echo "    MT4 installation complete."

# ── Step 7: Find MT4 install path ────────────────────────────────────────────
echo ""
echo "==> Locating MT4 installation…"
MT4_DIR=$(find "$WINE_PREFIX/drive_c/Program Files (x86)" -maxdepth 2 \
    -name "terminal.exe" 2>/dev/null | head -1 | xargs -I{} dirname {})

if [ -z "$MT4_DIR" ]; then
    MT4_DIR=$(find "$WINE_PREFIX/drive_c" -maxdepth 4 \
        -name "terminal.exe" 2>/dev/null | head -1 | xargs -I{} dirname {})
fi

if [ -z "$MT4_DIR" ]; then
    echo "    WARNING: Could not auto-detect MT4 directory."
    echo "    Check manually: find $WINE_PREFIX -name terminal.exe"
    MT4_DIR="$WINE_PREFIX/drive_c/Program Files (x86)/MetaTrader 4"
fi

echo "    MT4 directory: $MT4_DIR"
MT4_FILES="$MT4_DIR/MQL4/Files"
mkdir -p "$MT4_FILES"
mkdir -p "$MT4_DIR/MQL4/Experts"

# ── Step 8: Download DWX Connect EA ──────────────────────────────────────────
echo ""
echo "==> Downloading DWX Connect EA…"
wget -qO "$DWX_EA" \
    https://github.com/darwinex/dwxconnect/raw/master/mql4/experts/DWX_Server.ex4
cp "$DWX_EA" "$MT4_DIR/MQL4/Experts/DWX_Server.ex4"
echo "    DWX_Server.ex4 copied to Experts folder."

# ── Step 9: Create autostart script ──────────────────────────────────────────
echo ""
echo "==> Creating MT4 start script at ~/start_mt4.sh…"
cat > "$HOME/start_mt4.sh" << STARTSCRIPT
#!/bin/bash
# Start MT4 under Wine headlessly
export DISPLAY=$DISPLAY_NUM
export WINEPREFIX=$WINE_PREFIX
export WINEARCH=win32
export WINEDEBUG=-all

# Start virtual display if not running
if ! pgrep -x Xvfb > /dev/null; then
    Xvfb $DISPLAY_NUM -screen 0 1024x768x16 &
    sleep 2
fi

# Start MT4
nohup wine "$MT4_DIR/terminal.exe" /portable > ~/logs/mt4.log 2>&1 &
echo "MT4 started: \$!"
STARTSCRIPT
chmod +x "$HOME/start_mt4.sh"
echo "    Start script created."

# ── Step 10: Create systemd service ──────────────────────────────────────────
echo ""
echo "==> Creating systemd service for MT4 autostart…"
sudo tee /etc/systemd/system/mt4.service > /dev/null << SYSTEMD
[Unit]
Description=MetaTrader 4 under Wine
After=network.target

[Service]
Type=forking
User=$USER
Environment=DISPLAY=$DISPLAY_NUM
Environment=WINEPREFIX=$WINE_PREFIX
Environment=WINEARCH=win32
Environment=WINEDEBUG=-all
ExecStartPre=/usr/bin/Xvfb $DISPLAY_NUM -screen 0 1024x768x16
ExecStart=/usr/bin/wine "$MT4_DIR/terminal.exe" /portable
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
SYSTEMD

sudo systemctl daemon-reload
echo "    Service created. To enable: sudo systemctl enable mt4 && sudo systemctl start mt4"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  MT4 + Wine setup complete!                                  ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  MT4 directory : $MT4_DIR"
echo "║  Files path    : $MT4_FILES"
echo "║  DWX EA        : copied to Experts/"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  NEXT STEPS:                                                 ║"
echo "║  1. Start MT4:  bash ~/start_mt4.sh                         ║"
echo "║  2. Log in to your OpoFinance demo account in MT4           ║"
echo "║  3. Open XAUUSD chart → Insert → Experts → DWX_Server      ║"
echo "║  4. Enable AutoTrading (F7 or toolbar button)               ║"
echo "║  5. In bot UI → Broker → DWX Connect → Test Connection      ║"
echo "║                                                              ║"
echo "║  Files path to paste in UI:                                  ║"
echo "║  $MT4_FILES"
echo "╚══════════════════════════════════════════════════════════════╝"
