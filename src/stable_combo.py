"""Diversified, regime-aware ensemble — built for stability (lower drawdown) with HONEST
leverage/liquidation modelling.

 - Finer regimes (regime_v2). Per regime, the eligible engines = those with robust edge
   (min of 1st/2nd-half in-position Sharpe above a floor); ensemble = mean of their positions
   -> continuous, diversified exposure (averaging cuts drawdown vs a single engine).
 - Vol-targeting: scale exposure down when realised vol is high.
 - Drawdown kill-switch: halve exposure while in a deep drawdown.
 - Honest liquidation: at leverage L, a single-day intraday adverse move >= ~1/L wipes the
   account (ruin) -> counted. Slippage on turnover. This makes the 5x ruin risk VISIBLE.
Combined 2014+ history (so it includes the leverage path the user flagged).
"""
import os
import numpy as np
import pandas as pd
import compare_m1m5 as cm
import regime_v2 as r2
import signals as sg
import backtest as bt

HERE = os.path.dirname(__file__)
ANN = 365
ENGINES = list(sg.EXCEL_COL.keys())


def prep():
    df = cm.prep(cm.build_combined())
    h, l, c = df["high"], df["low"], df["close"]
    df["ATRpct"] = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1).rolling(14).mean() / c
    df["ADX"], df["PDI"], df["MDI"] = r2.wilder_adx(h, l, c, 14)
    reg = r2.classify(df)
    sigs = sg.run_all(df, single_lookahead=False)
    memb = {k: bt.signals_to_position(sigs[k]) for k in ENGINES}
    return df, reg, memb


def eligible_map(df, reg, memb, floor=0.5, topn=3):
    """Per regime, engines with robust (min of H1/H2) in-position Sharpe >= floor."""
    close = df["close"].to_numpy(); px = np.zeros(len(df)); px[1:] = close[1:] / close[:-1] - 1
    rprev = np.roll(reg, 1); mid = len(df) // 2
    emap = {}
    for cell in r2.CELLS:
        mask = rprev == cell
        scores = []
        for k in ENGINES:
            held = np.roll(memb[k], 1); r = held * px
            m1 = mask.copy(); m1[mid:] = False; m2 = mask.copy(); m2[:mid] = False
            r1, r2_ = r[m1], r[m2]
            if len(r1) > 12 and len(r2_) > 12 and r1.std() > 0 and r2_.std() > 0:
                s1 = r1.mean() * ANN / (r1.std(ddof=1) * np.sqrt(ANN))
                s2 = r2_.mean() * ANN / (r2_.std(ddof=1) * np.sqrt(ANN))
                scores.append((k, min(s1, s2)))
        scores = [s for s in scores if s[1] >= floor]
        scores.sort(key=lambda x: -x[1])
        emap[cell] = [k for k, _ in scores[:topn]]
    return emap


def exposure_series(df, reg, memb, emap):
    n = len(df); exp = np.zeros(n)
    for i in range(n):
        elig = emap.get(reg[i], [])
        if elig:
            exp[i] = np.mean([memb[k][i] for k in elig])   # diversified, in [-1,1]
    return exp


def simulate(df, exp, lev=1.0, fee=0.0005, slip=0.0, vol_target=0.0, dd_kill=0.0,
             dd_derisk=0.0, smooth=0, band=0.0, use_funding=True, start=500.0, maint=0.01):
    close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
    n = len(df)
    if smooth and smooth > 1:                                   # EMA-smooth the exposure path
        exp = pd.Series(exp).ewm(span=smooth, adjust=False).mean().to_numpy()
    rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
    fmap = {}
    p = os.path.join(HERE, "..", "data", "funding.csv")
    if os.path.exists(p):
        fmap = dict(zip(*[pd.read_csv(p)[x] for x in ["date", "funding_rate"]]))
    fund = np.array([fmap.get(d, 0.0) for d in df["Date"]]) if use_funding else np.zeros(n)
    eq = np.full(n, start); equity = start; peak = start; held = 0.0; liqs = 0
    i0 = 260
    for i in range(i0, n):
        # target exposure decided at close[i-1] earns day i
        tgt = exp[i - 1] * lev
        if vol_target > 0 and rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt = np.clip(tgt, -abs(exp[i - 1]) * lev, abs(exp[i - 1]) * lev)
            scale = min(1.0, vol_target / rv[i - 1])
            tgt *= scale
        if dd_kill > 0 and equity < peak * (1 - dd_kill):
            tgt *= 0.5
        if dd_derisk > 0:                                       # continuous de-risk as DD deepens
            dd_now = equity / peak - 1.0                        # <= 0
            tgt *= max(0.1, 1.0 + dd_now / dd_derisk)           # at DD = -dd_derisk -> ~0 exposure
        e = tgt
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0):
            e = held                                            # deadband: skip tiny rebalances (cuts turnover)
        # honest liquidation: intraday adverse move vs prior close
        if e > 0:
            adverse = -(low[i] / close[i - 1] - 1)        # positive = down move magnitude
        elif e < 0:
            adverse = (high[i] / close[i - 1] - 1)
        else:
            adverse = 0.0
        if e != 0 and abs(e) * max(adverse, 0) >= (1 - maint):
            equity *= 0.01; liqs += 1; held = 0.0          # wiped (ruin)
            eq[i] = equity; peak = max(peak, equity); continue
        ret = close[i] / close[i - 1] - 1
        pnl = e * ret
        turn = abs(e - held); fee_c = turn * (fee + slip)   # slippage hits rebalancing turnover
        fund_c = abs(e) * fund[i]
        equity *= (1 + pnl); equity -= equity * (fee_c + fund_c)
        held = e; eq[i] = equity; peak = max(peak, equity)
        if equity <= start * 1e-4:
            eq[i:] = equity; break
    return eq, liqs


def metrics(eq, start=500.0):
    eq = np.asarray(eq, float)
    r = np.diff(eq) / eq[:-1]; r = r[np.isfinite(r)]
    yrs = len(eq) / ANN
    cagr = (eq[-1] / start) ** (1 / yrs) - 1 if eq[-1] > 0 else -1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dn = r[r < 0].std(ddof=1) * np.sqrt(ANN) if (r < 0).sum() > 1 else float("nan")
    sortino = r.mean() * ANN / dn if dn and dn > 0 else float("nan")
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    return dict(final=eq[-1], cagr=cagr, sharpe=sh, sortino=sortino, maxdd=dd,
                calmar=cagr / abs(dd) if dd < 0 else float("nan"))


def main():
    df, reg, memb = prep()
    emap = eligible_map(df, reg, memb)
    print("=== eligible engines per regime (robust min(H1,H2) Sharpe >= 0.5) ===")
    for cell in r2.CELLS:
        print(f"  {cell:12s} -> {emap[cell] or '(stand aside)'}")
    exp = exposure_series(df, reg, memb, emap)
    print(f"\nexposure: in-market {np.mean(exp[260:]!=0)*100:.0f}% of days, avg |exp| {np.mean(np.abs(exp[260:])):.2f}")

    def wf(eq):
        mid = len(eq) // 2
        return metrics(eq[:mid])["sharpe"], metrics(eq[mid:])["sharpe"]

    print("\n=== DIVERSIFIED ENSEMBLE (2014+, honest liquidation, fees+funding, 30bp slip) ===")
    print(f"{'config':30s} {'$500->':>13s} {'CAGR':>6s} {'Shrp':>5s} {'maxDD':>7s} {'Calm':>5s} {'liq':>4s} {'WF H1/H2':>12s}")
    configs = [
        ("1x base", dict(lev=1)),
        ("1x +voltgt60 +DDkill30", dict(lev=1, vol_target=0.60, dd_kill=0.30)),
        ("2x +voltgt60 +DDkill30", dict(lev=2, vol_target=0.60, dd_kill=0.30)),
        ("3x +voltgt60 +DDkill30", dict(lev=3, vol_target=0.60, dd_kill=0.30)),
        ("5x +voltgt60 +DDkill30", dict(lev=5, vol_target=0.60, dd_kill=0.30)),
        ("5x raw (no controls)", dict(lev=5)),
    ]
    for name, kw in configs:
        eq, liq = simulate(df, exp, slip=0.003, **kw)
        m = metrics(eq); h1, h2 = wf(eq)
        print(f"{name:30s} ${m['final']:>12,.0f} {m['cagr']*100:>5.0f}% {m['sharpe']:>5.2f} "
              f"{m['maxdd']*100:>6.0f}% {m['calmar']:>5.2f} {liq:>4d} {h1:.2f}/{h2:.2f}")


if __name__ == "__main__":
    main()
