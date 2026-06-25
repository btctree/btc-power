"""Telegram bot for BTC Power Signal — tracks the deployed 8B model.

Modes:
  --mode daily   full report (8B signal + core + forecast + levels).
  --mode watch   hourly: alert on a NEW 8B signal (entry/exit/flip) or an intraday
                 cut-loss breach; once a day also sends the full report. State persisted
                 in ../state.json so an alert fires only on a transition (no spam).
Entry alerts always include the cut-loss price. Single source of truth = the CI run
(don't send manual one-offs, or the dashboard and Telegram desync).
"""
import os, json, sys, datetime as dt
import urllib.request, urllib.parse

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "out")
STATE = os.path.join(HERE, "..", "state.json")


def load_env():
    p = os.path.join(HERE, "..", ".env")
    if os.path.exists(p):
        for ln in open(p):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


def tg(text):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN"); chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("[telegram] no creds — message:\n" + text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data), timeout=20) as r:
            ok = json.loads(r.read()).get("ok", False); print("[telegram]", "sent" if ok else "not-ok"); return ok
    except Exception as e:
        print("[telegram] failed:", e); return False


def live_price(fallback):
    try:
        with urllib.request.urlopen("https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT", timeout=15) as r:
            return float(json.loads(r.read())["price"])
    except Exception:
        return fallback


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE))
        except Exception:
            pass
    return {"direction": "FLAT", "entry": None, "cutloss": None, "last_report_date": None}


def daily_report(d, url):
    C = d["live"]; B = d["model_8b"]; F = d["forecast"]; lv = d["levels"]; sp = d["scenarios"]["Core 1x"]["metrics"]
    de = {"LONG": "🟢", "SHORT": "🔴", "FLAT": "⚪"}.get(B["direction"], "⚪")
    lines = [f"<b>⚡ BTC POWER SIGNAL — {d['as_of']}</b>",
             f"Price <b>${d['price']:,.0f}</b> · RSI {d['rsi']}",
             f"{de} <b>8B (5×): {B['action']}</b>", "",
             "<b>8B model · 5× leverage</b>",
             f"• Market {B['regime']} · engines {', '.join(B['engines']) or '—'} · confidence {B['confidence']}"]
    if B["cutloss"]:
        lines.append(f"• Margin {B['margin_pct']:.0f}% · 🛑 cut-loss ${B['cutloss']:,.0f} · liquidation ${B['liquidation']:,.0f}")
    lines += ["", (f"<b>Core (spot 1×, same way)</b>: {C['action']} · {C['size_pct']:.0f}%"
                   + (f" · cut ${C['cutloss']:,.0f}" if C["cutloss"] else "")),
              "", f"<b>Forecast</b> {F['bias']} — {F['headline']}",
              f"<b>Levels</b> S20 ${lv['sma20']:,.0f} · S50 ${lv['sma50']:,.0f} · S200 ${lv['sma200']:,.0f}",
              f"<b>Core 1× backtest</b> $500→${sp['final']:,.0f} · maxDD {sp['maxdd']*100:.0f}%"]
    if url:
        lines += ["", f"📱 {url}"]
    lines += ["", "<i>8B = 5× leverage (can be liquidated on a >20% gap); spot 1× cannot. Hypothetical; not advice.</i>"]
    return "\n".join(lines)


def entry_msg(B, price):
    de = "🟢 LONG" if B["direction"] == "LONG" else "🔴 SHORT"
    return (f"<b>⚡ BTC POWER — ENTER {de} (8B · 5×)</b>\n"
            f"Price <b>${price:,.0f}</b> · {B['regime']} · engines {', '.join(B['engines']) or '—'}\n"
            f"Confidence {B['confidence']} · margin {B['margin_pct']:.0f}%\n"
            f"🛑 <b>Pre-set cut-loss ${B['cutloss']:,.0f}</b> (−15%) · liquidation ${B['liquidation']:,.0f} (−20%)\n"
            f"<i>Place the resting stop at the cut-loss to avoid the −20% liquidation.</i>")


def exit_msg(s, price, reason):
    d = s["direction"]; pnl = (price / s["entry"] - 1) * (1 if d == "LONG" else -1) if s.get("entry") else 0
    return (f"<b>⚡ BTC POWER — EXIT {d} (8B)</b> {'🟢' if pnl >= 0 else '🔴'}\n"
            f"Out ${price:,.0f}" + (f" (in ${s['entry']:,.0f}) · <b>{pnl*100:+.1f}%</b>" if s.get('entry') else "")
            + f"\nReason: {reason}. Now FLAT — wait for the next 8B signal.")


def main():
    load_env()
    mode = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "daily"
    d = json.load(open(os.path.join(OUT, "results_live.json")))
    url = os.environ.get("DASHBOARD_URL", "")
    B = d["model_8b"]
    if mode == "daily" or "--dry" in sys.argv:
        msg = daily_report(d, url)
        if "--dry" in sys.argv:
            print(msg); return
        tg(msg); return

    # ---- watch mode (tracks the 8B model) ----
    s = load_state(); today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    price = live_price(d["price"]); cur = B["direction"]
    # 1) intraday cut-loss breach on an open position
    if s["direction"] in ("LONG", "SHORT") and s.get("cutloss"):
        hit = (price <= s["cutloss"]) if s["direction"] == "LONG" else (price >= s["cutloss"])
        if hit:
            tg(exit_msg(s, s["cutloss"], "cut-loss hit"))
            s = {"direction": "FLAT", "entry": None, "cutloss": None, "last_report_date": s["last_report_date"]}
    # 2) 8B signal change (entry / exit / flip)
    if cur != s["direction"]:
        if s["direction"] in ("LONG", "SHORT"):
            tg(exit_msg(s, price, "8B signal flipped to " + cur))
        if cur in ("LONG", "SHORT"):
            tg(entry_msg(B, price))
            s.update(direction=cur, entry=price, cutloss=B["cutloss"])
        else:
            s.update(direction="FLAT", entry=None, cutloss=None)
    # 3) once-a-day full report
    if s.get("last_report_date") != today:
        tg(daily_report(d, url)); s["last_report_date"] = today
    json.dump(s, open(STATE, "w"), indent=2)
    print("[watch] 8B:", cur, "| state:", s)


if __name__ == "__main__":
    main()
