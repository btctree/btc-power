"""Popular BTC indicators from the online scan, tested as HYPOTHESIS-DRIVEN gates on our two best
configs (cap2+dollar-gate and Growth A live). All trailing / no look-ahead, 50bp.
  G1 Mayer Multiple (close/SMA200d): halve exposure when >2.4 (overheated; classic threshold)
  G2 200-WEEK MA floor: no shorts when price < 200WMA (cycle-bottom zone; shorts dangerous there)
  G3 100/250 SMA cross: halve counter-trend exposure (user asked about 250SMA)
  G4 Weekly trend filter (weekly close vs weekly SMA10): halve daily signals against the weekly trend
Report FULL $, 2021+ CAGR, straightness, DD vs base. Discipline: these are 4 pre-registered popular
rules, not a mined grid — but any single winner still deserves skepticism.
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
u = fetch_yahoo("UUP", refresh=False)
uup = pd.Series(u["close"].values, index=pd.to_datetime(u["date"])).reindex(dates).ffill()
dollar_strong = (uup > uup.rolling(200).mean()).shift(1).fillna(False).to_numpy()
c_ = pd.Series(close, index=dates)
sma200d = c_.rolling(200).mean(); mayer = (c_ / sma200d).shift(1).to_numpy()
wma200 = c_.rolling(1400).mean(); below_200w = (c_ < wma200).shift(1).fillna(False).to_numpy()
s100 = c_.rolling(100).mean(); s250 = c_.rolling(250).mean()
up_cross = (s100 > s250).shift(1).fillna(True).to_numpy()
wk = c_.resample("W").last(); wk_up_w = wk > wk.rolling(10).mean()
wk_up = wk_up_w.reindex(dates, method="ffill").shift(1).fillna(True).to_numpy()

def sim(cap, vt, band=0.15, slip=0.005, dd_kill=0.30, fee=0.0005, maint=0.01, dgate=0.0, gate=None):
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        sig = esm[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if dgate and dollar_strong[i - 1]: g *= dgate
        if gate == "mayer" and mayer[i] == mayer[i] and mayer[i] > 2.4: g *= 0.5
        if gate == "wma200" and sig < 0 and below_200w[i]: g = 0.0
        if gate == "cross" and ((sig > 0) != bool(up_cross[i])) and sig != 0: g *= 0.5
        if gate == "weekly" and ((sig > 0) != bool(wk_up[i])) and sig != 0: g *= 0.5
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        e = sig * g * min(cap, vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint): eqv *= 0.01; held = 0.0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv)
    return eq

def rep(eq):
    s = pd.Series(eq[i0:], index=dates[i0:])
    e1 = s[s.index < "2021-01-01"]; e2 = s[s.index >= "2021-01-01"]
    c1 = (e1.iloc[-1] / e1.iloc[0]) ** (ANN / len(e1)) - 1; c2 = (e2.iloc[-1] / e2.iloc[0]) ** (ANN / len(e2)) - 1
    dd = (s / s.cummax() - 1).min()
    return s.iloc[-1], c2, (c2 / c1 if c1 > 0 else np.nan), dd

for base_nm, kw in [("cap2+gate", dict(cap=2, vt=1.5, dgate=0.5)), ("Growth A", dict(cap=5, vt=1.5))]:
    print(f"\n=== base: {base_nm} ===")
    print(f"{'gate':28s} {'FULL $':>12} {'21+ CAGR':>8} {'late/early':>10} {'maxDD':>6}")
    for gnm, g in [("(none)", None), ("Mayer>2.4 halve", "mayer"), ("no shorts <200W-MA", "wma200"),
                   ("100/250 cross counter-halve", "cross"), ("weekly-trend counter-halve", "weekly")]:
        f, c2, ratio, dd = rep(sim(gate=g, **kw))
        print(f"{gnm:28s} ${f:>11,.0f} {c2*100:>+7.0f}% {ratio:>10.2f} {dd*100:>5.0f}%")

# COMBO check (one combination only, flagged as extra selection step): 200WMA-floor + weekly filter
def sim2(cap, vt, band=0.15, slip=0.005, dd_kill=0.30, fee=0.0005, maint=0.01, dgate=0.0):
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        sig = esm[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if dgate and dollar_strong[i - 1]: g *= dgate
        if sig < 0 and below_200w[i]: g = 0.0
        if ((sig > 0) != bool(wk_up[i])) and sig != 0: g *= 0.5
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        e = sig * g * min(cap, vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint): eqv *= 0.01; held = 0.0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv)
    return eq
print("\nCOMBO 200WMA-floor + weekly:")
for nm, kw in [("cap2+gate", dict(cap=2, vt=1.5, dgate=0.5)), ("Growth A", dict(cap=5, vt=1.5))]:
    f, c2, ratio, dd = rep(sim2(**kw))
    print(f"  {nm:12s} ${f:>11,.0f}  21+ {c2*100:+.0f}%  ratio {ratio:.2f}  DD {dd*100:.0f}%")
