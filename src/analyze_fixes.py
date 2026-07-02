"""Test candidate fixes for the 3 bad windows against REAL data.
Baseline = current Core-1x exposure (conviction-filtered v2 ensemble).
Variants layer on: (A) SMA200 trend filter, (B) turnover control (smooth+deadband),
(C) trend-following shorts in downtrends. Reports full-history metrics + the 3 windows.
"""
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le

ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
dates = pd.to_datetime(df["Date"])
close = df["close"].to_numpy()
sma200 = df["SMA200"].to_numpy()
n = len(df); i0 = 260
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)

def sim(exp, smooth=0, band=0.0, vol_target=0.60, dd_kill=0.30, dd_derisk=0.0, fee=0.0005, slip=0.003):
    e_in = exp.copy()
    if smooth and smooth > 1:
        e_in = pd.Series(e_in).ewm(span=smooth, adjust=False).mean().to_numpy()
    equity = peak = 500.0; held = 0.0
    eq = np.full(n, 500.0); turn_tot = 0.0
    for i in range(i0, n):
        tgt = e_in[i - 1] * 1.0
        if vol_target > 0 and rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt *= min(1.0, vol_target / rv[i - 1])
        if dd_kill > 0 and equity < peak * (1 - dd_kill):
            tgt *= 0.5
        if dd_derisk > 0:
            tgt *= max(0.1, 1.0 + (equity / peak - 1.0) / dd_derisk)
        e = tgt
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0):
            e = held
        ret = close[i] / close[i - 1] - 1
        turn = abs(e - held); turn_tot += turn
        equity *= (1 + e * ret); equity -= equity * turn * (fee + slip)
        held = e; peak = max(peak, equity); eq[i] = equity
    return pd.Series(eq[i0:], index=dates.iloc[i0:]), turn_tot / ((n - i0) / ANN)

# trend gate (decided at i-1, no look-ahead)
sma50 = df["SMA50"].to_numpy()
up = close > sma200
up50 = close > sma50
def trend_filter(exp, gate=None):
    g = up if gate is None else gate
    out = exp.copy()
    for i in range(n):
        if exp[i] > 0 and not g[i]:   # long blocked in downtrend
            out[i] = 0.0
        elif exp[i] < 0 and g[i]:     # short blocked in uptrend
            out[i] = 0.0
    return out
def trend_follow(exp):
    # with-trend conviction: in downtrend a 'long' signal becomes a short of same strength
    out = exp.copy()
    for i in range(n):
        if exp[i] > 0 and not up[i]:
            out[i] = -abs(exp[i])
        elif exp[i] < 0 and up[i]:
            out[i] = abs(exp[i])
    return out

def m(eq):
    r = eq.pct_change().dropna(); yrs = len(eq) / ANN
    cagr = (eq.iloc[-1] / 500) ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dn = r[r < 0].std(ddof=1) * np.sqrt(ANN) if (r < 0).sum() > 1 else float("nan")
    sortino = r.mean() * ANN / dn if dn and dn > 0 else float("nan")
    dd = (eq / eq.cummax() - 1).min()
    calmar = cagr / abs(dd) if dd < 0 else float("nan")
    return cagr, sh, sortino, dd, calmar

WINDOWS = [("W1 2017-12->2018-11", "2017-12-16", "2018-11-18"),
           ("W2 2021-10->2022-03", "2021-10-20", "2022-03-09"),
           ("W3 2025-05->2025-12", "2025-05-22", "2025-12-01")]

VARIANTS = [
    ("baseline (current)", expf, dict()),
    ("A: SMA200 filter", trend_filter(expf), dict()),
    ("B: turnover ctrl", expf, dict(smooth=5, band=0.15)),
    ("B+: strong turnover", expf, dict(smooth=8, band=0.22)),
    ("B + crash-derisk", expf, dict(smooth=5, band=0.15, dd_derisk=0.25)),
    ("A+B SMA200+turn", trend_filter(expf), dict(smooth=5, band=0.15)),
    ("A50+B SMA50+turn", trend_filter(expf, up50), dict(smooth=5, band=0.15)),
    ("C: trend-follow shorts", trend_follow(expf), dict()),
    ("C+B follow+turnover", trend_follow(expf), dict(smooth=5, band=0.15)),
    ("over-hedged A50+B+derisk", trend_filter(expf, up50), dict(smooth=6, band=0.18, dd_derisk=0.25)),
]

print(f"{'variant':26s} {'$500->':>12s} {'PnL($)':>12s} {'CAGR':>5s} {'Sharpe':>6s} {'Sortino':>7s} {'Calmar':>6s} {'maxDD':>6s} {'turn':>5s}")
for name, exp, kw in VARIANTS:
    eq, turn = sim(exp, **kw)
    cagr, sh, so, dd, cal = m(eq)
    pnl = eq.iloc[-1] - 500
    print(f"{name:26s} ${eq.iloc[-1]:>11,.0f} ${pnl:>11,.0f} {cagr*100:>4.0f}% {sh:>6.2f} {so:>7.2f} {cal:>6.2f} {dd*100:>5.0f}% {turn:>4.0f}x")
