"""NEW MECHANISM: funding-carry sleeve on idle capital. When the trend model isn't fully deployed,
idle equity goes into delta-neutral cash-and-carry (long spot + short perp) collecting funding when
positive. Income, not direction -> should lift the FLAT stretches (2021+) without touching the trend
engine. Honest: carry only when funding>0 (unwind otherwise, cost charged on carry notional changes,
20bp round-trip both legs), funding data real (data/funding.csv), no carry before data starts.
Compare: Growth A and cap2+dollar-gate, each with/without carry. Report 2021+ yearly + straightness.
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
fmap = lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate")
funding = np.array([fmap.get(d, np.nan) for d in dstr])
fs = pd.Series(funding, index=dates).dropna()
print(f"funding data: {fs.index[0].date()} -> {fs.index[-1].date()} | mean daily {fs.mean()*100:.4f}% "
      f"(~{fs.mean()*365*100:.1f}%/yr) | positive days {(fs>0).mean()*100:.0f}%")
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
# carry availability: funding known yesterday, positive, and smoothed positive (avoid churn)
f_sm = pd.Series(funding, index=dates).rolling(7, min_periods=3).mean().shift(1).to_numpy()
carry_on = (f_sm > 0)
f_yday = pd.Series(funding, index=dates).shift(1).to_numpy()

def sim(cap, vt, band=0.15, slip=0.005, dd_kill=0.30, fee=0.0005, maint=0.01, dgate=0.0, carry=False, carry_cost=0.002):
    eqv = peak = 500.0; held = 0.0; heldc = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        sig = esm[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if dgate and dollar_strong[i - 1]: g *= dgate
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        e = sig * g * min(cap, vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint):
            eqv *= 0.01; held = 0.0; heldc = 0.0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        if carry:
            # carry on IDLE capital, wide re-size threshold (0.3) so it can't churn
            idle = max(0.0, 1.0 - abs(e))
            c_t = idle if (carry_on[i - 1] and idle > 0.25) else 0.0
            if abs(c_t - heldc) > 0.3 or (c_t == 0 and heldc > 0):       # re-size carry (both legs cost)
                eqv -= eqv * abs(c_t - heldc) * carry_cost; heldc = c_t
            if heldc > 0 and f_yday[i] == f_yday[i]:
                eqv *= (1 + heldc * max(f_yday[i], -0.0005))             # collect funding (tiny neg tolerated)
        held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv)
    return eq

def rep(eq):
    s = pd.Series(eq[i0:], index=dates[i0:])
    e1 = s[s.index < "2021-01-01"]; e2 = s[s.index >= "2021-01-01"]
    c1 = (e1.iloc[-1] / e1.iloc[0]) ** (ANN / len(e1)) - 1; c2 = (e2.iloc[-1] / e2.iloc[0]) ** (ANN / len(e2)) - 1
    dd = (s / s.cummax() - 1).min(); dd2 = (e2 / e2.cummax() - 1).min()
    yr = {}
    for y in range(2021, 2027):
        seg = s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]
        if len(seg) > 20: yr[y] = seg.iloc[-1] / seg.iloc[0] - 1
    return s.iloc[-1], c1, c2, (c2 / c1 if c1 > 0 else np.nan), dd, dd2, yr

cfgs = [("cap2+gate", dict(cap=2, vt=1.5, dgate=0.5)),
        ("cap2+gate + carry", dict(cap=2, vt=1.5, dgate=0.5, carry=True)),
        ("Core 1x", dict(cap=1, vt=1.5)),
        ("Core 1x + carry", dict(cap=1, vt=1.5, carry=True))]
print(f"\n{'config':20s} {'FULL $':>12} {'21+ CAGR':>8} {'late/early':>10} {'21+ DD':>6} | yearly 21-26")
for nm, kw in cfgs:
    f, c1, c2, ratio, dd, dd2, yr = rep(sim(**kw))
    ys = " ".join(f"{y%100}:{r*100:+.0f}%" for y, r in yr.items())
    print(f"{nm:20s} ${f:>11,.0f} {c2*100:>+7.0f}% {ratio:>10.2f} {dd2*100:>5.0f}% | {ys}")
