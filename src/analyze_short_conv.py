"""Does short win rate rise with a CONVICTION filter on shorts (vs regime-only)? And what does it
cost in trade count (the >200 in&out constraint)? Constrained trend-aligned 3.25/3 base.
"""
import numpy as np, pandas as pd
import stable_combo as sc, live_engine as le
ANN = 365
df, reg0, memb = sc.prep(); reg, emap, exp_raw = le.ensemble_ctx(df, memb)
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
sma200 = df["SMA200"].to_numpy(); n = len(df); i0 = 260; dates = pd.to_datetime(df["Date"]); dstr = df["Date"].tolist()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN); up = close > sma200; regA = np.array(reg, dtype=object)
def lmap(p, c):
    f = pd.read_csv(p); return dict(zip(f.iloc[:, 0].astype(str), f[c]))
funding = np.array([lmap("../data/funding.csv", "funding_rate").get(d, np.nan) for d in dstr])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); frr = trk(funding)
gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if frr[i] == frr[i]:
        if frr[i] > 0.90: gl[i] *= 0.5
        if frr[i] < 0.10: gs[i] *= 0.5
def build(short_conv):
    ef = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
    e = pd.Series(ef).ewm(span=5, adjust=False).mean().to_numpy().copy()
    for i in range(n):
        if e[i] < 0:
            ok = (regA[i] in ("STRONG_DOWN", "TREND_DOWN")) and (close[i] < sma200[i]) and (abs(exp_raw[i]) >= short_conv)
            if not ok: e[i] = 0.0
    return e
def run(e_in, capA=3.25, slip=0.005):
    sgn = np.sign(e_in); aligned = ((sgn > 0) & up) | ((sgn < 0) & ~up); cap = np.where(aligned, capA, 3.0)
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); E = np.zeros(n); liq = 0
    for i in range(i0, n):
        sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; E[i] = held; continue
        e = sig * g * min(cap[i - 1], 1.5 / rv[i - 1])
        if eqv < peak * 0.70: e *= 0.5
        if abs(e - held) < 0.15 and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= 0.99: eqv *= 0.01; liq += 1; held = 0.0; eq[i] = eqv; E[i] = 0; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (0.0005 + slip)
        held = e; eq[i] = max(eqv, 1e-9); E[i] = e; peak = max(peak, eqv)
    s = pd.Series(eq[i0:], index=dates.iloc[i0:].values); r = s.pct_change().dropna(); yrs = len(s) / ANN
    cagr = (s.iloc[-1] / 500) ** (1 / yrs) - 1; sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)); dd = (s / s.cummax() - 1).min()
    i = i0; tr = []
    while i < n:
        sg = 1 if E[i] > 0 else (-1 if E[i] < 0 else 0)
        if sg == 0: i += 1; continue
        j = i
        while j + 1 < n and (1 if E[j+1]>0 else (-1 if E[j+1]<0 else 0)) == sg: j += 1
        f0 = eq[i-1] if i > 0 else 500.0; tr.append((sg, eq[j]/f0-1)); i = j + 1
    allp = np.array([t[1] for t in tr]); L = [t for t in tr if t[0]>0]; S = [t for t in tr if t[0]<0]
    ow = (allp>0).mean(); lw = (np.array([t[1] for t in L])>0).mean() if L else 0; sw = (np.array([t[1] for t in S])>0).mean() if S else 0
    return s.iloc[-1], cagr/abs(dd), sh, dd, len(tr)*2, len(S), ow, lw, sw, liq
print(f"{'short filter':30s} {'$@50bp':>11s} {'Calm':>5s} {'Shrp':>5s} {'maxDD':>6s} {'in&out':>6s} {'#S':>4s} {'all/L/S win':>14s}  PASS?")
for sc_, lbl in [(0.40, "confirmed-dn (regime only)"), (0.50, "confirmed-dn + conv0.50"), (0.55, "confirmed-dn + conv0.55"), (0.60, "confirmed-dn + conv0.60")]:
    f, cal, sh, dd, io, nS, ow, lw, sw, liq = run(build(sc_))
    pas = (io > 200) and (liq == 0) and (dd >= -0.55) and (f >= 1_000_000) and (cal > 1) and (sh > 1)
    print(f"{lbl:30s} ${f:>10,.0f} {cal:>5.2f} {sh:>5.2f} {dd*100:>5.0f}% {io:>6d} {nS:>4d} {ow*100:>3.0f}/{lw*100:.0f}/{sw*100:.0f}%   {'PASS' if pas else 'no'}")
