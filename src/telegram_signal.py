"""Telegram daily signal bot. Reads out/results_production.json and sends a formatted
daily update (signal + market forecast + performance + disclaimer) to your bot.

Config (env vars or btc_signal/.env):
  TELEGRAM_BOT_TOKEN   from @BotFather
  TELEGRAM_CHAT_ID     your chat/channel id (message @userinfobot to get it)
  DASHBOARD_URL        (optional) link shown in the message

Run:  python telegram_signal.py            (sends)
      python telegram_signal.py --dry       (prints, does not send)
Degrades gracefully: with no token it just prints the message.
"""
import os, json, sys
import urllib.request
import urllib.parse

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "out")


def load_env():
    p = os.path.join(HERE, "..", ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def fmt(d):
    L = d["live"]; F = d["forecast"]; lv = d["levels"]; P = d["production"]
    dir_emoji = {"LONG": "🟢", "SHORT": "🔴", "FLAT": "⚪"}.get(L["direction"], "⚪")
    bias_emoji = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "➖"}.get(F["bias"], "➖")
    core = P.get("CORE_1x_2017", {})
    url = os.environ.get("DASHBOARD_URL", "")
    lines = [
        f"<b>₿ BTC Daily Signal — {d['as_of']}</b>",
        f"Price <b>${d['price']:,.0f}</b>  ·  RSI {L['rsi']}",
        f"{dir_emoji} <b>{L['action']}</b>",
        "",
        f"<b>Setup</b>",
        f"• Market: {L['regime']}  ·  Strategy: {L['active_strategy']}",
        f"• Confidence: {L['confidence']} ({L['confidence_score']})  ·  Size: {L['size_pct_equity']}% of equity",
        f"• Margin: {L['margin_note']}",
        f"• Stop: {('$'+format(L['trailing_stop'],',.0f')) if L['trailing_stop'] else '—'}  ·  TP: ride trend (no fixed target)",
        "",
        f"<b>Forecast</b> {bias_emoji} {F['bias']}",
        f"• {F['note']}",
        f"• Arms LONG &gt; ${F['arms_long_above']:,.0f}  ·  arms SHORT &lt; ${F['arms_short_below']:,.0f}",
        "",
        f"<b>Levels</b>  S20 ${lv['sma20']:,.0f} · S50 ${lv['sma50']:,.0f} · S200 ${lv['sma200']:,.0f} · "
        f"BB ${lv['bb_lower']:,.0f}–${lv['bb_upper']:,.0f} · 20d ${lv['swing_low_20d']:,.0f}–${lv['swing_high_20d']:,.0f}",
        "",
        f"<b>Strategy (backtest, real fills)</b>",
        f"• CORE 1× spot: $500→${core.get('final',0):,.0f} · Sharpe {core.get('sharpe','—')} · maxDD {core.get('maxdd',0)*100:.0f}% · 0 liq",
    ]
    if url:
        lines += ["", f"📱 Dashboard: {url}"]
    lines += ["", "<i>Hypothetical backtest; daily-close signal, spot, no leverage. Not financial advice.</i>"]
    return "\n".join(lines)


def send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[telegram] no TELEGRAM_BOT_TOKEN/CHAT_ID set — printing message instead:\n")
        print(text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
        return False
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ok = json.loads(r.read()).get("ok", False)
            print("[telegram] sent OK" if ok else "[telegram] API returned not-ok")
            return ok
    except Exception as e:
        print(f"[telegram] send failed: {e}")
        return False


def main():
    load_env()
    d = json.load(open(os.path.join(OUT, "results_production.json")))
    text = fmt(d)
    if "--dry" in sys.argv:
        print(text)
        return
    send(text)


if __name__ == "__main__":
    main()
