#!/bin/bash
cd /home/botuser/xau_bot/backend
exec /home/botuser/xau_bot/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8443
