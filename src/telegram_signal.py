"""Telegram bot for BTC Power Signal — tracks the deployed GROWTH A model (production).

Modes:
  --mode daily   full report (Growth A signal + core + forecast + levels).
  --mode watch   hourly: alert on a NEW Growth A signal (entry/exit/flip) or an intraday
                 cut-loss breach; once a day also sends the full report. State persisted
                 in ../state.json so an alert fires only on a transition (no spam).
  --selftest     verify the deployed token (getMe) AND send a one-off test message.
Entry alerts always include the cut-loss price. Single source of truth = the CI run
(don't send manual one-offs, or the dashboard and Telegram desync).

Issue-#1 hardening: tg() now prints the full API response / HTTP error, main() runs a
getMe self-check first (so the Actions log shows immediately if the repo secret token is
wrong/rotated), and the token length + last-4 are logged so you can tell which token is live.
"""
import os, json, sys, datetime as dt
import urllib.request, urllib.parse, urllib.error

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


def _strip(t):
    for a in ("<b>", "</b>", "<i>", "</i>"):
        t = t.replace(a, "")
    return t


def tg_selfcheck():
    """Verify the deployed bot token. Logs loudly so a bad/rotated repo secret is obvious in CI."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN"); chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok:
        print("[telegram] SELFCHECK: TELEGRAM_BOT_TOKEN is NOT set in this environment."); return False
    print(f"[telegram] token present (len {len(tok)}, ...{tok[-4:]}) · chat {'set' if chat else 'MISSING'}")
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/getMe", timeout=15) as r:
            b = json.loads(r.read())
        if b.get("ok"):
            print(f"[telegram] SELFCHECK ok — bot @{b['result'].get('username','?')}"); return True
        print("[telegram] SELFCHECK NOT-OK:", b); return False
    except urllib.error.HTTPError as e:
        print(f"[telegram] SELFCHECK FAILED — HTTP {e.code}: {e.read().decode('utf-8','ignore')} (token likely wrong/rotated)"); return False
    except Exception as e:
        print("[telegram] SELFCHECK FAILED:", repr(e)); return False


def tg(text):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN"); chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("[telegram] NO CREDS — message would be:\n" + _strip(text)); return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://api.telegram.org/bot{tok}/sendMessage", data=data), timeout=20) as r:
            b = json.loads(r.read()); ok = b.get("ok", False)
            if ok:
                print("[telegram] SENT ok · message_id", b.get("result", {}).get("message_id"))
            else:
                print("[telegram] sendMessage NOT-OK:", json.dumps(b))
            return ok
    except urllib.error.HTTPError as e:
        print(f"[telegram] SEND FAILED — HTTP {e.code}: {e.read().decode('utf-8','ignore')}"); return False
    except Exception as e:
        print("[telegram] SEND FAILED:", repr(e)); return False


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


def _model(d):
    return d.get("model_growth") or d.get("model_apex") or d["model_8b"]


def daily_report(d, url):
    C = d["live"]; B = _model(d); F = d["forecast"]; lv = d["levels"]
    head = d["scenarios"].get("Growth A @50bp", d["scenarios"].get("Apex @50bp", {})).get("metrics", {})
    spot = d["scenarios"].get("1x (spot, 50bp)", {}).get("metrics", {})
    de = {"LONG": "🟢", "SHORT": "🔴", "FLAT": "⚪"}.get(B["direction"], "⚪")
    lines = [f"<b>⚡ BTC POWER SIGNAL — {d['as_of']}</b>",
             f"Price <b>${d['price']:,.0f}</b> · RSI {d['rsi']}",
             f"{de} <b>Growth A: {B['action']}</b>", "",
             "<b>Growth A model · 5× vol-targeted</b>",
             f"• Market {B['regime']} · engines {', '.join(B['engines']) or '—'} · confidence {B['confidence']}"]
    if B.get("cutloss"):
        liqs = f" · liquidation ${B['liquidation']:,.0f}" if B.get("liquidation") else ""
        lines.append(f"• Effective {B.get('exposure_mult', 0):.1f}× · margin {B['margin_pct']:.0f}% · 🛑 cut-loss ${B['cutloss']:,.0f}{liqs}")
    lines += ["", (f"<b>Core (spot 1×, same way)</b>: {C['action']} · {C['size_pct']:.0f}%"
                   + (f" · cut ${C['cutloss']:,.0f}" if C.get("cutloss") else "")),
              "", f"<b>Forecast</b> {F['bias']} — {F['headline']}",
              f"<b>Levels</b> S20 ${lv['sma20']:,.0f} · S50 ${lv['sma50']:,.0f} · S200 ${lv['sma200']:,.0f}"]
    if head:
        sp = f" · spot 1× ${spot['final']:,.0f}" if spot else ""
        lines.append(f"<b>Growth A backtest</b> $500→${head['final']:,.0f} @50bp · maxDD {head['maxdd']*100:.0f}%{sp}")
    if url:
        lines += ["", f"📱 {url}"]
    lines += ["", "<i>Growth A uses up to ~5× effective leverage (can be liquidated on a large adverse gap); "
              "deep drawdowns and losing years happen (2018/2022/2025 in backtest). Spot 1× cannot be "
              "liquidated. Hypothetical; not financial advice.</i>"]
    return "\n".join(lines)


def entry_msg(B, price):
    de = "🟢 LONG" if B["direction"] == "LONG" else "🔴 SHORT"
    liqs = f" · liquidation ${B['liquidation']:,.0f}" if B.get("liquidation") else ""
    return (f"<b>⚡ BTC POWER — ENTER {de} (Growth A)</b>\n"
            f"Price <b>${price:,.0f}</b> · {B['regime']} · engines {', '.join(B['engines']) or '—'}\n"
            f"Confidence {B['confidence']} · effective {B.get('exposure_mult', 0):.1f}× · margin {B['margin_pct']:.0f}%\n"
            f"🛑 <b>Cut-loss ${B['cutloss']:,.0f}</b> (−15%){liqs}\n"
            f"<i>Place a resting stop at the cut-loss to cap the downside.</i>")


def exit_msg(s, price, reason):
    d = s["direction"]; pnl = (price / s["entry"] - 1) * (1 if d == "LONG" else -1) if s.get("entry") else 0
    return (f"<b>⚡ BTC POWER — EXIT {d} (Growth A)</b> {'🟢' if pnl >= 0 else '🔴'}\n"
            f"Out ${price:,.0f}" + (f" (in ${s['entry']:,.0f}) · <b>{pnl*100:+.1f}%</b>" if s.get('entry') else "")
            + f"\nReason: {reason}. Now FLAT — wait for the next Growth A signal.")


def main():
    load_env()
    mode = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "daily"
    d = json.load(open(os.path.join(OUT, "results_live.json")))
    url = os.environ.get("DASHBOARD_URL", "")
    B = _model(d)

    if "--selftest" in sys.argv:
        ok = tg_selfcheck()
        tg(f"<b>⚡ BTC POWER — selftest</b>\nGrowth A: {B['action']} · as of {d['as_of']}. If you see this, the live token works.")
        print("[selftest] token ok:", ok); return

    if mode == "daily" or "--dry" in sys.argv:
        msg = daily_report(d, url)
        if "--dry" in sys.argv:
            print(msg); return
        tg_selfcheck(); tg(msg); return

    # ---- watch mode (tracks the Growth A model) ----
    tg_selfcheck()
    s = load_state(); today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    price = live_price(d["price"]); cur = B["direction"]
    # 1) intraday cut-loss breach on an open position
    if s["direction"] in ("LONG", "SHORT") and s.get("cutloss"):
        hit = (price <= s["cutloss"]) if s["direction"] == "LONG" else (price >= s["cutloss"])
        if hit:
            tg(exit_msg(s, s["cutloss"], "cut-loss hit"))
            s = {"direction": "FLAT", "entry": None, "cutloss": None, "last_report_date": s["last_report_date"]}
    # 2) Growth A signal change (entry / exit / flip)
    if cur != s["direction"]:
        if s["direction"] in ("LONG", "SHORT"):
            tg(exit_msg(s, price, "Growth A signal flipped to " + cur))
        if cur in ("LONG", "SHORT"):
            tg(entry_msg(B, price))
            s.update(direction=cur, entry=price, cutloss=B["cutloss"])
        else:
            s.update(direction="FLAT", entry=None, cutloss=None)
    # 3) once-a-day full report
    if s.get("last_report_date") != today:
        tg(daily_report(d, url)); s["last_report_date"] = today
    json.dump(s, open(STATE, "w"), indent=2)
    print("[watch] Growth A:", cur, "| state:", s)


if __name__ == "__main__":
    main()
