"""Corrected real-trade engine (v2), driven by the finding that the daily ensemble
holds the edge and a tight intraday trailing stop destroys it.

Design:
 - Target exposure (multiple of equity) = consensus_fraction x LEV_CAP, long-only.
   At LEV_CAP=1 this reproduces the validated daily ensemble (Sharpe ~1.28).
 - Held continuously; rebalanced daily at the close (turnover -> fees).
 - Intraday DISASTER stop only: if the day's low (true 1-min intraday extreme, from
   btc_daily derived from 1m) breaches entry*(1-stop), the day's loss is capped at
   -stop and we go flat until the next close. Wide (default 15%) so it only cuts tails.
 - Explicit LIQUIDATION if an intraday move wipes the margin (price drop >= 1/lev).
 - Funding charged daily on notional; taker fees on turnover. Start $500.
"""
import os, copy, json
import numpy as np
import pandas as pd
import indicators as ind
import signals as sg
import backtest as bt

HERE = os.path.dirname(__file__)
DATADIR = os.path.join(HERE, "..", "data")
MEMBERS = ["OBV", "DSAM", "MACD", "RSI", "EMA", "BB", "MFI", "OBV_ROC", "MACD_SIG"]

CFG = dict(
    start=500.0, fee=0.0005, lev_cap=1.0, stop=0.15, maint=0.005,
    use_funding=True, fund_fallback=0.00011 * 3, warmup=260,
    exit_thresh=0.10,        # consensus below this -> flat
    lev_trend_only=False,    # apply leverage only in TREND_UP regime (else 1x)
    dd_killswitch=0.0,       # if >0: scale target by kill_scale when in DD worse than this
    kill_scale=0.5,
    vol_target=0.0,          # if >0: scale target so realized vol ~ this (annualized)
)


def _regime_array(df):
    c = df["close"].to_numpy(); s20 = df["SMA20"].to_numpy()
    bbw = ((df["BB_Upper"] - df["BB_Lower"]) / df["SMA20"]).to_numpy()
    bbw_med = pd.Series(bbw).rolling(365, min_periods=30).median().to_numpy()
    ext = (c - s20) / s20
    reg = np.zeros(len(df), dtype="int8")  # 0 neutral,1 trend_up,2 trend_dn,3 ranging
    trend = (bbw > bbw_med * 1.15) & (np.abs(ext) > 0.04)
    reg[trend & (ext > 0)] = 1
    reg[trend & (ext <= 0)] = 2
    return reg


def load():
    raw = pd.read_csv(os.path.join(DATADIR, "btc_daily.csv"))
    df = ind.compute(raw[["date", "close", "volume", "high", "low", "open"]]
                     .rename(columns={"date": "Date"})).reset_index(drop=True)
    df["SMA50"] = df["close"].rolling(50).mean()
    fund = {}
    p = os.path.join(DATADIR, "funding.csv")
    if os.path.exists(p):
        f = pd.read_csv(p); fund = dict(zip(f["date"], f["funding_rate"]))
    sigs = sg.run_all(df, single_lookahead=False)
    cons = np.clip(np.mean([bt.signals_to_position(sigs[k]) for k in MEMBERS], axis=0), 0, None)
    reg = _regime_array(df)
    rv = pd.Series(df["close"].pct_change()).rolling(20).std().to_numpy() * np.sqrt(365)
    return df, cons, fund, reg, rv


_CACHE = None


def simulate(cfg=CFG):
    global _CACHE
    if _CACHE is None:
        _CACHE = load()
    df, cons, fund, reg, rv = _CACHE
    close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
    dates = df["Date"].tolist()
    n = len(df)
    peak_eq = cfg["start"]

    equity = cfg["start"]
    held = 0.0            # current exposure multiple (of equity), long-only
    eq = np.full(n, cfg["start"], float)
    target_prev = 0.0
    trades = 0; wins = 0; stops = 0; liqs = 0
    fees_paid = funding_paid = 0.0
    in_pos_days = 0
    prev_in = False

    for i in range(1, n):
        date_i = dates[i]
        exposure = target_prev                     # exposure decided at close[i-1]
        notional = exposure * equity
        day_ret = close[i] / close[i - 1] - 1.0
        low_ret = low[i] / close[i - 1] - 1.0       # worst intraday move vs entry ref
        stopped = False
        if exposure > 0:
            in_pos_days += 1
            # liquidation: intraday drop wipes margin (drop >= 1/lev)
            if cfg["lev_cap"] > 1 and low_ret <= -(1.0 / cfg["lev_cap"]) + cfg["maint"]:
                equity -= notional * (1.0 / cfg["lev_cap"])   # lose the margin slice
                equity -= notional * cfg["fee"]; fees_paid += notional * cfg["fee"]
                liqs += 1; trades += 1; held = 0.0
                eq[i] = max(equity, 0.0); peak_eq = max(peak_eq, equity)
                # decide new target at close[i]
                target_prev = _target(cons, i, cfg, equity, reg, rv, peak_eq)
                fees_paid += abs(target_prev) * equity * cfg["fee"]; equity -= abs(target_prev) * equity * cfg["fee"]
                if equity <= 0:
                    eq[i:] = 0.0; break
                continue
            # disaster stop
            if low_ret <= -cfg["stop"]:
                r = -cfg["stop"]
                stopped = True; stops += 1
            else:
                r = day_ret
            pnl = notional * r
            fee_funding = notional * (fund.get(date_i, cfg["fund_fallback"]) if cfg["use_funding"] else 0.0)
            equity += pnl - fee_funding
            funding_paid += fee_funding

        # ---- close[i] decision ----
        peak_eq = max(peak_eq, equity)
        held_after = 0.0 if stopped else exposure
        target = _target(cons, i, cfg, equity, reg, rv, peak_eq)
        # turnover fee
        turn = abs(target - held_after)
        fee = turn * equity * cfg["fee"]
        equity -= fee; fees_paid += fee
        # trade accounting (a closed exposure -> count)
        if exposure > 0 and (target == 0 or stopped):
            trades += 1
            # crude win flag: equity rose while in this position window -> approx by day pnl sign sum is complex;
            # use: this exit's realized day pnl proxy
        eq[i] = max(equity, 0.0)
        target_prev = target
        if equity <= 0:
            eq[i:] = 0.0; break

    return _report(cfg, df, eq, trades, stops, liqs, fees_paid, funding_paid, cons, in_pos_days)


def _target(cons, i, cfg, equity, reg, rv, peak_eq):
    if equity <= 1:
        return 0.0
    c = cons[i]
    if c < cfg["exit_thresh"]:
        return 0.0
    lev = cfg["lev_cap"]
    if cfg["lev_trend_only"] and reg[i] != 1:   # only lever in TREND_UP
        lev = min(lev, 1.0)
    tgt = c * lev
    if cfg["vol_target"] > 0 and rv[i] == rv[i] and rv[i] > 0:
        tgt = min(tgt, c * lev, (cfg["vol_target"] / rv[i]) * lev)
    if cfg["dd_killswitch"] > 0 and equity < peak_eq * (1 - cfg["dd_killswitch"]):
        tgt *= cfg["kill_scale"]
    return tgt


def _report(cfg, df, eq, trades, stops, liqs, fees, funding, cons, in_pos_days):
    n = len(eq)
    ret = np.zeros(n); ret[1:] = np.where(eq[:-1] > 0, eq[1:] / eq[:-1] - 1, 0)
    ann = 365; years = n / ann
    final = eq[-1]; total = final / cfg["start"] - 1
    cagr = (final / cfg["start"]) ** (1 / years) - 1 if final > 0 else -1.0
    peak = np.maximum.accumulate(eq); maxdd = (eq / peak - 1).min()
    sd = ret.std(ddof=1)
    sharpe = ret.mean() * ann / (sd * np.sqrt(ann)) if sd > 0 else float("nan")
    down = ret[ret < 0].std(ddof=1) * np.sqrt(ann) if (ret < 0).sum() > 1 else float("nan")
    sortino = ret.mean() * ann / down if down and down > 0 else float("nan")
    calmar = cagr / abs(maxdd) if maxdd < 0 else float("nan")
    return dict(config=cfg, final=final, total=total, cagr=cagr, maxdd=maxdd, sharpe=sharpe,
                sortino=sortino, calmar=calmar, trades=trades, stops=stops, liquidations=liqs,
                fees_paid=fees, funding_paid=funding, eq=eq, dates=df["Date"].tolist(),
                exposure_days=in_pos_days / n)


def run(over):
    c = copy.deepcopy(CFG); c.update(over); return simulate(c)


def row(label, r):
    return (f"{label:24s} ${r['final']:>10,.0f} {r['total']*100:>+8.0f}% {r['cagr']*100:>6.1f}% "
            f"{r['sharpe']:>5.2f} {r['sortino']:>5.2f} {r['maxdd']*100:>7.1f}% {r['calmar']:>5.2f} "
            f"{r['liquidations']:>3d} ${r['fees_paid']:>6,.0f} ${r['funding_paid']:>7,.0f}")


if __name__ == "__main__":
    print("config                        final     total    CAGR  Shrp  Sort    maxDD  Calm liq    fees  funding")
    print("-" * 110)
    print("[ROLE-CONVERGED FINAL CANDIDATES]")
    # A: SPOT 1x, no stop (best risk-adjusted, no funding/liquidation)
    print(row("A SPOT 1x no-stop", run(dict(lev_cap=1.0, use_funding=False, stop=0.99))))
    # B: PERP 1x, funding, 25% catastrophe stop
    print(row("B PERP 1x catstop25", run(dict(lev_cap=1.0, stop=0.25))))
    # C: geared 1.5x trend-only + DD killswitch + cat stop (quant enhancement)
    print(row("C GEARED 1.5x trend", run(dict(lev_cap=1.5, stop=0.25, lev_trend_only=True,
                                              dd_killswitch=0.30, kill_scale=0.5))))
    # D: vol-targeted spot (actuary: stabilize DD)
    print(row("D SPOT voltgt 60%", run(dict(lev_cap=1.0, use_funding=False, stop=0.99, vol_target=0.60))))
    # E: geared 1.5x trend, SPOT-style (no funding) for comparison
    print(row("E GEARED 1.5x noFund", run(dict(lev_cap=1.5, stop=0.25, lev_trend_only=True,
                                               dd_killswitch=0.30, use_funding=False))))
    print("-" * 110)
    print("[reference]")
    print(row("daily ens 1x +funding", run(dict(lev_cap=1.0, stop=0.99))))
