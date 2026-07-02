"""Push overall win rate >50% while keeping @50bp profit, on the trend-aligned 5/3 model.
Levers: short-quality gate (only short confirmed downtrends), higher conviction threshold,
heavier smoothing (fewer whipsaw trades), long-only. Reports win% overall/long/short + profit.
"""
import os
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le
ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
sma200 = df["SMA200"].to_numpy(); ADX = df["ADX"].to_numpy()
n = len(df); i0 = 260; dstr = df["Date"].tolist(); dates = pd.to_datetime(df["Date"])
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
regA = np.array(reg, dtype=object)
HERE = os.path.dirname(os.path.abspath(__file__))
def lmap(p, col):
    if not os.path.exists(p): return {}
    f = pd.read_csv(p); return dict(zip(f.iloc[:, 0].astype(str), f[col]))
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); fr = trk(funding)
gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5
up = close > sma200

def build_ein(conv, short_gate, smooth, long_only):
    ef = np.where(np.abs(exp_raw) >= conv, exp_raw, 0.0)
    e = pd.Series(ef).ewm(span=smooth, adjust=False).mean().to_numpy().copy()
    for i in range(n):
        if e[i] < 0:
            if long_only: e[i] = 0.0
            elif short_gate == "downtrend" and not (regA[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]): e[i] = 0.0
            elif short_gate == "strong" and not (regA[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i] and ADX[i] > 25): e[i] = 0.0
    return e

def sim(e_in, vt=1.5, slip=0.005, dd_kill=0.30, band=0.15, fee=0.0005, maint=0.01):
    sgn = np.sign(e_in); aligned = ((sgn > 0) & up) | ((sgn < 0) & ~up); cap = np.where(aligned, 5.0, 3.0)
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); E = np.zeros(n)
    for i in range(i0, n):
        sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; E[i] = held; continue
        ee = sig * g * min(cap[i - 1], vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): ee *= 0.5
        if band > 0 and abs(ee - held) < band and not (ee == 0 and held != 0): ee = held
        adv = (-(low[i] / close[i - 1] - 1)) if ee > 0 else ((high[i] / close[i - 1] - 1) if ee < 0 else 0.0)
        if ee != 0 and abs(ee) * max(adv, 0) >= (1 - maint):
            eqv *= 0.01; held = 0.0; eq[i] = eqv; E[i] = 0.0; peak = max(peak, eqv); continue
        eqv *= (1 + ee * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(ee - held) * (fee + slip)
        held = ee; eq[i] = max(eqv, 1e-9); E[i] = ee; peak = max(peak, eqv)
    return eq, E
def spells(eq, E):
    i = i0; tr = []
    while i < n:
        s = 1 if E[i] > 0 else (-1 if E[i] < 0 else 0)
        if s == 0: i += 1; continue
        j = i
        while j + 1 < n and (1 if E[j + 1] > 0 else (-1 if E[j + 1] < 0 else 0)) == s: j += 1
        f0 = eq[i - 1] if i > 0 else 500.0
        tr.append((s, eq[j] / f0 - 1)); i = j + 1
    return tr
def report(nm, conv, sg, sm, lo):
    e_in = build_ein(conv, sg, sm, lo); eq, E = sim(e_in); tr = spells(eq, E)
    allp = np.array([t[1] for t in tr])
    L = [t[1] for t in tr if t[0] > 0]; S = [t[1] for t in tr if t[0] < 0]
    ow = (allp > 0).mean() * 100 if len(tr) else 0
    lw = (np.array(L) > 0).mean() * 100 if L else 0; sw = (np.array(S) > 0).mean() * 100 if S else 0
    s = pd.Series(eq[i0:], index=dates.iloc[i0:].values); dd = (s / s.cummax() - 1).min()
    r = s.pct_change().dropna(); yrs = len(s) / ANN; cagr = (s.iloc[-1] / 500) ** (1 / yrs) - 1
    print(f"{nm:34s} win {ow:3.0f}% (L{lw:3.0f}%/{len(L)} S{sw:3.0f}%/{len(S)}) | $50bp {s.iloc[-1]:>12,.0f} Calm {cagr/abs(dd):>4.2f} DD {dd*100:>4.0f}%")

print(f"{'variant':34s} {'win rates + counts':28s}   {'profit / risk'}")
report("BASE trend-aligned 5/3", 0.4, None, 5, False)
report("+short=downtrend only", 0.4, "downtrend", 5, False)
report("+short=strong-dn(ADX>25)", 0.4, "strong", 5, False)
report("+short=downtrend +sm10", 0.4, "downtrend", 10, False)
report("LONG-ONLY", 0.4, None, 5, True)
report("LONG-ONLY +sm10", 0.4, None, 10, True)
report("conv0.55 +short=downtrend", 0.55, "downtrend", 5, False)
report("conv0.6 +short=strong +sm10", 0.6, "strong", 10, False)
report("conv0.55 +short=strong +sm12", 0.55, "strong", 12, False)

print("\n=== conviction sweep (short=downtrend only, sm5) — find the >50% crossover ===")
for conv in [0.45,0.50,0.55,0.60,0.65,0.70]:
    report(f"conv{conv} +short=downtrend", conv, "downtrend", 5, False)
