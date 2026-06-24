"""Telegram bot for BTC Power Signal.

Modes:
  --mode daily   full daily report (signal + forecast + levels + performance).
  --mode watch   hourly watcher: detects ENTRY (in-market) / EXIT (out-market) and
                 intraday trailing-stop hits, sends an alert ONLY on a transition,
                 and once a day also sends the daily report. Uses ../state.json to
                 remember the open position across runs (committed by the workflow).

Entry alerts always include the CUT-LOSS price to pre-set as a resting stop.
Config: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (env or ../.env), DASHBOARD_URL.
"""
import os, json, sys, datetime as dt
import urllib.request, urllib.parse

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "out")
STATE = os.path.join(HERE, "..", "state.json")
TRAIL_L, TRAIL_S = 0.10, 0.07


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
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://api.telegram.org/bot{tok}/sendMessage", data=data), timeout=20) as r:
            ok = json.loads(r.read()).get("ok", False); print("[telegram]", "sent" if ok else "not-ok"); return ok
    except Exception as e:
        print("[telegram] failed:", e); return False


def live_price():
    try:
        u = "https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT"
        with urllib.request.urlopen(u, timeout=15) as r:
            return float(json.loads(r.read())["price"])
    except Exception as e:
        print("[price] fetch failed:", e); return None


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE))
        except Exception:
            pass
    return {"in_position": False, "direction": None, "entry": None, "stop": None,
            "hi": None, "lo": None, "entry_date": None, "last_report_date": None}


def save_state(s):
    json.dump(s, open(STATE, "w"), indent=2)


def flat(prev):
    return {"in_position": False, "direction": None, "entry": None, "stop": None,
            "hi": None, "lo": None, "entry_date": None, "last_report_date": prev.get("last_report_date")}


def daily_report(d, url):
    L = d["live"]; F = d["no_trade_status"]; lv = d["levels"]; sp = d["scenarios"]["Spot 1x"]["metrics"]
    de = {"LONG": "🟢", "SHORT": "🔴", "FLAT": "⚪"}.get(L["direction"], "⚪")
    lines = [f"<b>⚡ BTC POWER SIGNAL — {d['as_of']}</b>",
             f"Price <b>${d['price']:,.0f}</b> · RSI {d['rsi']}",
             f"{de} <b>{L['action']}</b>", "",
             "<b>Setup</b>",
             f"• Market: {L['regime']} · Engine: {L['engine']}",
             f"• Confidence: {L['confidence']} ({L['confidence_score']}) · Size: {L['size_pct']}%",
             f"• Margin: {L['margin']}",
             f"• Cut-loss: {('$'+format(L['cutloss'],',.0f')) if L['cutloss'] else '—'} · TP: ride trend", ""]
    if not d["in_position"]:
        lines += ["<b>No position — next action</b>", f"• {F['next_action']}", ""]
    lines += [f"<b>Levels</b> S20 ${lv['sma20']:,.0f} · S50 ${lv['sma50']:,.0f} · S200 ${lv['sma200']:,.0f} · BB ${lv['bb_lower']:,.0f}-${lv['bb_upper']:,.0f}",
              f"<b>Strategy</b> spot 1x: $500→${sp['final']:,.0f} · maxDD {sp['maxdd']*100:.0f}%"]
    if url:
        lines += ["", f"📱 {url}"]
    lines += ["", "<i>Hypothetical; daily-close signal, spot 1x. Not financial advice.</i>"]
    return "\n".join(lines)


def entry_msg(L, price):
    de = "🟢 LONG" if L["direction"] == "LONG" else "🔴 SHORT"
    return (f"<b>⚡ BTC POWER — ENTER {de}</b>\n"
            f"Price <b>${price:,.0f}</b> · {L['regime']} · engine {L['engine']}\n"
            f"Confidence {L['confidence']} ({L['confidence_score']}) · Size {L['size_pct']}% · spot 1x\n"
            f"🛑 <b>Pre-set cut-loss: ${L['cutloss']:,.0f}</b> ({int(TRAIL_L*100) if L['direction']=='LONG' else int(TRAIL_S*100)}% trailing)\n"
            f"TP: none — ride trend; exit on reversal / regime-change / stop.\n"
            f"<i>Place a resting stop at the cut-loss to fight slippage.</i>")


def exit_msg(s, price, reason):
    d = s["direction"]; pnl = (price / s["entry"] - 1) * (1 if d == "LONG" else -1)
    e = "🟢" if pnl >= 0 else "🔴"
    return (f"<b>⚡ BTC POWER — EXIT {d}</b> {e}\n"
            f"Out ${price:,.0f} (in ${s['entry']:,.0f}) · <b>{pnl*100:+.1f}%</b>\n"
            f"Reason: {reason}. Now FLAT — wait for next signal.")


def main():
    load_env()
    mode = "daily"
    if "--mode" in sys.argv:
        mode = sys.argv[sys.argv.index("--mode") + 1]
    d = json.load(open(os.path.join(OUT, "results_live.json")))
    url = os.environ.get("DASHBOARD_URL", "")
    L = d["live"]
    if mode == "daily" or "--dry" in sys.argv:
        msg = daily_report(d, url)
        if "--dry" in sys.argv:
            print(msg); return
        tg(msg); return

    # ---- watch mode ----
    s = load_state()
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    price = live_price() or d["price"]
    want_long = L["direction"] == "LONG"; want_short = L["direction"] == "SHORT"; want_flat = L["direction"] == "FLAT"

    # 1) exit by intraday trailing stop while in position
    if s["in_position"]:
        if s["direction"] == "LONG":
            s["hi"] = max(s.get("hi") or s["entry"], price); s["stop"] = max(s["stop"], s["hi"] * (1 - TRAIL_L))
            if price <= s["stop"]:
                tg(exit_msg(s, s["stop"], "trailing stop hit")); s = flat(s)
        else:
            s["lo"] = min(s.get("lo") or s["entry"], price); s["stop"] = min(s["stop"], s["lo"] * (1 + TRAIL_S))
            if price >= s["stop"]:
                tg(exit_msg(s, s["stop"], "trailing stop hit")); s = flat(s)

    # 2) daily-signal transitions (entries / signal exits) — based on the closed-bar signal
    if s["in_position"] and (want_flat or (s["direction"] == "LONG" and want_short) or (s["direction"] == "SHORT" and want_long)):
        tg(exit_msg(s, price, "daily signal flipped"))
        s = flat(s)
    if (not s["in_position"]) and (want_long or want_short):
        tg(entry_msg(L, price))
        s.update(in_position=True, direction=L["direction"], entry=price, stop=L["cutloss"],
                 hi=price, lo=price, entry_date=today)

    # 3) once-a-day full report
    if s.get("last_report_date") != today:
        tg(daily_report(d, url)); s["last_report_date"] = today

    save_state(s)
    print("[watch] state:", s)


if __name__ == "__main__":
    main()
