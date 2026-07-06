#!/usr/bin/env bash
# BTC Power - 24/7 cloud runner (Oracle Cloud VM / any Linux). Scheduled hourly via cron.
# Refresh data -> recompute Max B -> reconcile Binance account -> Telegram alert.
# Secrets come from the git-ignored .env next to this script. Never commit .env.
cd "$(dirname "$0")" || exit 1
export STATE_FILE="../state_local.json"     # local-only position state (no clash with CI's state.json)
export ORDER_TYPE="MARKET"                   # reliable fills so the position tracks the model
export PYTHONIOENCODING="utf-8"
PY="${BTC_PY:-python3}"                       # set BTC_PY to a venv python if you use one
mkdir -p logs
{
  echo "[$(date -u '+%Y-%m-%d %H:%M:%S') UTC] === cloud runner start ==="
  "$PY" src/fetch_data.py
  "$PY" src/growth_engine.py
  "$PY" src/binance_trader.py
  "$PY" src/telegram_signal.py --mode watch
  echo "[$(date -u '+%Y-%m-%d %H:%M:%S') UTC] === done ==="
} >> logs/cloud_runner.log 2>&1
