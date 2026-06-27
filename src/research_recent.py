"""Honest research: does the 2021-2026 regime admit a REAL improvement over the leveraged Apex,
or is the unleveraged 1x the best we have? Test PRINCIPLED variants (rules derived from mechanism,
NOT parameters tuned to the recent window) and report each split by sub-period so front-loading
can't hide. No look-ahead (day i uses signal i-1). 50bp slippage on turnover.
"""
import numpy as np, pandas as pd, bisect, os
from live_engine import setup, ensemble_ctx, HERE
ANN = 365

df, reg0, memb = setup()
reg, emap, exp_raw = ensemble_ctx(df, memb)
dates = df["Date"].tolist(); n = len(df); i0 = 260
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
sma200 = df["SMA200"].to_numpy(); regA = np.array(reg, dtype=object); up = close > sma200
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy().copy()
for i in range(n):
    if e_in[i] < 0 and not (regA[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]):
        e_in[i] = 0.0
# gates (same as Apex)
p = os.path.join(HERE, "..", "data", "funding.csv")
fmap = dict(zip(*[pd.read_csv(p)[c] for c in ["date", "funding_rate"]])) if os.path.exists(p) else {}
funding = np.array([fmap.get(d, np.nan) for d in dates])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); fr = trk(funding); gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5

strong = np.array([r in ("STRONG_UP", "STRONG_DOWN") for r in reg])
chop = np.array([r in ("CHOP_HIVOL", "RANGE") for r in reg])
aligned = ((np.sign(e_in) > 0) & up) | ((np.sign(e_in) < 0) & ~up)

def sim(ein, cap_arr, slip=0.005, vt=1.5, dd_kill=0.30, band=0.15, fee=0.0005, maint=0.01):
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); E = np.zeros(n); liq = 0; trades = 0
    for i in range(i0, n):
        sig = ein[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; E[i] = held; continue
        e = sig * g * min(cap_arr[i - 1], vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint):
            eqv *= 0.01; liq += 1; held = 0.0; eq[i] = eqv; E[i] = 0.0; peak = max(peak, eqv); continue
        if (np.sign(e) != np.sign(held)) and not (e == held): trades += 1
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); E[i] = e; peak = max(peak, eqv)
    return eq, liq, trades

def at(ds): return min(bisect.bisect_left(dates, ds), n - 1)
def sub(eq, a, b):
    s = eq[a:b]; yrs = (b - a) / ANN
    cg = (s[-1] / s[0]) ** (1 / yrs) - 1 if s[0] > 0 and s[-1] > 0 else -1
    dd = (s / np.maximum.accumulate(s) - 1).min()
    r = pd.Series(s).pct_change().dropna(); sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    return s[-1] / s[0] - 1, cg, dd, sh

ones = np.ones(n)
sma50 = df["SMA50"].to_numpy()
cap_apex = np.where(aligned, 3.25, 3.0)
cap_strong = np.where(strong, 3.0, 1.0)                         # lever ONLY in confirmed strong trends
ein_flatchop = np.where(chop, 0.0, e_in)                        # go FLAT in chop, don't hold lagging
# --- classic, non-overfit PARTICIPATION signals (all 1x, vol-targeted) ---
ein_sma200 = np.where(up, 1.0, 0.0)                             # long when price > SMA200, else flat
ein_gc = np.where(sma50 > sma200, 1.0, 0.0)                     # golden-cross long-only
ein_ens_or_up = np.where(up, 1.0, e_in)                         # long in any uptrend; ensemble in downtrends
variants = [
    ("Apex (lev 3.25/3)", e_in, cap_apex),
    ("1x spot (ensemble)", e_in, ones),
    ("cap 2.0 flat", e_in, ones * 2.0),
    ("lever-only-strong-trend (3x/1x)", e_in, cap_strong),
    ("Apex + flat-in-chop", ein_flatchop, cap_apex),
    ("SMA200 long-only 1x", ein_sma200, ones),
    ("golden-cross long-only 1x", ein_gc, ones),
    ("uptrend-long + ens-downtrend 1x", ein_ens_or_up, ones),
]
a17, b20 = at("2017-09-01"), at("2021-01-01"); a21, bend = at("2021-01-01"), n - 1
hdr = f"{'variant':32s} {'FULL $':>13s} {'fDD':>5s} | {'17-20 ret':>9s} {'DD':>5s} | {'21-26 CAGR':>10s} {'21-26 DD':>8s} {'Shrp':>5s} {'liq':>4s}"
print(hdr); print("-" * len(hdr))
for name, ein, cap in variants:
    eq, liq, tr = sim(ein, cap)
    full = eq[i0:]; fdd = (full / np.maximum.accumulate(full) - 1).min()
    r17, c17, d17, s17 = sub(eq, a17, b20)
    r21, c21, d21, s21 = sub(eq, a21, bend)
    print(f"{name:32s} ${full[-1]:>11,.0f} {fdd*100:>4.0f}% | {r17*100:>+8.0f}% {d17*100:>4.0f}% | {c21*100:>+9.0f}% {d21*100:>7.0f}% {s21:>5.2f} {liq:>4d}")

# BTC buy & hold recent baseline
bh = close / close[a21]; rb, cb, dbb, sbb = sub(close, a21, bend)
print("-" * len(hdr))
print(f"{'BTC buy & hold (recent)':32s} {'':>13s} {'':>5s} | {'':>9s} {'':>5s} | {cb*100:>+9.0f}% {dbb*100:>7.0f}% {sbb:>5.2f}")
