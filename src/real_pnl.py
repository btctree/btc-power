"""Real account P&L for the dashboard — READ-ONLY.

Pulls actual BTCUSDT margin fills (bot + manual) and the account snapshot, reconstructs the
current open position (average entry from real fills, real fees) and recent closed round trips,
and writes out/real_pnl.json for build_live_dashboard.py to embed.

Honesty rules:
  * Anchored to reality: reconstruction starts from (current net - sum of fill deltas), so the
    walk always ends exactly at the account's live position even if history is truncated.
  * Fees included, converted to USDT (BNB fees valued at the CURRENT BNB price - labeled approx).
  * No estimates otherwise: entry prices and quantities are the exchange's own fill records.

Keys: prefers the READ-ONLY pair BINANCE_RO_KEY/BINANCE_RO_SECRET (safe for CI), falls back to
BINANCE_API_KEY/BINANCE_API_SECRET (the VM). With no keys at all it exits 0 without writing,
and the dashboard renders exactly as before. GET endpoints only - this module cannot trade.
"""
import os, json, time, hmac, hashlib, urllib.parse, urllib.request

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "out", "real_pnl.json")
BASE = "https://api.binance.com"
DUST = 1.5e-4        # |net| below this (~$10) counts as flat between round trips — well under any
                     # real position (min ~0.003 BTC) but above repay/fee residuals (~0.00005)
DAYS = 60


def load_env():
    p = os.path.join(HERE, "..", ".env")
    if os.path.exists(p):
        for ln in open(p):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


def _get(path, params=None):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read())


def _signed(key, sec, path, params):
    params = dict(params or {})
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 10000
    qs = urllib.parse.urlencode(params)
    sig = hmac.new(sec.encode(), qs.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(f"{BASE}{path}?{qs}&signature={sig}",
                                 headers={"X-MBX-APIKEY": key})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def fee_usdt(t, bnb_px):
    fee, asset = float(t["commission"]), t["commissionAsset"]
    if asset == "USDT":
        return fee
    if asset == "BTC":
        return fee * float(t["price"])
    if asset == "BNB":
        return fee * bnb_px          # approximation: current BNB price, not fill-time
    return 0.0


def main():
    load_env()
    key = os.environ.get("BINANCE_RO_KEY") or os.environ.get("BINANCE_API_KEY", "")
    sec = os.environ.get("BINANCE_RO_SECRET") or os.environ.get("BINANCE_API_SECRET", "")
    if not key or not sec:
        print("[real_pnl] no API key available — skipping (dashboard shows model view only).")
        return

    px = float(_get("/api/v3/ticker/price", {"symbol": "BTCUSDT"})["price"])
    try:
        bnb_px = float(_get("/api/v3/ticker/price", {"symbol": "BNBUSDT"})["price"])
    except Exception:
        bnb_px = 0.0

    acct = _signed(key, sec, "/sapi/v1/margin/account", {})
    assets = {x["asset"]: x for x in acct["userAssets"]}
    btc_net = float(assets.get("BTC", {}).get("netAsset", 0))
    usdt_net = float(assets.get("USDT", {}).get("netAsset", 0))
    equity = usdt_net + btc_net * px

    start = int(time.time() * 1000) - DAYS * 86_400_000
    fills = _signed(key, sec, "/sapi/v1/margin/myTrades",
                    {"symbol": "BTCUSDT", "startTime": start})
    fills.sort(key=lambda t: t["time"])

    # anchor: walk MUST end at the live net position
    net = btc_net - sum((1 if t["isBuyer"] else -1) * float(t["qty"]) for t in fills)
    trips, cur = [], None
    for t in fills:
        q = (1 if t["isBuyer"] else -1) * float(t["qty"])
        p = float(t["price"]); f = fee_usdt(t, bnb_px)
        if cur is None and abs(net) <= DUST and abs(net + q) > DUST:
            cur = dict(opened=t["time"], side="LONG" if q > 0 else "SHORT",
                       cash=0.0, fees=0.0, max_qty=0.0, open_qty=0.0, open_cost=0.0)
        net += q
        if cur is not None:
            cur["cash"] -= q * p          # buys spend cash, sells receive
            cur["fees"] += f
            cur["max_qty"] = max(cur["max_qty"], abs(net))
            same_side = (q > 0) == (cur["side"] == "LONG")
            if same_side:                  # opening/adding: track weighted entry
                cur["open_qty"] += abs(q); cur["open_cost"] += abs(q) * p
            if abs(net) <= DUST:           # round trip closed
                cur.update(closed=t["time"], realized=cur["cash"] - net * p - cur["fees"])
                trips.append(cur); cur = None

    def iso(ms):
        return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ms / 1000)) + " UTC"

    open_pos = None
    if cur is not None and abs(net) > DUST:
        avg = cur["open_cost"] / cur["open_qty"] if cur["open_qty"] else 0.0
        unreal = (px - avg) * net - cur["fees"]     # signed net: works for long and short
        open_pos = dict(side=cur["side"], qty=round(abs(net), 6), avg_entry=round(avg, 2),
                        opened=iso(cur["opened"]), fees_usdt=round(cur["fees"], 2),
                        unrealized_usd=round(unreal, 2),
                        unrealized_pct_equity=round(unreal / equity * 100, 2) if equity else None)

    out = dict(
        generated=iso(int(time.time() * 1000)), price=px, equity_usdt=round(equity, 2),
        margin_level=float(acct.get("marginLevel", 999)),
        bnb_fee_note="BNB-paid fees valued at current BNB price (approx.)" if bnb_px else "",
        open=open_pos,
        recent_closed=[dict(side=c["side"], opened=iso(c["opened"]), closed=iso(c["closed"]),
                            max_qty=round(c["max_qty"], 6), fees_usdt=round(c["fees"], 2),
                            realized_usd=round(c["realized"], 2)) for c in trips[-10:]][::-1],
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, OUT)
    o = out["open"]
    print(f"[real_pnl] wrote {OUT} | open: " +
          (f"{o['side']} {o['qty']} @ {o['avg_entry']} unreal ${o['unrealized_usd']}" if o else "flat") +
          f" | {len(trips)} closed trips")


if __name__ == "__main__":
    # NEVER break the pipeline: this module is cosmetic (dashboard P&L). Any failure — geo-blocked
    # host (HTTP 451 on api.binance.com from US CI runners), bad key, network — must leave the build
    # running and the dashboard falling back to the model view.
    try:
        main()
    except Exception as e:
        msg = str(e)
        if "451" in msg:
            msg += "  (api.binance.com is geo-blocked from this host — account data needs a machine " \
                   "in a permitted region, e.g. the VM. Public market data uses data-api.binance.vision.)"
        print(f"[real_pnl] SKIPPED — {msg}")
