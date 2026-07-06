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
    """Cross-margin account -> (equity_usdt, btc_net, usdt_net). btc_net = holding - borrowed."""
    a = _signed(c, "GET", "/sapi/v1/margin/account", {})
    assets = {x["asset"]: x for x in a["userAssets"]}
    btc = assets.get("BTC", {}); usdt = assets.get("USDT", {})
    btc_net = float(btc.get("netAsset", 0)); usdt_net = float(usdt.get("netAsset", 0))
    px = price(c)
    equity_usdt = usdt_net + btc_net * px                       # 2-asset BTCUSDT approximation
    return equity_usdt, btc_net, usdt_net, px


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
    side_effect = "MARGIN_BUY" if plan["side"] == "BUY" else "AUTO_REPAY"  # borrow to add / repay to reduce
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
    target_exposure = sign * float(g.get("exposure_mult") or 0)
    log(f"model target: {g['action']} (exposure {target_exposure:+.2f}x) as of {d['as_of']}")

    if os.path.exists(os.path.join(ROOT, "STOP")):
        log("KILL-SWITCH present (btc_signal/STOP) — trading frozen, exiting."); return
    if not c["key"] or not c["secret"]:
        log("no BINANCE_API_KEY/SECRET in .env — cannot read account. (dry-run of math only)")
        log(f"[{'TESTNET' if c['testnet'] else 'MAINNET'}] would target {target_exposure:+.2f}x of equity. "
            f"Add keys to .env to enable. Nothing placed."); return

    try:
        step, min_notional = symbol_filters(c)
        equity, btc_net, usdt_net, px = margin_account(c)
    except Exception as e:
        log(f"account/market read FAILED: {e}"); return
    log(f"account [{'TESTNET' if c['testnet'] else 'MAINNET'}]: equity ${equity:,.2f} · BTC net {btc_net:+.6f} "
        f"· USDT net ${usdt_net:,.2f} · price ${px:,.2f}")

    plan = reconcile(target_exposure, equity, btc_net, px, step, min_notional, c)
    log(f"plan: {plan['side']} {plan['qty']:.6f} BTC (~${plan['delta_usd']:,.0f}) "
        f"| current {plan['current_btc']:+.6f} -> target {plan['target_btc']:+.6f} BTC")
    if plan["skip"]:
        log(f"NO ORDER: {plan['reason']}"); return

    if not c["live"]:
        log(f"DRY-RUN (LIVE_TRADING!=1): would {plan['side']} {plan['qty']:.6f} BTC (~${plan['delta_usd']:,.0f}). "
            f"Nothing placed. Set LIVE_TRADING=1 to arm."); return
    if not c["testnet"]:
        log("ARMED ON MAINNET — placing REAL order.")
    resp = place(c, plan, px)
    log(f"ORDER PLACED: id {resp.get('orderId')} status {resp.get('status')} "
        f"clientId {resp.get('clientOrderId')}")


if __name__ == "__main__":
    main()
