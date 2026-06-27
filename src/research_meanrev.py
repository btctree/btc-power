"""Different approach: add a MEAN-REVERSION sleeve that trades the RANGING regimes (where the
trend-follower stands aside / bleeds), combined with the trend ensemble in trending regimes.
Hypothesis: MR returns are ~orthogonal to trend returns, so the blend lifts recent Sharpe without
leverage. Tested HONESTLY: rules are classic (RSI oversold/overbought inside a confirmed range),
NOT tuned to 2021-26; reported split by sub-period + correlation of the two sleeves. 1x, 50bp.
"""
import numpy as np, pandas as pd, bisect, os
from live_engine import setup, ensemble_ctx, HERE
ANN = 365
df, reg0, memb = setup(); reg, emap, exp_raw = ensemble_ctx(df, memb)
dates = df["Date"].tolist(); n = len(df); i0 = 260
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
sma200 = df["SMA200"].to_numpy(); rsi = df["RSI"].to_numpy(); up = close > sma200
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy().copy()
for i in range(n):
    if e_in[i] < 0 and not (reg[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]):
        e_in[i] = 0.0
ein_trend = np.clip(e_in, -1, 1)                          # 1x trend sleeve

ranging = np.array([r in ("RANGE", "CHOP_HIVOL") for r in reg])
# classic mean-reversion state machine, ACTIVE only inside confirmed ranges
mr = np.zeros(n); pos = 0
for i in range(n):
    if not ranging[i]:
        pos = 0
    else:
        if pos == 0:
            if rsi[i] < 35: pos = 1
            elif rsi[i] > 65: pos = -1
        elif pos == 1 and rsi[i] > 50: pos = 0
        elif pos == -1 and rsi[i] < 50: pos = 0
    mr[i] = pos
ein_combo = np.where(ranging, mr, ein_trend)             # MR in chop, trend elsewhere (1x total)

def sim(ein, slip=0.005, vt=1.5, dd_kill=0.30, band=0.12, fee=0.0005):
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); E = np.zeros(n)
    for i in range(i0, n):
        sig = ein[i - 1]
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; E[i] = held; continue
        e = sig * min(1.0, vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); E[i] = e; peak = max(peak, eqv)
    return eq

def at(ds): return min(bisect.bisect_left(dates, ds), n - 1)
def sub(eq, a, b):
    s = eq[a:b]; yrs = (b - a) / ANN
    cg = (s[-1] / s[0]) ** (1 / yrs) - 1 if s[0] > 0 and s[-1] > 0 else -1
    dd = (s / np.maximum.accumulate(s) - 1).min()
    r = pd.Series(s).pct_change().dropna(); sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    return s[-1] / s[0] - 1, cg, dd, sh

a17, b20, a21, bend = at("2017-09-01"), at("2021-01-01"), at("2021-01-01"), n - 1
rows = [("1x trend (current)", ein_trend), ("MR-in-chop only", np.where(ranging, mr, 0.0)),
        ("trend + MR blend", ein_combo)]
hdr = f"{'system':22s} {'FULL $':>11s} | {'17-20 CAGR':>10s} {'DD':>5s} {'Shrp':>5s} | {'21-26 CAGR':>10s} {'DD':>5s} {'Shrp':>5s}"
print(hdr); print("-" * len(hdr))
eqs = {}
for name, ein in rows:
    eq = sim(ein); eqs[name] = eq
    r1, c1, d1, s1 = sub(eq, a17, b20); r2, c2, d2, s2 = sub(eq, a21, bend)
    print(f"{name:22s} ${eq[-1]:>9,.0f} | {c1*100:>+9.0f}% {d1*100:>4.0f}% {s1:>5.2f} | {c2*100:>+9.0f}% {d2*100:>4.0f}% {s2:>5.2f}")
# correlation of the two sleeves' daily returns (recent) — the whole premise
rt = pd.Series(sim(ein_trend)).pct_change(); rm = pd.Series(sim(np.where(ranging, mr, 0.0))).pct_change()
corr_full = rt.iloc[i0:].corr(rm.iloc[i0:]); corr_rec = rt.iloc[a21:].corr(rm.iloc[a21:])
print("-" * len(hdr))
print(f"trend vs MR daily-return correlation: full {corr_full:+.2f} | recent {corr_rec:+.2f}  (near 0 = good diversification)")
print(f"MR active days: {int(ranging[i0:].sum())}/{n-i0} ({ranging[i0:].mean()*100:.0f}% of the time)")
