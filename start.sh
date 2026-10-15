#!/bin/bash
# Restart the Ledgerleaf server on port 8787
cd /workspace/stock-app
pkill -f "stock-app/app.py"; sleep 1
nohup .venv/bin/python /workspace/stock-app/app.py > server.log 2>&1 &
sleep 2; curl -s -o /dev/null -w "local: %{http_code}\n" http://localhost:8787/
