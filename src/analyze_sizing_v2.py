"""Better SIZE CONTROL on the ensemble: exposure = signal x clip(vol_target/realised_vol, 0, cap).
Unlike the current models (which only scale DOWN, capped at nominal lev), this scales UP in calm
markets toward a hard cap and DOWN hard in volatile markets. Goal: a lower-risk 8B and a
more-profitable Growth-B. Honest: 2014+, turnover control, VOL+FUND gates, fees+slippage, liquidation.
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
n = len(df); i0 = 260; dstr = df["Date"].tolist(); dates = pd.to_datetime(df["Date"])
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

def sim(vt, cap, smooth=5, band=0.15, dd_kill=0.30, slip=0.005, fee=0.0005, maint=0.01,
        legacy=None):
    """legacy=lev -> reproduce current model (lev x min(1,0.6/rv)); else new sizing clip(vt/rv,0,cap)."""
    e_in = pd.Series(expf).ewm(span=smooth, adjust=False).mean().to_numpy() if smooth and smooth > 1 else expf.copy()
    equity = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); liq = 0; exps = []
    for i in range(i0, n):
        sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = equity; continue
        if legacy:
            mult = legacy * min(1.0, 0.60 / rv[i - 1])
        else:
            mult = min(cap, vt / rv[i - 1])
        e = sig * g * mult
        if dd_kill > 0 and equity < peak * (1 - dd_kill): e *= 0.5
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint):
            equity *= 0.01; liq += 1; held = 0.0; eq[i] = equity; peak = max(peak, equity); continue
        equity *= (1 + e * (close[i] / close[i - 1] - 1)); equity -= equity * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(equity, 1e-9); peak = max(peak, equity); exps.append(abs(e))
    s = pd.Series(eq[i0:], index=dates.iloc[i0:].values); r = s.pct_change().dropna(); yrs = len(s) / ANN
    cagr = (s.iloc[-1] / 500) ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dd = (s / s.cummax() - 1).min()
    return s.iloc[-1], sh, (cagr / abs(dd) if dd < 0 else float("nan")), dd, liq, np.mean(exps), np.max(exps)
W = [("W1", "2017-12-16", "2018-11-18"), ("W2", "2021-10-20", "2022-03-09"), ("W3", "2025-05-22", "2025-12-01")]
def wdd(vt, cap, **kw):
    e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()  # placeholder unused
    return None

def row(nm, **kw):
    f, sh, cal, dd, liq, ae, me = sim(**kw)
    print(f"{nm:26s} ${f:>14,.0f} {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}% {liq:>3d} {ae:>5.2f}x {me:>5.2f}x")

print(f"{'model (vt/cap)':26s} {'$500->':>15s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s} {'liq':>3s} {'avgX':>5s} {'maxX':>5s}")
print("-- BASELINES --")
row("raw 8B 5x (current)", vt=0, cap=0, smooth=0, band=0.0, legacy=5)
row("B 2x +VOL+FUND (current)", vt=0, cap=0, legacy=2)
print("-- LOWER-RISK (8B replacement) --")
row("size vt0.6 cap2.0", vt=0.6, cap=2.0)
row("size vt0.8 cap2.0", vt=0.8, cap=2.0)
row("size vt0.6 cap2.3", vt=0.6, cap=2.3)
print("-- MORE-PROFITABLE (Growth) --")
row("size vt1.2 cap2.5", vt=1.2, cap=2.5)
row("size vt1.5 cap3.0", vt=1.5, cap=3.0)
row("size vt2.0 cap3.5", vt=2.0, cap=3.5)
row("size vt2.5 cap5.0", vt=2.5, cap=5.0)

print("\n=== 8B-lite (vt0.8 size control) — leverage & slippage breakdown ===")
yrs = (n - i0) / ANN
print(f"{'config':30s} {'$500->':>14s} {'CAGR':>6s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s} {'avgX':>6s} {'maxX':>6s} {'liq':>4s}")
for nm, cap, slip in [("cap2.0 (up to 2x) @0bp", 2.0, 0.0), ("cap2.0 (up to 2x) @50bp", 2.0, 0.005),
                      ("cap1.0 (NO leverage) @0bp", 1.0, 0.0), ("cap1.0 (NO leverage) @50bp", 1.0, 0.005)]:
    f, sh, cal, dd, liq, ae, me = sim(vt=0.8, cap=cap, slip=slip)
    cagr = (f / 500) ** (1 / yrs) - 1
    print(f"{nm:30s} ${f:>13,.0f} {cagr*100:>5.0f}% {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}% {ae:>5.2f}x {me:>5.2f}x {liq:>4d}")

def eqseries(vt, cap, slip, smooth=5, band=0.15, dd_kill=0.30, fee=0.0005, maint=0.01):
    e_in = pd.Series(expf).ewm(span=smooth, adjust=False).mean().to_numpy()
    equity = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); liq = 0; exps = []
    for i in range(i0, n):
        sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = equity; continue
        e = sig * g * min(cap, vt / rv[i - 1])
        if dd_kill > 0 and equity < peak * (1 - dd_kill): e *= 0.5
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint):
            equity *= 0.01; liq += 1; held = 0.0; eq[i] = equity; peak = max(peak, equity); continue
        equity *= (1 + e * (close[i] / close[i - 1] - 1)); equity -= equity * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(equity, 1e-9); peak = max(peak, equity); exps.append(abs(e))
    return pd.Series(eq[i0:], index=dates.iloc[i0:].values), liq, np.mean(exps), np.max(exps)
WIN = [("2017-12-16","2018-11-18"),("2021-10-20","2022-03-09"),("2025-05-22","2025-12-01")]
yrs=(n-i0)/ANN
print("\n=== BALANCED 8B candidates (size+margin controlled, VOL+FUND) ===")
print(f"{'config':22s} {'slip':>5s} {'$500->':>14s} {'CAGR':>5s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s} {'maxX/margin':>12s} {'liq':>3s} | W1/W2/W3")
for nm, vt, cap in [("Bal cap2.5 vt1.2",1.2,2.5),("Bal cap3.0 vt1.5",1.5,3.0),("Bal cap3.5 vt1.8",1.8,3.5)]:
    for slip,tag in [(0.0,"0bp"),(0.005,"50bp")]:
        s,liq,ae,me=eqseries(vt,cap,slip)
        r=s.pct_change().dropna(); cagr=(s.iloc[-1]/500)**(1/yrs)-1
        sh=r.mean()*ANN/(r.std(ddof=1)*np.sqrt(ANN)); dd=(s/s.cummax()-1).min()
        ww=[(s.loc[a:b]/s.loc[a:b].cummax()-1).min()*100 for a,b in WIN]
        print(f"{nm:22s} {tag:>5s} ${s.iloc[-1]:>13,.0f} {cagr*100:>4.0f}% {sh:>5.2f} {(cagr/abs(dd)):>5.2f} {dd*100:>5.0f}% {me:>5.1f}x/{me/5*100:>3.0f}% {liq:>3d} | {ww[0]:>3.0f}/{ww[1]:>3.0f}/{ww[2]:>3.0f}%")
