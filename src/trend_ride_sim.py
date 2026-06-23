"""Trend-ride engine — ports the 3 inspirations from the M1-vs-M5 system:
  1) FULL deployment (100% of equity at 1x; optional confidence scaling / leverage)
  2) LET WINNERS RUN — no early take-profit on trend trades; ride until the strategy
     reverses, the regime flips away, or the trailing stop is hit.
  3) Hard 10% TRAILING cut-loss overlay (ratchets behind high/low-water; caps the
     left tail while the right tail stays uncapped).
Also: LONG AND SHORT (direction follows the active strategy's signal), single
position at a time, 1-minute intraday fills for stops. Start $500.
"""
import os, copy, json
import numpy as np
import regime_switch_sim as rss   # reuse load(), MAP, regimes, intraday, funding
import regime_system as rs

HERE = os.path.dirname(__file__)
TREND_GROUP = rss.TREND_GROUP
BEAR_GROUP = rss.BEAR_GROUP

CFG = dict(
    start=500.0, fee=0.0005, use_funding=True, fund_fallback=0.00011 * 3,
    cutloss=0.10,            # hard trailing stop distance (M1vM5 uses 10%)
    deploy_high=1.0, deploy_med=1.0, deploy_low=1.0,   # full deployment (fraction of equity)
    lev=1.0,                 # leverage multiple on the deployed fraction
    conf_floor=0.5,          # skip regimes with regime-strategy Sharpe below this
    conf_high=1.8, conf_med=1.0,
    allow_short=True,        # let the engine flip short in bear/down strategies
    maint=0.005,
    let_run=True,            # trend trades ignore the early signal-flip-to-flat exit
    slip=0.0,                # stop-fill slippage (fraction worse than the stop level)
    # ----- ASYMMETRIC long/short controls (longs and shorts are NOT mirrored) -----
    cutloss_long=None, cutloss_short=None,   # None -> fall back to cutloss
    short_size_mult=1.0,                     # shorts deploy this fraction of the long size
    short_regimes=None,                      # None=any; else only short in these regimes
)

_C = None


def load():
    global _C
    if _C is None:
        _C = rss.load()       # (df, reg, memb, intr, fund)
    return _C


def deploy_for(cs, cfg):
    if cs >= cfg["conf_high"]:
        return cfg["deploy_high"], "High"
    if cs >= cfg["conf_med"]:
        return cfg["deploy_med"], "Med"
    return cfg["deploy_low"], "Low"


def simulate(cfg=CFG):
    df, reg, memb, intr, fund = load()
    close = df["close"].to_numpy(); dates = df["Date"].tolist(); n = len(df)
    H, L, C, di = intr["h"], intr["l"], intr["c"], intr["di"]
    equity = cfg["start"]; pos = None
    eq = np.full(n, cfg["start"], float)
    trades = []; liqs = 0; fees = 0.0; funding_paid = 0.0
    start_i = 260

    def intraday(date_str):
        o = rss._date_ord(date_str)
        if o not in di:
            return None
        s, e = di[o]
        return L[s:e], H[s:e], C[s:e]

    for i in range(n):
        date_i = dates[i]; rg = reg[i]
        # ---- manage open position intraday ----
        if pos is not None:
            arr = intraday(date_i); exited = False
            d = pos["dir"]
            if arr is not None:
                lows, highs, closes = arr
                for bl, bh in zip(lows, highs):
                    if d == 1:
                        if bh > pos["hi"]:
                            pos["hi"] = bh; pos["stop"] = max(pos["stop"], pos["hi"] * (1 - pos["cl"]))
                        hit = bl <= pos["stop"]; fill = pos["stop"]
                        liq_hit = pos["liq"] is not None and bl <= pos["liq"]
                    else:
                        if bl < pos["lo"]:
                            pos["lo"] = bl; pos["stop"] = min(pos["stop"], pos["lo"] * (1 + pos["cl"]))
                        hit = bh >= pos["stop"]; fill = pos["stop"]
                        liq_hit = pos["liq"] is not None and bh >= pos["liq"]
                    if liq_hit:
                        equity -= pos["margin"]; fee = pos["notional"] * cfg["fee"]
                        equity -= fee; fees += fee; liqs += 1
                        trades.append(_t(pos, pos["liq"], i, date_i, "LIQUIDATED", -pos["margin"] - fee))
                        pos = None; exited = True; break
                    if hit:
                        fill = fill * (1 - cfg["slip"]) if d == 1 else fill * (1 + cfg["slip"])
                        ex = _close(pos, fill, i, date_i, "TRAIL-CUTLOSS", cfg)
                        equity += ex["pnl"]; fees += ex["fee"]; trades.append(ex["t"]); pos = None; exited = True; break
            if pos is not None:
                fr = fund.get(date_i, cfg["fund_fallback"]) if cfg["use_funding"] else 0.0
                fc = pos["notional"] * fr; equity -= fc; funding_paid += fc
                suited = _suited(pos, rg)
                m = memb[pos["strat"]][i]
                # let winners run: for trend trades, only exit on reversal (opposite signal)
                # or regime change; do NOT exit on a mere flip-to-flat.
                if pos["kind"] == "trend" and cfg["let_run"]:
                    sig_exit = (m * pos["dir"] < 0)            # signal flipped to opposite
                else:
                    sig_exit = (m * pos["dir"] <= 0)           # flat or opposite ends MR trade
                if (not suited) or sig_exit:
                    ex = _close(pos, close[i], i, date_i,
                                "REGIME-CHANGE" if not suited else "SIGNAL-EXIT", cfg)
                    equity += ex["pnl"]; fees += ex["fee"]; trades.append(ex["t"]); pos = None

        # ---- entry (flat only) ----
        if pos is None and i >= start_i and equity > 1:
            strat, kind, cs = rss.MAP.get(rg, (None, "flat", 0.0))
            if strat is not None and cs >= cfg["conf_floor"]:
                m = memb[strat][i]
                d = 1 if m > 0 else (-1 if (m < 0 and cfg["allow_short"]) else 0)
                # asymmetric short gating: only short in allowed regimes
                if d == -1 and cfg["short_regimes"] is not None and rg not in cfg["short_regimes"]:
                    d = 0
                if d != 0:
                    dep, bk = deploy_for(cs, cfg)
                    cl_l = cfg["cutloss_long"] if cfg["cutloss_long"] is not None else cfg["cutloss"]
                    cl_s = cfg["cutloss_short"] if cfg["cutloss_short"] is not None else cfg["cutloss"]
                    if d == -1:
                        dep *= cfg["short_size_mult"]
                    cl = cl_l if d == 1 else cl_s
                    margin = equity * dep; notional = margin * cfg["lev"]
                    fee = notional * cfg["fee"]; equity -= fee; fees += fee
                    entry = close[i]
                    if d == 1:
                        stop = entry * (1 - cl)
                        liq = entry * (1 - 1.0 / cfg["lev"] + cfg["maint"]) if cfg["lev"] > 1 else None
                        if liq:
                            stop = max(stop, liq * 1.003)
                    else:
                        stop = entry * (1 + cl)
                        liq = entry * (1 + 1.0 / cfg["lev"] - cfg["maint"]) if cfg["lev"] > 1 else None
                        if liq:
                            stop = min(stop, liq * 0.997)
                    pos = dict(entry=entry, entry_i=i, entry_date=date_i, margin=margin, notional=notional,
                               lev=cfg["lev"], strat=strat, kind=kind, regime=rg, bucket=bk, conf=cs,
                               dir=d, hi=entry, lo=entry, stop=stop, liq=liq, cl=cl)
        eq[i] = max(equity, 0.0)
        if equity <= 0:
            eq[i:] = 0.0; break

    if pos is not None:
        ex = _close(pos, close[-1], n - 1, dates[-1], "EOD", cfg)
        equity += ex["pnl"]; fees += ex["fee"]; trades.append(ex["t"]); eq[-1] = max(equity, 0)
    return _report(cfg, df, eq, trades, liqs, fees, funding_paid)


def _suited(pos, rg):
    if pos["kind"] == "trend" and pos["regime"] in TREND_GROUP:
        return rg in TREND_GROUP
    if pos["regime"] in BEAR_GROUP:
        return rg in BEAR_GROUP
    return rg == pos["regime"]


def _close(pos, price, i, date, reason, cfg):
    notional = pos["notional"]; fee = notional * cfg["fee"]
    pnl = notional * (price / pos["entry"] - 1.0) * pos["dir"] - fee
    return dict(pnl=pnl, fee=fee, t=_t(pos, price, i, date, reason, pnl))


def _t(pos, price, i, date, reason, pnl):
    return dict(entry=pos["entry"], exit=price, dir=pos["dir"], strat=pos["strat"], regime=pos["regime"],
                bucket=pos["bucket"], reason=reason, pnl=pnl, margin=pos["margin"], notional=pos["notional"],
                bars=i - pos["entry_i"], ret=(price / pos["entry"] - 1) * pos["dir"])


def _report(cfg, df, eq, trades, liqs, fees, funding):
    n = len(eq); ret = np.zeros(n); ret[1:] = np.where(eq[:-1] > 0, eq[1:] / eq[:-1] - 1, 0)
    ann = 365; years = n / ann; final = eq[-1]
    total = final / cfg["start"] - 1
    cagr = (final / cfg["start"]) ** (1 / years) - 1 if final > 0 else -1
    peak = np.maximum.accumulate(eq); maxdd = (eq / peak - 1).min()
    sd = ret.std(ddof=1)
    sharpe = ret.mean() * ann / (sd * np.sqrt(ann)) if sd > 0 else float("nan")
    down = ret[ret < 0].std(ddof=1) * np.sqrt(ann) if (ret < 0).sum() > 1 else float("nan")
    sortino = ret.mean() * ann / down if down and down > 0 else float("nan")
    calmar = cagr / abs(maxdd) if maxdd < 0 else float("nan")
    pnls = [t["pnl"] for t in trades]; wins = [p for p in pnls if p > 0]
    reasons = {}
    for t in trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    longs = [t for t in trades if t["dir"] == 1]; shorts = [t for t in trades if t["dir"] == -1]
    return dict(config=cfg, final=final, total=total, cagr=cagr, maxdd=maxdd, sharpe=sharpe,
                sortino=sortino, calmar=calmar, n_trades=len(trades), mult=final / cfg["start"],
                winrate=len(wins) / len(pnls) if pnls else float("nan"),
                liquidations=liqs, fees=fees, funding=funding, exit_reasons=reasons,
                n_long=len(longs), n_short=len(shorts), eq=eq, dates=df["Date"].tolist(), trades=trades)


def pr(r, title):
    print(f"\n===== {title} =====")
    c = r["config"]
    print(f"  deploy {int(c['deploy_high']*100)}% lev {c['lev']}x  cutloss {int(c['cutloss']*100)}%  "
          f"short {'on' if c['allow_short'] else 'off'}  let_run {c['let_run']}")
    print(f"  $500 -> ${r['final']:,.0f}  ({r['mult']:.1f}x)  CAGR {r['cagr']*100:.1f}%  Sharpe {r['sharpe']:.2f}  "
          f"maxDD {r['maxdd']*100:.1f}%  Calmar {r['calmar']:.2f}")
    print(f"  trades {r['n_trades']} ({r['n_long']}L/{r['n_short']}S)  win {r['winrate']*100:.0f}%  "
          f"liq {r['liquidations']}  fees ${r['fees']:,.0f}  funding ${r['funding']:,.0f}")
    print(f"  exits: {r['exit_reasons']}")


if __name__ == "__main__":
    pr(simulate(CFG), "TREND-RIDE v1 (full 1x deploy, let-run, 10% trail, long+short)")
