#!/bin/bash
# start_all.sh — Start all XAU Bot services (survives SSH session close)
cd /home/botuser/xau_bot
mkdir -p logs

# Start virtual display
pkill Xvfb 2>/dev/null; sleep 1
nohup Xvfb :99 -screen 0 1024x768x16 > logs/xvfb.log 2>&1 &
sleep 2
export DISPLAY=:99

# Start MT5
export WINEPREFIX=~/.wine-mt4
export WINEARCH=win64
export WINEDEBUG=-all
pkill -f terminal64.exe 2>/dev/null
nohup wine "/home/botuser/.wine-mt4/drive_c/Program Files/MetaTrader 5/terminal64.exe" > logs/mt5.log 2>&1 &
echo "MT5 started: $!"
sleep 12

# Start VNC (for MT5 access)
pkill x11vnc 2>/dev/null; pkill websockify 2>/dev/null; sleep 1
nohup x11vnc -display :99 -nopw -rfbport 5900 -forever -quiet > logs/vnc.log 2>&1 &
nohup websockify --web=/usr/share/novnc/ 6080 localhost:5900 > logs/novnc.log 2>&1 &
echo "VNC started on :6080"

# Start API backend
cd /home/botuser/xau_bot/backend
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8443 \
  --ssl-keyfile /etc/letsencrypt/live/xaubot.aswaqalseyouh.ae/privkey.pem \
  --ssl-certfile /etc/letsencrypt/live/xaubot.aswaqalseyouh.ae/fullchain.pem \
  --workers 1 --log-level info \
  > /home/botuser/xau_bot/logs/api.log 2>&1 &
echo "API started: $!"

# Start Streamlit UI
cd /home/botuser/xau_bot
nohup .venv/bin/streamlit run ui/app.py \
  --server.port 8502 --server.address 0.0.0.0 --server.headless true \
  > logs/ui.log 2>&1 &
echo "Streamlit started: $!"

# Start trading bot
nohup .venv/bin/python main.py --mode live \
  > logs/xau_bot.log 2>&1 &
echo "Bot started: $!"

echo ""
echo "All services started. MT5 needs ~30s to fully load."
echo "Then open VNC: http://159.89.110.11:6080/vnc.html"
echo "And attach XAU_Bridge EA to XAUUSD chart if needed."
