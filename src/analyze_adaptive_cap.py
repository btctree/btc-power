"""Merge cap3 & cap5 via a REGIME/TREND-ADAPTIVE cap: high leverage only where it's safe.
Tests: flat cap4; regime-cap (5 in strong trends, 3 else); trend-aligned (5 when position agrees
with SMA200 trend, low when counter-trend); vol-cap; conviction-cap. vs cap3 and cap5(A).
Honest: 2014+, VOL+FUND gates, vt1.5, sm5, bd0.15, dd-kill, slippage, liquidation.
"""
import os
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le
ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
sma200 = df["SMA200"].to_numpy(); n = len(df); i0 = 260; dstr = df["Date"].tolist(); dates = pd.to_datetime(df["Date"])
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
HERE = os.path.dirname(os.path.abspath(__file__))
def lmap(p, col):
    if not os.path.exists(p): return {}
    f = pd.read_csv(p); return dict(zip(f.iloc[:, 0].astype(str), f[col]))
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trail_rank(a, w=365):
    return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vol_rank = trail_rank(rv); fund_rank = trail_rank(funding)
gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vol_rank[i] == vol_rank[i] and vol_rank[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fund_rank[i] == fund_rank[i]:
        if fund_rank[i] > 0.90: gl[i] *= 0.5
        if fund_rank[i] < 0.10: gs[i] *= 0.5
e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()
sgn = np.sign(e_in)
up200 = close > sma200
TREND = np.isin(np.array(reg, dtype=object), ["STRONG_UP","TREND_UP","STRONG_DOWN","TREND_DOWN"])

# ---- cap arrays (decided per day) ----
caps = {}
caps["cap3 (ref)"] = np.full(n, 3.0)
caps["cap4 flat"] = np.full(n, 4.0)
caps["cap5 = A (ref)"] = np.full(n, 5.0)
caps["regime 5/3 (strong-trend)"] = np.where(TREND, 5.0, 3.0)
aligned = ((sgn > 0) & up200) | ((sgn < 0) & ~up200)
caps["trend-aligned 5 / 2.5"] = np.where(aligned, 5.0, 2.5)
caps["trend-aligned 5 / 3"] = np.where(aligned, 5.0, 3.0)
caps["vol-cap 5(calm)/3(vol)"] = np.where(vol_rank < 0.5, 5.0, 3.0)
caps["conviction 5(hi)/3(lo)"] = np.where(np.abs(e_in) >= 0.6, 5.0, 3.0)
caps["aligned+calm 5 else 3"] = np.where(aligned & (vol_rank < 0.6), 5.0, 3.0)

def sim(caparr, slip, vt=1.5, dd_kill=0.30, band=0.15, fee=0.0005, maint=0.01):
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); liq = 0; me = 0.0
    for i in range(i0, n):
        sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        e = sig * g * min(caparr[i - 1], vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint):
            eqv *= 0.01; liq += 1; held = 0.0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv); me = max(me, abs(e))
    return eq, liq, me
WIN = [("2017-12-16","2018-11-18"),("2021-10-20","2022-03-09"),("2025-05-22","2025-12-01")]
def stats(eq):
    s = pd.Series(eq[i0:], index=dates.iloc[i0:].values); r = s.pct_change().dropna(); yrs = len(s) / ANN
    cagr = (s.iloc[-1] / 500) ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dd = (s / s.cummax() - 1).min(); ww = [(s.loc[a:b] / s.loc[a:b].cummax() - 1).min() * 100 for a, b in WIN]
    return s.iloc[-1], (cagr / abs(dd) if dd < 0 else 0), sh, dd, ww
print(f"{'cap scheme':28s} {'$@0bp':>13s} {'$@50bp':>12s} {'Calm':>5s} {'Shrp':>5s} {'maxDD':>6s} {'liq':>3s} {'maxX':>5s} | W1/W2/W3")
for nm, ca in caps.items():
    eq0, _, _ = sim(ca, 0.0); eq5, liq, me = sim(ca, 0.005)
    f0 = eq0[-1]; f5, cal, sh, dd, ww = stats(eq5)
    print(f"{nm:28s} ${f0:>12,.0f} ${f5:>11,.0f} {cal:>5.2f} {sh:>5.2f} {dd*100:>5.0f}% {liq:>3d} {me:>4.1f}x | {ww[0]:>3.0f}/{ww[1]:>3.0f}/{ww[2]:>3.0f}%")
