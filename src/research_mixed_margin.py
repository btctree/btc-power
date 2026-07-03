"""MIXED MARGIN LEVELS: different cap for LONG vs SHORT positions, on the live Max B stack
(floor + Pi Cycle), 50bp. Hypothesis (pre-registered, from short win-rate 31-38% + squeeze risk +
the M1vM5 5x/2x precedent): lower short caps should help. Grid of (longCap, shortCap); report
full $, DD, 21+ CAGR, hard years, liquidations. Winner re-checked at 0bp. Selection-risk note:
small grid, one axis, directional hypothesis stated before running.
"""
import os, numpy as np, pandas as pd
from live_engine import setup, ensemble_ctx, HERE
ANN = 365
df, reg0, memb = setup(); reg, emap, exp_raw = ensemble_ctx(df, memb)
dates = pd.to_datetime(df["Date"]); dstr = df["Date"].tolist(); n = len(df); i0 = 260
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()
def lmap(p, c): return dict(zip(pd.read_csv(p).iloc[:, 0].astype(str), pd.read_csv(p)[c])) if os.path.exists(p) else {}
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); fr = trk(funding); gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5
c_ = pd.Series(close)
wma200 = c_.rolling(1400).mean(); below_200w = (c_ < wma200).shift(1).fillna(False).to_numpy()
m111 = c_.rolling(111).mean(); m350x2 = 2 * c_.rolling(350).mean()
above = (m111 > m350x2).to_numpy(); pi_alarm = np.zeros(n, bool); _lc = -10**9
for i in range(1, n):
    if above[i] and not above[i - 1]: _lc = i
    if i - _lc <= 365: pi_alarm[i] = True
pi_alarm = np.roll(pi_alarm, 1); pi_alarm[0] = False

def sim(capL, capS, slip=0.005, vt=1.5, dd_kill=0.30, band=0.15, fee=0.0005, maint=0.01):
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); liq = 0
    for i in range(i0, n):
        sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if sig < 0 and below_200w[i]: g = 0.0
        if pi_alarm[i]: g *= 0.5
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        cap = capL if sig > 0 else capS
        e = sig * g * min(cap, vt / rv[i - 1]) if cap > 0 else 0.0
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint): eqv *= 0.01; liq += 1; held = 0.0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv)
    return eq, liq

def rep(eq):
    s = pd.Series(eq[i0:], index=dates[i0:])
    dd = (s / s.cummax() - 1).min()
    e2 = s[s.index >= "2021-01-01"]; c2 = (e2.iloc[-1] / e2.iloc[0]) ** (ANN / len(e2)) - 1
    ys = {}
    for y in (2018, 2022, 2024, 2025):
        seg = s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]
        if len(seg) > 20: ys[y] = seg.iloc[-1] / seg.iloc[0] - 1
    return float(s.iloc[-1]), c2, dd, ys

print(f"{'longCap/shortCap':>16} {'FULL $ @50bp':>13} {'21+':>6} {'maxDD':>6} {'liq':>4} | {'2018':>6} {'2022':>6} {'2024':>6} {'2025':>6}")
best = None
for L, S in [(5, 5), (5, 3), (5, 2), (5, 1), (5, 0), (4, 2), (3, 2), (3, 5)]:
    eq, liq = sim(L, S); f, c2, dd, ys = rep(eq)
    tag = "  <= LIVE Max B" if (L, S) == (5, 5) else ""
    if best is None or f > best[0]: best = (f, L, S)
    print(f"{L}x long / {S}x short {'':>0} ${f:>12,.0f} {c2*100:>+5.0f}% {dd*100:>5.0f}% {liq:>4} | {ys.get(2018,0)*100:>+5.0f}% {ys.get(2022,0)*100:>+5.0f}% {ys.get(2024,0)*100:>+5.0f}% {ys.get(2025,0)*100:>+5.0f}%{tag}")
f, L, S = best
eq0, _ = sim(L, S, slip=0.0)
print(f"\nbest by final: {L}x/{S}x -> ${f:,.0f} @50bp | same config @0bp: ${rep(eq0)[0]:,.0f}")
