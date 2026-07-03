"""Win ratio of the live Growth A + honest options to make 2021+ compound upward at 50bp.
Same engine as growth_engine.py; varies only the RISK CONTROLS (cap / vol-target / dollar gate) —
no signal re-mining. Reports win% (all/long/short), trade count, full-period and 2021+ CAGR/DD/Sharpe.
"""
import os, numpy as np, pandas as pd
from live_engine import setup, ensemble_ctx, HERE
from global_engine import fetch_yahoo
ANN = 365
df, reg0, memb = setup(); reg, emap, exp_raw = ensemble_ctx(df, memb)
dates = pd.to_datetime(df["Date"]); dstr = df["Date"].tolist(); n = len(df); i0 = 260
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
esm = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()
def lmap(p, c): return dict(zip(pd.read_csv(p).iloc[:, 0].astype(str), pd.read_csv(p)[c])) if os.path.exists(p) else {}
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); fr = trk(funding); gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5
# dollar gate (the one cross-validated macro hint)
u = fetch_yahoo("UUP", refresh=False)
uup = pd.Series(u["close"].values, index=pd.to_datetime(u["date"])).reindex(dates).ffill()
dollar_strong = (uup > uup.rolling(200).mean()).shift(1).fillna(False).to_numpy()

def sim(cap, vt, band=0.15, slip=0.005, dd_kill=0.30, fee=0.0005, maint=0.01, dgate=0.0):
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); E = np.zeros(n)
    for i in range(i0, n):
        sig = esm[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if dgate and dollar_strong[i - 1]: g *= dgate
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; E[i] = held; continue
        e = sig * g * min(cap, vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint): eqv *= 0.01; held = 0.0; eq[i] = eqv; E[i] = 0.0; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); E[i] = e; peak = max(peak, eqv)
    return eq, E

def spells(eq, E):
    out = []; i = i0
    while i < n:
        s = 1 if E[i] > 0 else (-1 if E[i] < 0 else 0)
        if s == 0: i += 1; continue
        j = i
        while j + 1 < n and (1 if E[j + 1] > 0 else (-1 if E[j + 1] < 0 else 0)) == s: j += 1
        f0 = eq[i - 1] if i > 0 else 500.0
        out.append((s, eq[j] / f0 - 1, dates[i])); i = j + 1
    return out

def stats(eq, a=None):
    s = pd.Series(eq, index=dates)
    if a: s = s[s.index >= a]
    r = s.pct_change().dropna(); yrs = len(s) / ANN
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1 if s.iloc[0] > 0 else -1
    dd = (s / s.cummax() - 1).min(); sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    return cagr, dd, sh, s.iloc[-1]

cfgs = [("Growth A (LIVE: cap5 vt1.5)", dict(cap=5, vt=1.5)),
        ("cap3 vt1.5", dict(cap=3, vt=1.5)),
        ("cap2 vt1.5", dict(cap=2, vt=1.5)),
        ("cap5 vt1.0", dict(cap=5, vt=1.0)),
        ("Growth A + dollar-gate 0.5", dict(cap=5, vt=1.5, dgate=0.5)),
        ("cap2 + dollar-gate 0.5", dict(cap=2, vt=1.5, dgate=0.5)),
        ("Core 1x (cap1)", dict(cap=1, vt=1.5))]
print(f"{'config':28s} {'win%':>5} {'L%':>4} {'S%':>4} {'#tr':>4} | {'FULL $':>12} {'DD':>5} | {'21+ CAGR':>8} {'21+ DD':>6} {'21+ Shp':>7} {'21+ $x':>7}")
for name, kw in cfgs:
    eq, E = sim(**kw); tr = spells(eq, E)
    allr = [t[1] for t in tr]; L = [t[1] for t in tr if t[0] > 0]; S = [t[1] for t in tr if t[0] < 0]
    w = np.mean([x > 0 for x in allr]) * 100; wl = np.mean([x > 0 for x in L]) * 100 if L else 0; ws = np.mean([x > 0 for x in S]) * 100 if S else 0
    cf, ddf, shf, ff = stats(eq); c2, dd2, sh2, _ = stats(eq, "2021-01-01")
    s21 = pd.Series(eq, index=dates); mult21 = s21.iloc[-1] / s21[s21.index >= "2021-01-01"].iloc[0]
    print(f"{name:28s} {w:>4.0f}% {wl:>3.0f}% {ws:>3.0f}% {len(tr):>4} | ${ff:>11,.0f} {ddf*100:>4.0f}% | {c2*100:>+7.0f}% {dd2*100:>5.0f}% {sh2:>7.2f} {mult21:>6.2f}x")

# ---- STRAIGHTNESS ANALYSIS: is there a config with $1M+ AND a stable straight log-line? ----
print("\nSTRAIGHTNESS vs SIZE (log-equity):")
print(f"{'config':28s} {'FULL $':>12} {'14-20 CAGR':>10} {'21+ CAGR':>9} {'late/early':>10} {'logR2':>6}")
for name, kw in cfgs:
    eq, E = sim(**kw); s = pd.Series(eq[i0:], index=dates[i0:])
    e1 = s[s.index < "2021-01-01"]; e2 = s[s.index >= "2021-01-01"]
    c1 = (e1.iloc[-1] / e1.iloc[0]) ** (ANN / len(e1)) - 1
    c2 = (e2.iloc[-1] / e2.iloc[0]) ** (ANN / len(e2)) - 1
    y = np.log(s.to_numpy()); x = np.arange(len(y))
    r2 = np.corrcoef(x, y)[0, 1] ** 2
    ratio = (c2 / c1) if c1 > 0 else float("nan")
    print(f"{name:28s} ${s.iloc[-1]:>11,.0f} {c1*100:>+9.0f}% {c2*100:>+8.0f}% {ratio:>10.2f} {r2:>6.2f}")
print("\n(straight line = late/early near 1.00 and logR2 near 1.0; $1M+ = FULL $ >= 1,000,000)")
