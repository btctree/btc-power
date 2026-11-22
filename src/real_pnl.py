"""Real account P&L for the dashboard — READ-ONLY.

Pulls actual BTCUSDT margin fills (bot + manual) and the account snapshot, reconstructs the
current open position (average entry from real fills, real fees) and closed round trips, and
writes out/real_pnl.json for build_live_dashboard.py to embed. `recent_closed` is a persisted
LEDGER of every closed trip since `ledger_since` (2026-11-21) — the walk rebuilds the last DAYS
of fills each run and merge_ledger() keeps the older trips it can no longer see.

Honesty rules:
  * Anchored to reality: reconstruction starts from (current net - sum of fill deltas), so the
    walk always ends exactly at the account's live position even if history is truncated.
  * Fees included, converted to USDT (BNB fees valued at the CURRENT BNB price - labeled approx).
  * No estimates otherwise: entry prices and quantities are the exchange's own fill records.

Keys: prefers the READ-ONLY pair BINANCE_RO_KEY/BINANCE_RO_SECRET (safe for CI), falls back to
BINANCE_API_KEY/BINANCE_API_SECRET (the VM). With no keys at all it exits 0 without writing,
and the dashboard renders exactly as before. GET endpoints only - this module cannot trade.
"""
import os, json, time, calendar, hmac, hashlib, urllib.parse, urllib.request

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "out", "real_pnl.json")
BASE = "https://api.binance.com"
DUST = 1.5e-4        # |net| below this (~$10) counts as flat between round trips — well under any
                     # real position (min ~0.003 BTC) but above repay/fee residuals (~0.00005)
DAYS = 60            # fill window the walk REBUILDS each run; older closed trips live in the ledger
HOURLY_DAYS = 90     # equity_history keeps every hourly point this far back; older days are thinned
# the record's inception (owner flattened the account and asked for a real track record "from
# now"); used only if the output file is MISSING, so a rebuilt VM re-seeds the same record
INCEPTION = {"ts": "2026-08-12 19:25 UTC", "equity": 292.2}


def _ts_ms(s):
    """'YYYY-MM-DD HH:MM UTC' -> epoch ms (None if unparseable)."""
    try:
        return calendar.timegm(time.strptime(str(s), "%Y-%m-%d %H:%M UTC")) * 1000
    except Exception:
        return None


def _trip_ms(t, which):
    """Exact opened/closed ms when the row stores it (rows written since 2026-11-22), else the
    minute from the iso string (legacy rows)."""
    v = t.get(which + "_ms")
    return int(v) if v is not None else _ts_ms(t.get(which))


def merge_ledger(old, fresh, start_ms, keep_old_interest=False):
    """Closed-trip LEDGER (2026-11-21, owner: "i need all real live trading record on the trade
    tape"). The walk only sees fills from start_ms on, so on 11-21 the 09-22 -> 10-08 trip
    (-$55.17) silently fell off the list when its entry fill passed the window edge. Now every
    published trip persists: this run's walk is authoritative for what it can see, the previous
    list supplies what it can no longer see.
      * old trip opened before the walk start -> kept as last fully computed; a fresh trip with
                                                its key or overlapping it is a window-edge
                                                truncation -> dropped
      * same (side, opened) in both          -> this run's figures win (freshest interest), except
                                                interest when this run's interest read was partial
      * old trip inside the window, overlapped by a fresh trip -> superseded by the rebuild
      * old trip inside the window, NOT overlapped -> kept (a fill-history gap must never
                                                erase a real record)
    Newest first, like the old recent_closed."""
    # identity: the exact open ms when the row has it (two same-side trips can open in one
    # minute); legacy rows (minute strings only) are matched to rebuilt rows by overlap instead
    key = lambda t: (t.get("side"), int(t["opened_ms"]) if t.get("opened_ms") is not None
                     else t.get("opened"))

    def span(t):
        o, c = _trip_ms(t, "opened"), _trip_ms(t, "closed")
        if t.get("closed_ms") is None and o is not None and c == o:
            c = o + 59_999            # legacy row opened+closed in one minute: the whole minute
        return o, c
    fresh_by_key = {key(f): f for f in fresh}
    fresh_span = [(f, span(f)) for f in fresh]
    overlaps = lambda o, c: [f for f, (fo, fc) in fresh_span
                             if fo is not None and fc is not None and fo < c and fc > o]
    keep, drop = [], set()
    for t in old:
        o, c = span(t)
        if o is None or c is None:
            continue
        k = key(t)
        if o < start_ms:
            keep.append(t)
            drop.add(k)
            drop.update(key(f) for f in overlaps(o, c))
        elif k in fresh_by_key:
            if keep_old_interest and t.get("interest_usdt") is not None:
                fresh_by_key[k]["interest_usdt"] = t["interest_usdt"]
        elif not overlaps(o, c):
            keep.append(t)
    out = keep + [f for f in fresh if key(f) not in drop]
    out.sort(key=lambda t: (_trip_ms(t, "closed") or 0, _trip_ms(t, "opened") or 0), reverse=True)
    return out


MIN_TWR_EQ = 5.0    # below this the account is effectively empty: its dust swings are not returns


def twr_since(bl_ms, bl_eq, pts, flows):
    """Time-weighted growth factor since the baseline with deposits/withdrawals REMOVED (owner
    2026-11-22: "make sure deposit would not count as profit"). Each step between equity
    snapshots grows by (eq_now - money moved in that step) / eq_before; steps chain.
    A step where removing the flow leaves nothing (the reading does not contain the money yet —
    clocks/latency) DEFERS that flow to the next reading instead of skipping it, so a deposit
    can never be booked as growth. Steps from an (almost) empty account count as flat."""
    f, t0, e0 = 1.0, bl_ms, bl_eq
    for p in pts:
        pm = int(p.get("ms") or _ts_ms(p.get("t")) or 0)
        if pm <= t0:
            continue
        moved = sum(x["dir"] * x["usd"] for x in flows
                    if x.get("usd") is not None and t0 < int(x["ms"]) <= pm)
        eq = float(p["eq"])
        if e0 and e0 >= MIN_TWR_EQ:
            g = (eq - moved) / e0
            if g <= 0 and moved:
                continue                      # flow not in this reading yet: carry it forward
            if g > 0:
                f *= g
        t0, e0 = pm, eq
    return f


def thin_history(pts, cut_ms, flow_ms=()):
    """Bounded equity history WITHOUT losing the record's start (2026-11-21: the old [-2200:]
    cap had already trimmed 12-22 Aug and would have cut the 20 Sep M1 start by ~21 Dec).
    Every point newer than cut_ms stays; each older UTC day keeps only its lowest, highest and
    last reading — real readings at their real times, so dips and peaks survive. The first point
    is always kept, and so are the last reading before and the first reading at/after every
    capital flow (review 2026-11-22: merging the hours around a deposit would credit the
    deposit-day gains to the pre-deposit balance and restate the time-weighted %). Steps with
    no flow multiply out exactly, so time-weighted growth is unchanged by thinning.
    Idempotent (a thinned day thins to itself)."""
    if not pts:
        return pts
    pm = lambda p: int(p.get("ms") or _ts_ms(p.get("t")) or 0)
    pinned = set()
    for fm in flow_ms:
        before = [i for i, p in enumerate(pts) if pm(p) < fm]
        after = [i for i, p in enumerate(pts) if pm(p) >= fm]
        if before: pinned.add(before[-1])
        if after: pinned.add(after[0])
    keep, days = [pts[0]], {}
    for i, p in enumerate(pts[1:], 1):
        ms = _ts_ms(p.get("t"))
        if ms is None or ms >= cut_ms or i in pinned:
            keep.append(p)
        else:
            days.setdefault(p["t"][:10], []).append(p)
    for day in days.values():
        lo = min(day, key=lambda p: p["eq"])
        hi = max(day, key=lambda p: p["eq"])
        keep += [p for p in day if p is lo or p is hi or p is day[-1]]
    keep.sort(key=lambda p: p["t"])
    return keep


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


def interest_rows(key, sec, start_ms):
    """Actual margin borrow interest charged by Binance (GET-only), fetched in <=29-day chunks.
    Returns (rows, complete). Partial results on any error — interest is cosmetic and must never
    sink the snapshot — but `complete` says so, so ledger rows are never frozen on a partial read."""
    rows, end = [], int(time.time() * 1000)
    cur = start_ms
    while cur < end:
        chunk_end = min(cur + 29 * 86_400_000, end)
        page = 1
        while True:
            try:
                r = _signed(key, sec, "/sapi/v1/margin/interestHistory",
                            {"startTime": cur, "endTime": chunk_end, "current": page, "size": 100})
            except Exception:
                return rows, False
            batch = r.get("rows", [])
            rows += batch
            if len(batch) < 100:
                break
            if page >= 10:
                return rows, False   # page cap hit: stop ALL chunks — a mid-window gap with later
                                     # chunks fetched would advance the watermark past unseen rows
            page += 1
        cur = chunk_end + 1
    return rows, True


def margin_transfers(key, sec, start_ms):
    """Money moved INTO / OUT OF the cross-margin account (GET-only): deposits and withdrawals
    are capital flows, not P&L. 30-day windows (the endpoint's limit), paginated. Raises on any
    error so the caller keeps the previous list instead of publishing a partial one."""
    rows, end_all = [], int(time.time() * 1000)
    cur = start_ms
    while cur < end_all:
        end = min(cur + 30 * 86_400_000 - 1, end_all)
        page = 1
        while True:
            r = _signed(key, sec, "/sapi/v1/margin/transfer",
                        {"startTime": cur, "endTime": end, "current": page, "size": 100})
            batch = r.get("rows", [])
            rows += batch
            if len(batch) < 100:
                break
            page += 1
            if page > 50:
                raise RuntimeError("margin transfer history: page cap hit")
        cur = end + 1
    return rows


def flow_usd(asset, qty, ms):
    """USD value of a transferred amount at the time of the transfer. USDT is exact; any other
    asset uses that minute's Binance close (public klines). None if no price — retried next run."""
    if asset == "USDT":
        return round(qty, 2)
    try:
        k = _get("/api/v3/klines", {"symbol": asset + "USDT", "interval": "1m",
                                    "startTime": int(ms) - 60_000, "limit": 1})
        return round(qty * float(k[0][4]), 2) if k else None
    except Exception:
        return None


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

    prev = {}
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT, encoding="utf-8"))
        except Exception as ex:
            # the trade ledger and equity history live ONLY in this file: never overwrite a record
            # we could not read (writes are atomic, so this means real damage — needs a human)
            raise RuntimeError(f"cannot read {OUT} ({ex}) — left untouched, nothing written")

    px = float(_get("/api/v3/ticker/price", {"symbol": "BTCUSDT"})["price"])
    try:
        bnb_px = float(_get("/api/v3/ticker/price", {"symbol": "BNBUSDT"})["price"])
    except Exception:
        # sync audit 2026-10-30: a one-run ticker failure used to value all BNB (balance,
        # liability, interest rows) at $0 — a permanent phantom dip in the persisted series.
        # Fall back to the last published price; 0.0 only before any price was ever stored.
        bnb_px = float(prev.get("bnb_px") or 0.0)

    # stamp BEFORE the balance read (review 2026-11-22): a transfer landing during the request
    # is then ordered AFTER this reading — at worst one step late, never "before but missing"
    snap_ms = int(time.time() * 1000)
    acct = _signed(key, sec, "/sapi/v1/margin/account", {})
    assets = {x["asset"]: x for x in acct["userAssets"]}
    btc_net = float(assets.get("BTC", {}).get("netAsset", 0))
    usdt_net = float(assets.get("USDT", {}).get("netAsset", 0))
    # BNB: the M1 trader's dust convert (2026-10-29) parks close residue as BNB — still equity;
    # without this term every convert would print as a phantom ~$1 loss on the curve
    bnb_net = float(assets.get("BNB", {}).get("netAsset", 0))
    equity = usdt_net + btc_net * px + bnb_net * bnb_px
    # Outstanding LIABILITIES (borrowed + accrued interest), surfaced explicitly (2026-10-23:
    # a $38.85 USDT loan from a manual app round-trip sat invisible for two days; 2026-10-29:
    # 0.0019 BNB of PERIODIC_CONVERTED interest — "pay interest in BNB" is ON — sat invisible
    # since Aug). Interest is included because it is money that must be repaid.
    def _liab(a):
        r = assets.get(a, {})
        return float(r.get("borrowed", 0)) + float(r.get("interest", 0))
    borrowed = dict(btc=_liab("BTC"), usdt=_liab("USDT"), bnb=_liab("BNB"))
    borrowed["total_usdt_value"] = round(
        borrowed["btc"] * px + borrowed["usdt"] + borrowed["bnb"] * bnb_px, 2)

    # --- real performance record: inception baseline (persisted; never overwritten). Seeded
    # 2026-08-12 when the owner flattened the account (~$292.20) and asked for a real track record
    # "from now". A MISSING file falls back to that same inception, not to "now".
    baseline = prev.get("baseline") or dict(INCEPTION)
    bl_ms = _ts_ms(baseline.get("ts")) or (int(time.time() * 1000) - DAYS * 86_400_000)

    start = int(time.time() * 1000) - DAYS * 86_400_000
    # A position still open at the window edge must stay visible to the walk until it closes
    # (review 2026-11-22: a >60-day hold would otherwise never produce its trip): the previous
    # run publishes walk_start_ms = the flat moment its open chain began; start no later than that.
    if prev.get("walk_start_ms"):
        start = min(start, int(prev["walk_start_ms"]) - 60_000)
    # one-time LEDGER SEED (2026-11-21): the first run of this version walks from the baseline so
    # the ledger starts with every trip since inception (the 60-day window had already lost the
    # 08-13, 09-21 and 09-22 trips). Later runs walk DAYS and merge (merge_ledger).
    seeding = not prev.get("ledger_since")
    if seeding:
        start = min(start, bl_ms)
    fills, _from = [], None
    while True:
        _p = {"symbol": "BTCUSDT", "limit": 1000}
        if _from is None:
            _p["startTime"] = start
        else:
            _p["fromId"] = _from + 1
        _batch = _signed(key, sec, "/sapi/v1/margin/myTrades", _p)
        fills += _batch
        if len(_batch) < 1000:
            break
        _from = max(int(t["id"]) for t in _batch)
    fills.sort(key=lambda t: t["time"])

    # Walk ORDERS, not raw fills (2026-10-28 fix, M1 session, owner-approved): the 10-26 short's
    # entry order filled in 19 parts and the FIRST partial (0.00008) kept |net| under DUST, so the
    # trip opened mid-order and $6.4 of entry proceeds never entered its cash (realized -8.66 vs
    # true ~-4.2). One order = one decision: aggregate each order to signed qty / VWAP / summed fees.
    events, byid = [], {}
    for t in fills:
        k = (t["orderId"], t["isBuyer"])
        e = byid.get(k)
        if e is None:
            e = byid[k] = dict(time=t["time"], q=0.0, cost=0.0, fee=0.0)
            events.append(e)
        sgn = 1 if t["isBuyer"] else -1
        e["q"] += sgn * float(t["qty"]); e["cost"] += float(t["qty"]) * float(t["price"])
        e["fee"] += fee_usdt(t, bnb_px)

    # --- non-fill BTC balance changes (sync audit 2026-10-30, walk-anchor fix): dust converts
    # (BTC->BNB), Close-All settles and transfers move BTC without any BTCUSDT fill; unseen,
    # each one shifts the derived baseline and cumulative shifts > DUST would mis-segment old
    # trips. Detect the unexplained delta vs the previous run and carry it as time-placed,
    # fill-less adjustment events (mechanism-agnostic). Adjustments move the running net but
    # never open a trip and never touch trip cash/VWAPs.
    adjs = [a for a in (prev.get("balance_adjustments") or []) if int(a.get("t", 0)) >= start]
    _pa = prev.get("btc_net_asof") or {}
    if _pa.get("t"):
        _pa_t = int(_pa["t"])
        _fills_since = sum((1 if t["isBuyer"] else -1) * float(t["qty"])
                           for t in fills if int(t["time"]) > _pa_t)
        _drift = btc_net - (float(_pa.get("net") or 0) + _fills_since)
        if abs(_drift) > 2e-7:    # above float noise; BTC-paid fees also land here (real)
            # stamp AFTER the interval's last fill (2026-11-04 fix): an app-close settle
            # follows its closing fill — stamping at interval START landed the adjustment
            # inside/before the trip and cost the 11-01 trip its $2.33 residual credit
            _ft = [int(t["time"]) for t in fills if int(t["time"]) > _pa_t]
            adjs.append({"t": (max(_ft) + 1) if _ft else int(time.time() * 1000) - 1,
                         "q": round(_drift, 8)})
    for a in adjs:
        events.append(dict(time=int(a["t"]), q=float(a["q"]), cost=0.0, fee=0.0, adj=True))
    events.sort(key=lambda e: e["time"])

    # anchor: walk MUST end at the live net position
    net = btc_net - sum(e["q"] for e in events)
    trips, cur = [], None
    chain_start = None       # when the current open chain (incl. one-order flips) left flat
    for e in events:
        q = e["q"]; p = e["cost"] / abs(e["q"]) if e["q"] else 0.0; f = e["fee"]
        # A flip can happen in ONE order (binance_trader places a single signed delta), so the net
        # can cross zero without ever resting near flat. Close the old trip and open the new one at
        # the crossing, otherwise the walk keeps the stale side and a meaningless average entry.
        crossed = cur is not None and net != 0 and (net > 0) != (net + q > 0) and abs(net + q) > DUST
        if crossed:
            cur.update(closed=e["time"],
                       realized=cur["cash"] + (net - cur["net0"]) * p - cur["fees"])
            trips.append(cur)
            cur = None
            q_new = net + q          # the part of this order that opens the opposite position
            net = 0.0
            q = q_new
        if cur is None and abs(net) <= DUST and abs(net + q) > DUST and not e.get("adj"):
            if not crossed:
                chain_start = e["time"]
            cur = dict(opened=e["time"], side="LONG" if q > 0 else "SHORT", net0=net,
                       cash=0.0, fees=0.0, max_qty=0.0, open_qty=0.0, open_cost=0.0,
                       entry_px=p, close_qty=0.0, close_cost=0.0, last_px=p)
        net += q
        if cur is not None:
            cur["cash"] -= q * p          # buys spend cash, sells receive
            cur["fees"] += f
            cur["max_qty"] = max(cur["max_qty"], abs(net))
            same_side = (q > 0) == (cur["side"] == "LONG")
            if not e.get("adj"):
                cur["last_px"] = p
                if same_side:              # opening/adding: track weighted entry
                    cur["open_qty"] += abs(q); cur["open_cost"] += abs(q) * p
                else:                      # reducing/closing: track weighted exit
                    cur["close_qty"] += abs(q); cur["close_cost"] += abs(q) * p
            if abs(net) <= DUST:           # round trip closed
                # realized marks only the CHANGE in residual dust across the trip at the close
                # price (2026-10-28 fix: the old `- net * p` had the residual's SIGN inverted and
                # charged pre-existing dust to the trip — reconciles with the account's equity).
                cur.update(closed=e["time"],
                           realized=cur["cash"] + (net - cur["net0"]) * p - cur["fees"])
                trips.append(cur); cur = None; chain_start = None

    # --- actual borrow interest (owner request via M1 session 2026-09-20): real margin cost,
    # attributed to each round trip's time window; valued in USDT (BTC/BNB rows at current price —
    # same labeled approximation as BNB fees). Failure -> fields absent; consumers degrade.
    irows, icomplete = interest_rows(key, sec, start)
    if not icomplete:
        print("[real_pnl] interest history read was partial — ledger interest left as last published")
    def i_usdt(row):
        v = float(row.get("interest", 0)); a = row.get("asset")
        return v if a == "USDT" else v * px if a == "BTC" else v * bnb_px if a == "BNB" else 0.0
    for c in trips:
        c["interest"] = sum(i_usdt(r) for r in irows
                            if c["opened"] <= int(r.get("interestAccuredTime", 0)) <= c["closed"])
    open_interest = (sum(i_usdt(r) for r in irows
                         if int(r.get("interestAccuredTime", 0)) >= cur["opened"])
                     if cur is not None else 0.0)

    def iso(ms):
        return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ms / 1000)) + " UTC"

    # "open: null" must mean FLAT, never "reconstruction failed". If the account holds a real
    # position but the walk never opened a trip for it (entry older than the DAYS window, or a gap
    # in the fill history), say so explicitly with what IS known rather than implying flat.
    open_pos = None
    recon_ok = True
    if cur is None and abs(btc_net) > DUST:
        recon_ok = False
        open_pos = dict(side="LONG" if btc_net > 0 else "SHORT", qty=round(abs(btc_net), 6),
                        avg_entry=None, opened=None, fees_usdt=0.0, interest_usdt=None,
                        unrealized_usd=None, unrealized_pct_equity=None,
                        note=f"entry predates the {DAYS}-day fill window — size is exact, "
                             f"average entry and P&L unavailable")
    if cur is not None and abs(net) > DUST:
        avg = cur["open_cost"] / cur["open_qty"] if cur["open_qty"] else 0.0
        unreal = (px - avg) * net - cur["fees"]     # signed net: works for long and short
        open_pos = dict(side=cur["side"], qty=round(abs(net), 6), avg_entry=round(avg, 2),
                        avg_entry_px=round(avg, 2),
                        first_entry_px=round(cur.get("entry_px") or avg, 2),
                        opened=iso(cur["opened"]), fees_usdt=round(cur["fees"], 2),
                        interest_usdt=round(open_interest, 4),
                        unrealized_usd=round(unreal, 2),
                        unrealized_pct_equity=round(unreal / equity * 100, 2) if equity else None)

    # --- account-vs-model truth (so the dashboard can never imply the model IS the account) ---
    # trading_frozen reflects btc-power's STOP (the Max B executor) — NOT the M1 trader that
    # actually drives this account (sync audit 2026-10-30): publish both, named honestly.
    frozen = os.path.exists(os.path.join(HERE, "..", "STOP"))
    m1_frozen = os.path.exists(os.path.expanduser("~/m1-trader/STOP"))
    m1 = {}
    try:
        with urllib.request.urlopen(
                "https://btctree.github.io/btc-dashboard/m1_state.json", timeout=15) as _r:
            _m1s = json.loads(_r.read())
        m1 = dict(signal=_m1s.get("signal"), entry=(_m1s.get("state") or {}).get("BY"),
                  stop=(_m1s.get("state") or {}).get("BV"), as_of=_m1s.get("last_date"))
    except Exception:
        pass
    model = {}
    try:
        _d = json.load(open(os.path.join(HERE, "..", "out", "results_live.json"), encoding="utf-8"))
        _g = _d.get("model_growth") or {}
        sign = 1 if _g.get("direction") == "LONG" else (-1 if _g.get("direction") == "SHORT" else 0)
        target_btc = sign * float(_g.get("exposure_mult") or 0) * equity / px
        model = dict(direction=_g.get("direction"), exposure_mult=_g.get("exposure_mult"),
                     entry_price=_g.get("entry_price"), entry_date=_g.get("entry_date"),
                     as_of=_d.get("as_of"), target_btc=round(target_btc, 6),
                     gap_usd=round(abs(target_btc - btc_net) * px, 2),
                     account_matches=bool(abs(target_btc - btc_net) * px < 20))
    except Exception:
        pass

    # --- equity history (persisted across runs; baseline was fixed above) ---
    now_iso = iso(snap_ms)
    # running interest total since baseline: watermark-persisted so it stays correct even after
    # rows age out of the fetch window
    watermark = int(prev.get("interest_watermark_ms") or bl_ms)
    if not icomplete:
        # partial read (review 2026-11-22): pages are newest-first, so advancing the watermark
        # past a partial page would skip the older unread rows forever — carry both forward
        total_interest = round(float(prev.get("total_interest_usdt") or 0), 4)
    elif bnb_px == 0 and any(r.get("asset") == "BNB" for r in irows
                             if int(r.get("interestAccuredTime", 0)) > watermark):
        # no BNB price at all (first run + ticker down): defer — recounted next run
        total_interest = round(float(prev.get("total_interest_usdt") or 0), 4)
    else:
        new_int = sum(i_usdt(r) for r in irows if int(r.get("interestAccuredTime", 0)) > watermark)
        total_interest = round(float(prev.get("total_interest_usdt") or 0) + new_int, 4)
        watermark = max([watermark] + [int(r.get("interestAccuredTime", 0)) for r in irows])
    # --- capital flows (owner request 2026-11-22: "add deposit tracker"): transfers into / out
    # of the margin account change equity without being profit or loss. Persisted by transfer id
    # since the baseline; each run re-reads from 2 days before the last successful check (a
    # pending transfer that confirms late is still caught). A failed read keeps the previous list
    # and says so (flows_ok=false) — consumers must not treat a failed read as "no deposits".
    now_ms = int(time.time() * 1000)
    flows_by_tx = {str(f["tx"]): dict(f) for f in (prev.get("capital_flows") or [])
                   if f.get("tx") is not None}
    checked = int(prev.get("flows_checked_ms") or 0)
    f_start = max(bl_ms, checked - 2 * 86_400_000) if checked else bl_ms
    flows_ok = True
    try:
        trows = margin_transfers(key, sec, f_start)
    except Exception as ex:
        trows, flows_ok = [], False
        print(f"[real_pnl] transfer history unavailable ({ex}) — keeping the previous flow list")
    for r in trows:
        try:
            typ = r.get("type")
            if r.get("status") != "CONFIRMED" or typ not in ("ROLL_IN", "ROLL_OUT"):
                continue
            tx = str(r.get("txId") or r.get("tranId") or "")
            if not tx:
                continue
            f = flows_by_tx.get(tx) or {}
            flows_by_tx[tx] = dict(tx=tx, ms=int(r["timestamp"]), t=iso(int(r["timestamp"])),
                                   asset=r.get("asset"), qty=float(r.get("amount") or 0),
                                   dir=1 if typ == "ROLL_IN" else -1, usd=f.get("usd"))
        except Exception as ex:          # one odd row must never stop the tracker: flag + retry
            flows_ok = False
            print(f"[real_pnl] unreadable transfer row skipped ({ex}) — retried next run")
    for f in flows_by_tx.values():
        if f.get("usd") is None:
            f["usd"] = flow_usd(f.get("asset"), float(f.get("qty") or 0), f["ms"])
    # only flows up to THIS balance reading are counted (review 2026-11-22: a transfer seconds
    # after the read would otherwise be subtracted from a balance that does not contain it);
    # later ones are picked up next run (the re-read starts 2 days before the last good check)
    flows = sorted((f for f in flows_by_tx.values() if bl_ms <= int(f["ms"]) <= snap_ms),
                   key=lambda f: (f["ms"], f["tx"]))
    net_flows = round(sum(f["dir"] * f["usd"] for f in flows if f.get("usd") is not None), 2)
    flows_valued = all(f.get("usd") is not None for f in flows)
    # the list is known complete up to: this reading if the read worked, else the last good check
    flows_known_to = snap_ms if flows_ok else checked

    hist = list(prev.get("equity_history") or [])
    if not (bnb_px == 0 and abs(bnb_net) > 1e-9):
        # never persist a $0-BNB point; `ms` = exact read time, so a deposit landing in the same
        # minute as a snapshot is still ordered correctly against it
        hist = hist + [dict(t=now_iso, eq=round(equity, 2), ms=snap_ms)]
    dedup = {}
    for pt in hist:
        if not (isinstance(pt, dict) and isinstance(pt.get("t"), str)
                and isinstance(pt.get("eq"), (int, float))):
            continue                          # a malformed point must not stop the tracker
        dedup[pt["t"][:13]] = pt              # one point per hour (key: 'YYYY-MM-DD HH')
    hist = thin_history([dedup[k] for k in sorted(dedup)],
                        int(time.time() * 1000) - HOURLY_DAYS * 86_400_000,
                        [int(f["ms"]) for f in flows])
    _pm = lambda p: int(p.get("ms") or _ts_ms(p.get("t")) or 0)

    # deposit-free performance (the same numbers every consumer should show). If the transfer
    # read failed, a deposit since the last good check could be in the balance but not in the
    # list — so the figures are taken AS OF the last reading the flow list is known to cover.
    bl_eq = float(baseline.get("equity") or 0)
    hist_ok = [p for p in hist if _pm(p) <= flows_known_to] if not flows_ok else hist
    twr = twr_since(bl_ms, bl_eq, hist_ok, flows)
    if flows_ok:
        pnl_since, perf_as_of = round(equity - bl_eq - net_flows, 2), now_iso
    elif hist_ok:
        _last = hist_ok[-1]
        _nf = sum(f["dir"] * f["usd"] for f in flows
                  if f.get("usd") is not None and int(f["ms"]) <= _pm(_last))
        pnl_since, perf_as_of = round(float(_last["eq"]) - bl_eq - _nf, 2), _last["t"]
    else:
        pnl_since, perf_as_of = None, None

    def eq_at(ms):
        """account equity when a trade opened (its % base): the last reading at or before the
        open PLUS any money moved in/out between that reading and the open (the trader sizes
        from the deposit-inclusive balance). Before the first stored reading the baseline is
        used only if nothing (no trip, no transfer) happened between the baseline and ms."""
        best = None
        for p in hist:
            if _pm(p) <= ms:
                best = p
            else:
                break
        if best is not None:
            bm = _pm(best)
            return round(float(best["eq"]) + sum(f["dir"] * f["usd"] for f in flows
                                                 if f.get("usd") is not None and bm < int(f["ms"]) <= ms), 2)
        busy = any(bl_ms < int(c["closed"]) < ms for c in trips) or \
            any(bl_ms < int(f["ms"]) <= ms for f in flows)
        return bl_eq if bl_eq and ms >= bl_ms and not busy else None
    if open_pos is not None and cur is not None:
        open_pos["eq_open"] = eq_at(int(cur["opened"]))

    def trip_out(c):
        return dict(side=c["side"], opened=iso(c["opened"]), closed=iso(c["closed"]),
                    opened_ms=int(c["opened"]), closed_ms=int(c["closed"]),
                    eq_open=eq_at(int(c["opened"])),
                    max_qty=round(c["max_qty"], 6), fees_usdt=round(c["fees"], 2),
                    interest_usdt=round(c.get("interest", 0), 4),
                    realized_usd=round(c["realized"], 2),
                    first_entry_px=round(c.get("entry_px") or 0, 2) or None,
                    avg_entry_px=(round(c["open_cost"] / c["open_qty"], 2)
                                  if c.get("open_qty") else None),
                    avg_exit_px=(round(c["close_cost"] / c["close_qty"], 2)
                                 if c.get("close_qty") else None),
                    last_exit_px=round(c.get("last_px") or 0, 2) or None)
    # ALL closed trips since ledger_since (key kept as recent_closed: both dashboards read it)
    closed_all = merge_ledger(prev.get("recent_closed") or [], [trip_out(c) for c in trips], start,
                              keep_old_interest=not icomplete)
    # a seed whose interest read was partial is NOT final: leave ledger_since unset so the next
    # run seeds again (its fresh rows replace these key-for-key)
    ledger_since = prev.get("ledger_since") or (iso(start) if icomplete else None)
    # keep the walk reaching back to an open chain's start; if the walk could not even find the
    # open position's entry this run, keep the previous pointer rather than losing it
    walk_start = (chain_start if cur is not None
                  else (prev.get("walk_start_ms") if not recon_ok else None))

    out = dict(
        generated=iso(int(time.time() * 1000)), price=px, equity_usdt=round(equity, 2),
        baseline=baseline, equity_history=hist,
        margin_level=float(acct.get("marginLevel", 999)),
        bnb_fee_note="BNB-paid fees valued at current BNB price (approx.)" if bnb_px else "",
        account_btc=round(btc_net, 6), borrowed=borrowed,
        trading_frozen=frozen, maxb_frozen=frozen, m1_frozen=m1_frozen, m1=m1,
        bnb_px=bnb_px,
        btc_net_asof=dict(t=int(time.time() * 1000), net=round(btc_net, 8)),
        balance_adjustments=adjs,
        model=model,
        total_interest_usdt=total_interest, interest_watermark_ms=watermark,
        reconstruction_ok=recon_ok, open=open_pos,
        ledger_since=ledger_since, recent_closed=closed_all, walk_start_ms=walk_start,
        flows_since=baseline.get("ts"), capital_flows=flows, net_flows_usd=net_flows,
        flows_ok=flows_ok, flows_valued=flows_valued,
        flows_checked_ms=now_ms if flows_ok else checked,
        # deposit-free performance since the baseline: P&L = equity - start - net deposits;
        # twr = time-weighted growth factor (deposits/withdrawals removed). USE THESE, not
        # equity - baseline, for any profit figure.
        pnl_since_baseline_usd=pnl_since, twr_since_baseline=round(twr, 6), perf_as_of=perf_as_of,
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    os.replace(tmp, OUT)
    o = out["open"]
    print(f"[real_pnl] wrote {OUT} | open: " +
          (f"{o['side']} {o['qty']} @ {o['avg_entry']} unreal ${o['unrealized_usd']}" if o else "flat") +
          f" | {len(trips)} trips rebuilt, {len(closed_all)} in ledger since {ledger_since}"
          + (" (seeded from baseline)" if seeding else ""))


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
