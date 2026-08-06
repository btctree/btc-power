"""BTC Power — Binance CROSS-MARGIN auto-executor for the live Max B target (Option 3).

WHAT IT DOES
  Reads the model's target exposure from out/results_live.json, reads your REAL Binance cross-margin
  account (equity + current BTC position), computes the exact order needed to make the account match
  the model target (enter / add / reduce / exit / flip), and — only when fully armed — places it.

SAFETY (all ON by default; you disarm deliberately, one gate at a time):
  * DRY-RUN by default: with LIVE_TRADING != "1" it computes + logs + Telegrams the intended order but
    places NOTHING.
  * TESTNET first: BINANCE_TESTNET=1 routes to Binance's spot-margin testnet (fake money).
  * Kill-switch file: if btc_signal/STOP exists, it does nothing (create the file to freeze trading).
  * MAX_ORDER_USD cap: refuses any single order above this notional (default 250).
  * Refuses to run live on mainnet unless LIVE_TRADING=1 AND a key is present AND kill-switch absent.
  * Withdrawals are NEVER called; create the API key with withdrawals DISABLED and IP-restricted.
  * Idempotent client order id (date+action) so a repeated run can't double-place the same action.

KEYS: read from the git-ignored .env (BINANCE_API_KEY / BINANCE_API_SECRET). Never commit them.

This module is intentionally standalone (stdlib only) and does NOT auto-run from CI. It is invoked by
the local runner once the user arms it. Backtest assumptions it honours: acts on the daily-close target,
uses LIMIT orders by default (post-only-ish) to respect the ~50bp cost model, market only if forced.
"""
import os, sys, json, time, hmac, hashlib, urllib.parse, urllib.request, urllib.error, datetime as dt

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "out")
ROOT = os.path.join(HERE, "..")
LOG = os.path.join(ROOT, "logs", "trader.log")


def load_env():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for ln in open(p):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


def log(msg):
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def tg_send(msg):
    """Best-effort Telegram alert. Execution problems must never be silent (2026-07-31 lesson)."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN"); chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": msg}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception:
        pass


# ---------- config ----------
def cfg():
    testnet = os.environ.get("BINANCE_TESTNET", "1") == "1"       # SAFE default: testnet
    return dict(
        key=os.environ.get("BINANCE_API_KEY", ""),
        secret=os.environ.get("BINANCE_API_SECRET", ""),
        testnet=testnet,
        live=os.environ.get("LIVE_TRADING", "0") == "1",          # SAFE default: dry-run
        base=("https://testnet.binance.vision" if testnet else "https://api.binance.com"),
        symbol=os.environ.get("SYMBOL", "BTCUSDT"),
        max_order_usd=float(os.environ.get("MAX_ORDER_USD", "250")),
        min_delta_usd=float(os.environ.get("MIN_DELTA_USD", "20")),  # ignore tiny rebalances
        order_type=os.environ.get("ORDER_TYPE", "LIMIT"),           # LIMIT (cost-friendly) or MARKET
        limit_offset_bp=float(os.environ.get("LIMIT_OFFSET_BP", "5")),
    )


# ---------- REST ----------
def _get(base, path, params=None):
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read())


def server_time_offset(c):
    """ms to add to local time so our timestamp matches Binance's server clock.
    Prevents error -1021 when the laptop's clock drifts (e.g. after waking from sleep)."""
    try:
        srv = int(_get(c["base"], "/api/v3/time")["serverTime"])
        return srv - int(time.time() * 1000)
    except Exception:
        return 0


def _signed(c, method, path, params):
    params = dict(params or {})
    params["timestamp"] = int(time.time() * 1000) + c.get("time_offset", 0)
    params["recvWindow"] = 10000
    qs = urllib.parse.urlencode(params)
    sig = hmac.new(c["secret"].encode(), qs.encode(), hashlib.sha256).hexdigest()
    url = f"{c['base']}{path}?{qs}&signature={sig}"
    req = urllib.request.Request(url, method=method, headers={"X-MBX-APIKEY": c["key"]})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"Binance HTTP {e.code}: {body}")


# ---------- account + market ----------
def symbol_filters(c):
    """LOT_SIZE stepSize + minNotional from public exchangeInfo (no key needed)."""
    info = _get(c["base"], "/api/v3/exchangeInfo", {"symbol": c["symbol"]})
    f = {x["filterType"]: x for x in info["symbols"][0]["filters"]}
    step = float(f["LOT_SIZE"]["stepSize"])
    min_notional = float(f.get("NOTIONAL", f.get("MIN_NOTIONAL", {"minNotional": "0"}))["minNotional"])
    return step, min_notional


def price(c):
    return float(_get(c["base"], "/api/v3/ticker/price", {"symbol": c["symbol"]})["price"])


def margin_account(c):
    """Cross-margin account -> (equity_usdt, btc_net, usdt_net, px, btc_free, usdt_free)."""
    a = _signed(c, "GET", "/sapi/v1/margin/account", {})
    assets = {x["asset"]: x for x in a["userAssets"]}
    btc = assets.get("BTC", {}); usdt = assets.get("USDT", {})
    btc_net = float(btc.get("netAsset", 0)); usdt_net = float(usdt.get("netAsset", 0))
    btc_free = float(btc.get("free", 0)); usdt_free = float(usdt.get("free", 0))
    px = price(c)
    equity_usdt = usdt_net + btc_net * px                       # 2-asset BTCUSDT approximation
    return equity_usdt, btc_net, usdt_net, px, btc_free, usdt_free


def max_borrowable(c, asset):
    """Binance's answer to 'how much of this asset can this account borrow right now'
    (accounts for the 3x/5x cross-margin tier, collateral and per-asset caps).
    Returns None on any error — callers must then fall back to try-and-alert."""
    try:
        r = _signed(c, "GET", "/sapi/v1/margin/maxBorrowable", {"asset": asset})
        return float(r.get("amount", 0))
    except Exception:
        return None


def afford(plan, c, px, step, btc_free, usdt_free):
    """Cap the planned order to what the account can actually execute (2026-08-06 lesson:
    the model wanted a 2.34x short but the account's borrow tier allowed less -> six -3006
    rejections). Sizes down instead of failing; alerts when capped."""
    if plan["skip"]:
        return plan
    if plan["side"] == "SELL":
        if plan["target_btc"] < 0:      # opening/adding a short: sell free BTC + borrow the rest
            mb = max_borrowable(c, "BTC")
            cap = None if mb is None else max(0.0, btc_free) + mb * 0.995
        else:                            # trimming a long: can only sell BTC actually held
            cap = max(0.0, btc_free)
    else:
        eff_px = px * (1 + c["limit_offset_bp"] / 1e4)  # a BUY costs slightly above spot (limit cross/slippage)
        if plan["current_btc"] < 0:      # covering a short (AUTO_REPAY): spend free USDT only
            cap = max(0.0, usdt_free) * 0.999 / eff_px
        else:                            # opening/adding a long: spend free USDT + borrow the rest
            mb = max_borrowable(c, "USDT")
            cap = None if mb is None else (max(0.0, usdt_free) + mb * 0.995) / eff_px
    if cap is None or plan["qty"] <= cap:
        return plan
    capped = abs(round_step(cap, step))
    msg = (f"order capped by available funds/borrow tier: wanted {plan['qty']:.6f} BTC "
           f"(~${plan['qty']*px:,.0f}), account allows {capped:.6f} (~${capped*px:,.0f})")
    log("AFFORDABILITY: " + msg)
    if capped * px < max(5.0, c["min_delta_usd"]):
        plan.update(skip=True, reason=f"affordable size ${capped*px:,.0f} below threshold — no trade")
        _cap_alert_once_daily(msg)       # persists for days while the tier is exhausted: Telegram once/day
        return plan
    tg_send("BTC Power: " + msg)         # an actual reduced order is going out — always alert
    plan.update(qty=capped, delta_usd=capped * px)
    return plan


def _cap_alert_once_daily(msg):
    """The capped-below-threshold state repeats hourly while the borrow tier stays exhausted;
    log every time (afford does), but Telegram at most once per UTC day."""
    try:
        p = os.path.join(ROOT, "logs", ".cap_alert_date")
        today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
        if os.path.exists(p) and open(p).read().strip() == today:
            return
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(today)
    except Exception:
        pass
    tg_send("BTC Power: " + msg + " (daily notice — hourly repeats are logged only)")


# ---------- reconcile ----------
def round_step(qty, step):
    import math
    return math.floor(abs(qty) / step) * step * (1 if qty >= 0 else -1)


def reconcile(target_exposure, equity_usdt, btc_net, px, step, min_notional, c):
    """Return the order plan to move current BTC position to target_exposure * equity (signed)."""
    target_notional = target_exposure * equity_usdt            # signed: + long, - short
    target_btc = target_notional / px
    delta_btc = round_step(target_btc - btc_net, step)
    delta_usd = abs(delta_btc) * px
    side = "BUY" if delta_btc > 0 else "SELL"
    reason = None
    if delta_usd < max(min_notional, c["min_delta_usd"]):
        reason = f"delta ${delta_usd:,.0f} below threshold (min ${max(min_notional, c['min_delta_usd']):,.0f}) — no trade"
    if delta_usd > c["max_order_usd"]:
        reason = f"delta ${delta_usd:,.0f} exceeds MAX_ORDER_USD ${c['max_order_usd']:,.0f} — BLOCKED (raise cap deliberately)"
    return dict(side=side, qty=abs(delta_btc), delta_usd=delta_usd,
                target_btc=target_btc, current_btc=btc_net, target_notional=target_notional,
                skip=(reason is not None), reason=reason)


def place(c, plan, px):
    """Place a cross-margin order with auto borrow/repay. Only reached when armed + not skipped."""
    # Side-effect must follow INTENT, not side: a SELL that takes net position below zero must
    # BORROW the shortfall (MARGIN_BUY); a BUY while net-short is a cover and must REPAY the BTC
    # debt (AUTO_REPAY). Side alone chooses wrong on both flip directions.
    if plan["side"] == "SELL":
        side_effect = "MARGIN_BUY" if plan["target_btc"] < 0 else "AUTO_REPAY"
    else:
        side_effect = "AUTO_REPAY" if plan["current_btc"] < 0 else "MARGIN_BUY"
    coid = "btcpwr-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d") + "-" + plan["side"]
    params = dict(symbol=c["symbol"], side=plan["side"], quantity=f"{plan['qty']:.6f}",
                  sideEffectType=side_effect, newClientOrderId=coid, isIsolated="FALSE")
    if c["order_type"] == "MARKET":
        params["type"] = "MARKET"
    else:
        off = c["limit_offset_bp"] / 1e4
        lp = px * (1 + off) if plan["side"] == "BUY" else px * (1 - off)  # cross the spread slightly
        params.update(type="LIMIT", timeInForce="GTC", price=f"{lp:.2f}")
    return _signed(c, "POST", "/sapi/v1/margin/order", params)


# ---------- main ----------
def main():
    load_env()
    c = cfg()
    c["time_offset"] = server_time_offset(c)   # sync to Binance clock (fixes -1021 after sleep drift)
    d = json.load(open(os.path.join(OUT, "results_live.json")))
    g = d.get("model_growth") or d.get("model_apex") or d["model_8b"]
    sign = 1 if g["direction"] == "LONG" else (-1 if g["direction"] == "SHORT" else 0)
    target_exposure = max(-5.0, min(5.0, sign * float(g.get("exposure_mult") or 0)))  # model cap is 5x
    log(f"model target: {g['action']} (exposure {target_exposure:+.2f}x) as of {d['as_of']}")

    if os.path.exists(os.path.join(ROOT, "STOP")):
        log("KILL-SWITCH present (btc_signal/STOP) — trading frozen, exiting."); return
    try:  # staleness gate: never reconcile real money against an old signal
        age_days = (dt.datetime.now(dt.timezone.utc).date() - dt.date.fromisoformat(str(d["as_of"]))).days
    except Exception:
        age_days = None
    if age_days is None or age_days > 2:
        msg = f"STALE SIGNAL: results_live.json as_of={d.get('as_of')!r} ({age_days} days old) — refusing to trade."
        log(msg); tg_send("BTC Power: " + msg); return
    if not c["key"] or not c["secret"]:
        log("no BINANCE_API_KEY/SECRET in .env — cannot read account. (dry-run of math only)")
        log(f"[{'TESTNET' if c['testnet'] else 'MAINNET'}] would target {target_exposure:+.2f}x of equity. "
            f"Add keys to .env to enable. Nothing placed."); return

    try:
        step, min_notional = symbol_filters(c)
        equity, btc_net, usdt_net, px, btc_free, usdt_free = margin_account(c)
    except Exception as e:
        log(f"account/market read FAILED: {e}")
        tg_send(f"BTC Power: account/market read FAILED — no reconcile this run. {e}"); return
    log(f"account [{'TESTNET' if c['testnet'] else 'MAINNET'}]: equity ${equity:,.2f} · BTC net {btc_net:+.6f} "
        f"· USDT net ${usdt_net:,.2f} · price ${px:,.2f}")

    plan = reconcile(target_exposure, equity, btc_net, px, step, min_notional, c)
    log(f"plan: {plan['side']} {plan['qty']:.6f} BTC (~${plan['delta_usd']:,.0f}) "
        f"| current {plan['current_btc']:+.6f} -> target {plan['target_btc']:+.6f} BTC")
    plan = afford(plan, c, px, step, btc_free, usdt_free)
    if plan["skip"]:
        log(f"NO ORDER: {plan['reason']}")
        if "BLOCKED" in (plan["reason"] or ""):
            tg_send(f"BTC Power: order BLOCKED — {plan['reason']}")
        return

    if not c["live"]:
        log(f"DRY-RUN (LIVE_TRADING!=1): would {plan['side']} {plan['qty']:.6f} BTC (~${plan['delta_usd']:,.0f}). "
            f"Nothing placed. Set LIVE_TRADING=1 to arm."); return
    if not c["testnet"]:
        log("ARMED ON MAINNET — placing REAL order.")
    try:
        resp = place(c, plan, px)
    except Exception as e:  # a rejected order must NEVER die silently (the 19h-short lesson)
        msg = f"ORDER FAILED: {plan['side']} {plan['qty']:.6f} BTC (~${plan['delta_usd']:,.0f}) — {e}"
        log(msg); tg_send("BTC Power EXECUTION FAILURE — " + msg)
        sys.exit(1)
    log(f"ORDER PLACED: id {resp.get('orderId')} status {resp.get('status')} "
        f"clientId {resp.get('clientOrderId')}")
    tg_send(f"BTC Power: {plan['side']} {plan['qty']:.6f} BTC (~${plan['delta_usd']:,.0f}) placed — "
            f"id {resp.get('orderId')} {resp.get('status')}")


if __name__ == "__main__":
    main()
