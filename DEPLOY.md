# Deploy — daily Telegram signal + iPhone dashboard (GitHub Pages + Actions)

This repo runs itself once a day in GitHub Actions: it refreshes Binance data, generates
the signal + forecast, sends a Telegram message to your bot, and publishes the mobile
dashboard to a public URL you open on your iPhone (and "Add to Home Screen" → opens like an app).

## 1. Create the Telegram bot (2 min)
1. In Telegram, message **@BotFather** → `/newbot` → follow prompts → copy the **bot token**.
2. Message your new bot once (say "hi") so it can message you back.
3. Message **@userinfobot** → it replies with your numeric **chat id**.

## 2. Put the code on GitHub
```bash
cd "btc_signal"
git init && git add -A && git commit -m "BTC daily signal"
git branch -M main
# create an empty repo named btc-signal on github.com, then:
git remote add origin https://github.com/<YOUR_USERNAME>/btc-signal.git
git push -u origin main
```

## 3. Add secrets + enable Pages (in the GitHub repo UI)
- **Settings → Secrets and variables → Actions → New repository secret**:
  - `TELEGRAM_BOT_TOKEN` = your bot token
  - `TELEGRAM_CHAT_ID` = your chat id
- **Variables** tab → New variable: `DASHBOARD_URL` = `https://<YOUR_USERNAME>.github.io/btc-signal/`
- **Settings → Pages → Build and deployment → Source: GitHub Actions**.

## 4. Run it
- **Actions tab → "BTC Daily Signal" → Run workflow** (manual test).
- You should get a Telegram message, and the dashboard goes live at
  `https://<YOUR_USERNAME>.github.io/btc-signal/`.
- After that it runs automatically every day at **01:05 UTC** (just after the daily close).
- On iPhone: open the URL in Safari → Share → **Add to Home Screen** → it launches full-screen like an app.

## Local test (optional)
```bash
cd src
python fetch_data.py && python production_engine.py && python build_mobile_dashboard.py
python telegram_signal.py --dry        # prints the message
cp ../.env.example ../.env             # fill in token/chat id, then:
python telegram_signal.py              # actually sends
```

## Notes
- The daily live signal only needs **daily** data (fetched fresh each run) — the 4.6M-row
  1-minute archive is git-ignored and only used for local backtesting/fidelity checks.
- The dashboard's backtest curves are recomputed each run from daily + the bundled
  CoinGecko history (`data/excel_indicators.csv`).
