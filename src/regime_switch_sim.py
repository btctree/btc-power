"""Regime-switching, single-strategy-at-a-time engine with TRUE 1-minute intraday
entry/exit fills.

Rules (per user spec):
 - One strategy active at a time = the best strategy for the current market type.
 - New entry only when flat (position == 0).
 - Exit when: take-profit hit (intraday) OR cut-loss hit (intraday) OR market type
   changes to one the active strategy isn't suited to.
 - TP / cut-loss are ATR-based and differ by regime (trend rides wider; range tighter).
 - Confidence index = regime-strategy fit (from regime_system Sharpe) -> sizing & leverage.
 - 1-minute bars resolve intraday fills AND the SL-vs-TP sequence within a day.
 - Explicit liquidation guard: stop is always kept inside the liquidation price.
Start $500.
"""
import os, copy, json
import numpy as np
import pandas as pd
import regime_system as rs
import signals as sg
import backtest as bt

HERE = os.path.dirname(__file__)
DATADIR = os.path.join(HERE, "..", "data")

# regime -> (strategy, kind, confidence-Sharpe) ; None strategy = stand aside
MAP = {
    "BULL_TREND":    ("MACD", "trend", 2.47),
    "BULL_PULLBACK": ("DSAM", "trend", 2.51),
    "RANGE_LOWVOL":  (None,   "flat",  0.19),
    "CHOP_HIGHVOL":  ("MACD_SIG", "mr", 2.25),
    "BEAR_TREND":    ("OBV",  "trend", 1.44),
    "BEAR_BOUNCE":   ("MFI",  "mr",    1.31),
    "NEUTRAL":       (None,   "flat",  0.0),
}
TREND_GROUP = {"BULL_TREND", "BULL_PULLBACK"}
BEAR_GROUP = {"BEAR_TREND", "BEAR_BOUNCE"}

CFG = dict(
    start=500.0, fee=0.0005, use_funding=True, fund_fallback=0.00011 * 3,
    conf_floor=0.5,          # don't trade if regime-strategy Sharpe below this
    # ATR multiples by kind
    trend_sl=3.0, trend_tp=0.0,   # tp=0 -> ride (trailing) ; sl trailing at 3*ATR
    mr_sl=1.5, mr_tp=2.0,
    trail_trend=True,
    # sizing (margin % of equity) and leverage by confidence bucket
    size_high=0.50, size_med=0.35, size_low=0.20,
    lev_high=3.0, lev_med=2.0, lev_low=1.0,
    conf_high=1.8, conf_med=1.0,   # Sharpe cutoffs for High/Med/Low
    maint=0.005,
    use_signal_exit=True,          # exit when active strategy flips flat (else ride TP/SL/regime)
    dd_kill=0.0,                   # if >0: halve exposure while equity in DD worse than this
)

_C = None


def load():
    global _C
    if _C is not None:
        return _C
    df = rs.load()
    reg = rs.classify(df)
    sigs = sg.run_all(df, single_lookahead=False)
    memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
    # ATR already in df
    z = np.load(os.path.join(DATADIR, "intraday_1m.npz"))
    day = z["day"]; udays, starts = np.unique(day, return_index=True)
    ends = np.append(starts[1:], len(day))
    di = {int(d): (int(s), int(e)) for d, s, e in zip(udays, starts, ends)}
    intr = dict(h=z["h"], l=z["l"], c=z["c"], di=di)
    fund = {}
    p = os.path.join(DATADIR, "funding.csv")
    if os.path.exists(p):
        f = pd.read_csv(p); fund = dict(zip(f["date"], f["funding_rate"]))
    _C = (df, reg, memb, intr, fund)
    return _C


def _date_ord(s):
    import datetime as dt
    y, m, d = map(int, s.split("-"))
    return (dt.date(y, m, d) - dt.date(1970, 1, 1)).days


def bucket(conf_sharpe, cfg):
    if conf_sharpe >= cfg["conf_high"]:
        return "High", cfg["size_high"], cfg["lev_high"]
    if conf_sharpe >= cfg["conf_med"]:
        return "Med", cfg["size_med"], cfg["lev_med"]
    return "Low", cfg["size_low"], cfg["lev_low"]


def simulate(cfg=CFG):
    df, reg, memb, intr, fund = load()
    close = df["close"].to_numpy(); atr = df["ATR"].to_numpy()
    dates = df["Date"].tolist(); n = len(df)
    H, L, C, di = intr["h"], intr["l"], intr["c"], intr["di"]

    equity = cfg["start"]
    pos = None
    eq = np.full(n, cfg["start"], float)
    trades = []; liqs = 0; fees = 0.0; funding_paid = 0.0
    start_i = 260; peak_eq = cfg["start"]

    def intraday(date_str):
        o = _date_ord(date_str)
        if o not in di:
            return None
        s, e = di[o]
        return L[s:e], H[s:e], C[s:e]

    for i in range(n):
        date_i = dates[i]; rg = reg[i]
        # ---- 1. manage open position intraday on day i ----
        if pos is not None:
            arr = intraday(date_i)
            exited = False
            if arr is not None:
                lows, highs, closes = arr
                for bl, bh in zip(lows, highs):
                    if pos["trail"] and bh > pos["hi"]:
                        pos["hi"] = bh
                        pos["stop"] = max(pos["stop"], pos["hi"] - pos["sl_dist"])
                    # liquidation guard (should not trigger: stop kept above liq)
                    if pos["liq"] is not None and bl <= pos["liq"]:
                        equity -= pos["margin"]; fee = pos["notional"] * cfg["fee"]
                        equity -= fee; fees += fee; liqs += 1
                        trades.append(_t(pos, pos["liq"], i, date_i, "LIQUIDATED", -pos["margin"] - fee))
                        pos = None; exited = True; break
                    if bl <= pos["stop"]:
                        ex = _close(pos, pos["stop"], i, date_i, "CUT-LOSS" if pos["stop"] <= pos["entry"] else "TRAIL-STOP", cfg)
                        equity += ex["pnl"]; fees += ex["fee"]; trades.append(ex["t"]); pos = None; exited = True; break
                    if pos["tp"] is not None and bh >= pos["tp"]:
                        ex = _close(pos, pos["tp"], i, date_i, "TAKE-PROFIT", cfg)
                        equity += ex["pnl"]; fees += ex["fee"]; trades.append(ex["t"]); pos = None; exited = True; break
            if pos is not None:
                # funding for the day
                fr = fund.get(date_i, cfg["fund_fallback"]) if cfg["use_funding"] else 0.0
                fc = pos["notional"] * fr; equity -= fc; funding_paid += fc
                # regime-change / signal exit at close
                strat = MAP.get(rg, (None,))[0]
                suited = _suited(pos, rg)
                sig_exit = cfg["use_signal_exit"] and memb[pos["strat"]][i] <= 0
                if (not suited) or sig_exit:
                    ex = _close(pos, close[i], i, date_i,
                                "REGIME-CHANGE" if not suited else "SIGNAL-EXIT", cfg)
                    equity += ex["pnl"]; fees += ex["fee"]; trades.append(ex["t"]); pos = None

        # ---- 2. entry decision at close[i] (only if flat) ----
        if pos is None and i >= start_i and equity > 1:
            strat, kind, cs = MAP.get(rg, (None, "flat", 0.0))
            if strat is not None and cs >= cfg["conf_floor"] and memb[strat][i] > 0:
                bk, sz, lev = bucket(cs, cfg)
                if cfg["dd_kill"] > 0 and equity < peak_eq * (1 - cfg["dd_kill"]):
                    sz *= 0.5   # de-risk while in deep drawdown
                margin = equity * sz; notional = margin * lev
                fee = notional * cfg["fee"]; equity -= fee; fees += fee
                a = atr[i] if atr[i] == atr[i] else close[i] * 0.03
                entry = close[i]
                if kind == "trend":
                    sl_dist = cfg["trend_sl"] * a
                    tp = None if cfg["trend_tp"] == 0 else entry + cfg["trend_tp"] * a
                    trail = cfg["trail_trend"]
                else:
                    sl_dist = cfg["mr_sl"] * a
                    tp = entry + cfg["mr_tp"] * a
                    trail = False
                stop = entry - sl_dist
                liq = entry * (1 - 1.0 / lev + cfg["maint"]) if lev > 1 else None
                if liq is not None:
                    stop = max(stop, liq * 1.003)   # keep stop above liquidation (no-liq rule)
                pos = dict(entry=entry, entry_i=i, entry_date=date_i, margin=margin, notional=notional,
                           lev=lev, strat=strat, kind=kind, regime=rg, bucket=bk, conf=cs,
                           hi=entry, stop=stop, sl_dist=sl_dist, tp=tp, trail=trail, liq=liq)
        eq[i] = max(equity, 0.0); peak_eq = max(peak_eq, equity)
        if equity <= 0:
            eq[i:] = 0.0; break

    if pos is not None:
        ex = _close(pos, close[-1], n - 1, dates[-1], "EOD", cfg)
        equity += ex["pnl"]; fees += ex["fee"]; trades.append(ex["t"]); eq[-1] = max(equity, 0)

    return _report(cfg, df, eq, trades, liqs, fees, funding_paid)


def _suited(pos, rg):
    # the active strategy stays suited while regime is in the same group it entered in
    if pos["kind"] == "trend" and pos["regime"] in TREND_GROUP:
        return rg in TREND_GROUP
    if pos["regime"] in BEAR_GROUP:
        return rg in BEAR_GROUP
    return rg == pos["regime"]


def _close(pos, price, i, date, reason, cfg):
    notional = pos["notional"]; fee = notional * cfg["fee"]
    pnl = notional * (price / pos["entry"] - 1.0) - fee
    return dict(pnl=pnl, fee=fee, t=_t(pos, price, i, date, reason, pnl))


def _t(pos, price, i, date, reason, pnl):
    return dict(entry=pos["entry"], exit=price, strat=pos["strat"], regime=pos["regime"],
                bucket=pos["bucket"], reason=reason, pnl=pnl, margin=pos["margin"],
                notional=pos["notional"], lev=pos["lev"], bars=i - pos["entry_i"],
                ret_margin=pnl / pos["margin"] if pos["margin"] else 0)


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
    return dict(config=cfg, final=final, total=total, cagr=cagr, maxdd=maxdd, sharpe=sharpe,
                sortino=sortino, calmar=calmar, n_trades=len(trades),
                winrate=len(wins) / len(pnls) if pnls else float("nan"),
                liquidations=liqs, fees=fees, funding=funding, exit_reasons=reasons,
                eq=eq, dates=df["Date"].tolist(), trades=trades)


def pr(r, title):
    print(f"\n===== {title} =====")
    print(f"  $500 -> ${r['final']:,.0f}  ({r['total']*100:+,.0f}%)  CAGR {r['cagr']*100:.1f}%  "
          f"Sharpe {r['sharpe']:.2f}  Sortino {r['sortino']:.2f}  maxDD {r['maxdd']*100:.1f}%  Calmar {r['calmar']:.2f}")
    print(f"  trades {r['n_trades']}  win {r['winrate']*100:.0f}%  LIQUIDATIONS {r['liquidations']}  "
          f"fees ${r['fees']:,.0f}  funding ${r['funding']:,.0f}")
    print(f"  exits: {r['exit_reasons']}")


if __name__ == "__main__":
    pr(simulate(CFG), "ITER-1 regime-switch (conf-scaled lev 1-3x, ATR stops)")
