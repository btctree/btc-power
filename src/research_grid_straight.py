"""FULL grid: every daily-BTC signal family x cap levels x dollar-gate, at 50bp, scored on SIZE
(full-period $) AND STRAIGHTNESS (2021+ CAGR, late/early ratio, log-R2). Answers: does ANY tested
model + cap logic give $1M+ with a stable straight growth line?
Signals: ens5 (Growth family), apex-sig (short-selective), sm10 (Smooth family), ens5-vt2 (Aggressive
family), apex trend-aligned cap. Excluded: intraday/1-min systems (different engine/data; full-period
honest finals ~$45-78k, far below $1M) and in-sample cycle timing (look-ahead).
Multiple-testing caveat: ~34 configs -> the exact best is selection-noisy; trust PATTERNS not winners.
"""
import os, numpy as np, pandas as pd
from live_engine import setup, ensemble_ctx, HERE
from global_engine import fetch_yahoo
ANN = 365
df, reg0, memb = setup(); reg, emap, exp_raw = ensemble_ctx(df, memb)
dates = pd.to_datetime(df["Date"]); dstr = df["Date"].tolist(); n = len(df); i0 = 260
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy(); sma200 = df["SMA200"].to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
def lmap(p, c): return dict(zip(pd.read_csv(p).iloc[:, 0].astype(str), pd.read_csv(p)[c])) if os.path.exists(p) else {}
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); fr = trk(funding); gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5
u = fetch_yahoo("UUP", refresh=False)
uup = pd.Series(u["close"].values, index=pd.to_datetime(u["date"])).reindex(dates).ffill()
dollar_strong = (uup > uup.rolling(200).mean()).shift(1).fillna(False).to_numpy()

S_ens5 = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()
S_apex = S_ens5.copy()
for i in range(n):
    if S_apex[i] < 0 and not (reg[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]): S_apex[i] = 0.0
S_sm10 = pd.Series(expf).ewm(span=10, adjust=False).mean().to_numpy()
up = close > sma200; sgA = np.sign(S_apex)
cap_ta = np.where(((sgA > 0) & up) | ((sgA < 0) & ~up), 3.25, 3.0)

def sim(sig, cap, vt, band, dgate=0.0, slip=0.005, dd_kill=0.30, fee=0.0005, maint=0.01):
    caparr = cap if hasattr(cap, "__len__") else None
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        s = sig[i - 1]; g = gl[i - 1] if s > 0 else (gs[i - 1] if s < 0 else 1.0)
        if dgate and dollar_strong[i - 1]: g *= dgate
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        e = s * g * min(caparr[i - 1] if caparr is not None else cap, vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint): eqv *= 0.01; held = 0.0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv)
    return eq

def score(eq):
    s = pd.Series(eq[i0:], index=dates[i0:])
    e1 = s[s.index < "2021-01-01"]; e2 = s[s.index >= "2021-01-01"]
    c1 = (e1.iloc[-1] / e1.iloc[0]) ** (ANN / len(e1)) - 1
    c2 = (e2.iloc[-1] / e2.iloc[0]) ** (ANN / len(e2)) - 1
    dd = (s / s.cummax() - 1).min()
    y = np.log(s.to_numpy()); x = np.arange(len(y)); r2 = np.corrcoef(x, y)[0, 1] ** 2
    return float(s.iloc[-1]), c1, c2, (c2 / c1 if c1 > 0 else np.nan), r2, dd

FAM = [("ens5", S_ens5, 1.5, 0.15), ("apex-sig", S_apex, 1.5, 0.15),
       ("sm10", S_sm10, 1.5, 0.25), ("ens5-vt2", S_ens5, 2.0, 0.25)]
rows = []
for fname, sig, vt, band in FAM:
    for cap in (1, 2, 3, 5):
        for dg in (0.0, 0.5):
            eq = sim(sig, cap, vt, band, dg)
            rows.append((f"{fname} cap{cap}{'+dg' if dg else ''}",) + score(eq))
for dg in (0.0, 0.5):
    eq = sim(S_apex, cap_ta, 1.5, 0.15, dg)
    rows.append((f"apex-TA 3.25/3{'+dg' if dg else ''}",) + score(eq))

rows.sort(key=lambda r: -(r[3] / r[2] if r[2] > 0 else 0))   # sort by late/early ratio
print(f"{'config':22s} {'FULL $':>12} {'14-20':>7} {'21+':>6} {'late/early':>10} {'logR2':>6} {'maxDD':>6}")
for nm, f, c1, c2, ratio, r2, dd in rows:
    star = "  *" if (f >= 1_000_000 and (ratio == ratio and ratio >= 0.3)) else ""
    print(f"{nm:22s} ${f:>11,.0f} {c1*100:>+6.0f}% {c2*100:>+5.0f}% {ratio:>10.2f} {r2:>6.2f} {dd*100:>5.0f}%{star}")
hits = [r for r in rows if r[1] >= 1_000_000 and (r[4] == r[4] and r[4] >= 0.3)]
print(f"\n$1M+ AND late/early>=0.3: {len(hits)} configs" + ("" if hits else "  -> NONE (the frontier holds)"))
best_m = max(rows, key=lambda r: r[1]); best_s = max(rows, key=lambda r: (r[4] if r[4] == r[4] else -1))
print(f"biggest: {best_m[0]} ${best_m[1]:,.0f} (ratio {best_m[4]:.2f}) | straightest: {best_s[0]} ratio {best_s[4]:.2f} (${best_s[1]:,.0f})")
