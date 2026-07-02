"""Find a BALANCE: keep 8B-like profit from leverage, but tame the 3 big drops.
Same proven ensemble (conviction-filtered v2) + turnover control (B), then layer leverage with
drawdown-control overlays: SMA trend filter (no falling knives / no longs into tops) and a
continuous crash de-risk. Honest: real data 2014+, fees, slippage on turnover, intraday liquidation.
Reports full metrics + in-window drawdown for the 3 user-flagged periods.
"""
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le

ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
sma50 = df["SMA50"].to_numpy(); sma200 = df["SMA200"].to_numpy()
dates = pd.to_datetime(df["Date"])
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
n = len(df); i0 = 260
up50 = close > sma50; up200 = close > sma200

def tfilter(exp, gate):
    out = exp.copy()
    out[(exp > 0) & (~gate)] = 0.0
    out[(exp < 0) & (gate)] = 0.0
    return out

def isim(exp, lev=1.0, slip=0.005, smooth=5, band=0.15, vol_target=0.60, dd_kill=0.30,
         dd_derisk=0.0, fee=0.0005, maint=0.01):
    e_in = pd.Series(exp).ewm(span=smooth, adjust=False).mean().to_numpy() if smooth > 1 else exp.copy()
    equity = peak = 500.0; held = 0.0; liqs = 0; turn_tot = 0.0
    eq = np.full(n, 500.0)
    for i in range(i0, n):
        tgt = e_in[i - 1] * lev
        if vol_target > 0 and rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt = np.clip(tgt, -abs(e_in[i - 1]) * lev, abs(e_in[i - 1]) * lev)
            tgt *= min(1.0, vol_target / rv[i - 1])
        if dd_kill > 0 and equity < peak * (1 - dd_kill):
            tgt *= 0.5
        if dd_derisk > 0:
            tgt *= max(0.1, 1.0 + (equity / peak - 1.0) / dd_derisk)
        e = tgt
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0):
            e = held
        adverse = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adverse, 0) >= (1 - maint):
            equity *= 0.01; liqs += 1; held = 0.0; eq[i] = equity; peak = max(peak, equity); continue
        ret = close[i] / close[i - 1] - 1
        turn = abs(e - held); turn_tot += turn
        equity *= (1 + e * ret); equity -= equity * turn * (fee + slip)
        held = e; eq[i] = equity; peak = max(peak, equity)
    return pd.Series(eq[i0:], index=dates.iloc[i0:]), liqs, turn_tot / ((n - i0) / ANN)

def met(eq):
    r = eq.pct_change().dropna(); yrs = len(eq) / ANN
    cagr = (eq.iloc[-1] / 500) ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dd = (eq / eq.cummax() - 1).min()
    return eq.iloc[-1], cagr, sh, (cagr / abs(dd) if dd < 0 else float("nan")), dd

WIN = [("W1", "2017-12-16", "2018-11-18"), ("W2", "2021-10-20", "2022-03-09"), ("W3", "2025-05-22", "2025-12-01")]
def wdd(eq):
    out = []
    for nm, a, b in WIN:
        w = eq.loc[a:b]
        out.append((w / w.cummax() - 1).min() * 100 if len(w) else float("nan"))
    return out

CONFIGS = [
    ("ref 1x B", expf, dict(lev=1)),
    ("ref 5x B (the -76%)", expf, dict(lev=5)),
    ("2x B", expf, dict(lev=2)),
    ("3x B", expf, dict(lev=3)),
    ("2x +SMA50", tfilter(expf, up50), dict(lev=2)),
    ("3x +SMA50", tfilter(expf, up50), dict(lev=3)),
    ("2x +SMA50 +derisk25", tfilter(expf, up50), dict(lev=2, dd_derisk=0.25)),
    ("3x +SMA50 +derisk25", tfilter(expf, up50), dict(lev=3, dd_derisk=0.25)),
    ("3x +SMA50 +derisk35", tfilter(expf, up50), dict(lev=3, dd_derisk=0.35)),
    ("3x +SMA200 +derisk30", tfilter(expf, up200), dict(lev=3, dd_derisk=0.30)),
    ("4x +SMA50 +derisk30", tfilter(expf, up50), dict(lev=4, dd_derisk=0.30)),
]

for slip in (0.0, 0.005):
    print(f"\n================  slippage {int(slip*10000)}bp  ================")
    print(f"{'config':22s} {'final $':>14s} {'CAGR':>5s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s} {'liq':>3s} | {'W1':>5s} {'W2':>5s} {'W3':>5s}")
    for name, exp, kw in CONFIGS:
        eq, liq, turn = isim(exp, slip=slip, **kw)
        fin, cagr, sh, cal, dd = met(eq)
        w1, w2, w3 = wdd(eq)
        print(f"{name:22s} ${fin:>13,.0f} {cagr*100:>4.0f}% {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}% {liq:>3d} | {w1:>4.0f}% {w2:>4.0f}% {w3:>4.0f}%")
