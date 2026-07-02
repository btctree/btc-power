"""Grid search for a package that pushes the @50bp return to >= $1M (from $500), honestly.
Levers: vol_target, exposure cap, turnover-smoothing (span), deadband, on top of the ensemble +
VOL+FUND gates + dd-kill + honest liquidation. Reports configs reaching $1M sorted by Calmar (best
risk-adjusted) and flags drawdown cost. Heavier smoothing/deadband cut slippage drag (the key at 50bp).
"""
import os, itertools
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
WIN = [("2017-12-16","2018-11-18"),("2021-10-20","2022-03-09"),("2025-05-22","2025-12-01")]
yrs = (n - i0) / ANN

def run(vt, cap, smooth, band, slip=0.005, dd_kill=0.30, fee=0.0005, maint=0.01):
    e_in = pd.Series(expf).ewm(span=smooth, adjust=False).mean().to_numpy() if smooth > 1 else expf.copy()
    equity = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); liq = 0; me = 0.0
    for i in range(i0, n):
        sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = equity; continue
        e = sig * g * min(cap, vt / rv[i - 1])
        if dd_kill > 0 and equity < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint):
            equity *= 0.01; liq += 1; held = 0.0; eq[i] = equity; peak = max(peak, equity); continue
        equity *= (1 + e * (close[i] / close[i - 1] - 1)); equity -= equity * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(equity, 1e-9); peak = max(peak, equity); me = max(me, abs(e))
    s = pd.Series(eq[i0:], index=dates.iloc[i0:].values); r = s.pct_change().dropna()
    cagr = (s.iloc[-1] / 500) ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dd = (s / s.cummax() - 1).min(); cal = cagr / abs(dd) if dd < 0 else float("nan")
    ww = [(s.loc[a:b] / s.loc[a:b].cummax() - 1).min() * 100 for a, b in WIN]
    return dict(final=s.iloc[-1], cagr=cagr, sh=sh, cal=cal, dd=dd, liq=liq, me=me, ww=ww,
                vt=vt, cap=cap, sm=smooth, bd=band)

res = []
for vt, cap, sm, bd in itertools.product([1.5,2.0,2.5,3.0],[3.0,4.0,5.0],[5,10,15],[0.15,0.25]):
    res.append(run(vt, cap, sm, bd))
million = [r for r in res if r["final"] >= 1_000_000]
print(f"tested {len(res)} configs | {len(million)} reach >=$1M @50bp\n")
print("TOP $1M+ configs by Calmar (best risk-adjusted first):")
print(f"{'vt':>4s} {'cap':>4s} {'sm':>3s} {'bd':>5s} | {'$500->':>13s} {'CAGR':>5s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s} {'maxX':>5s} {'liq':>3s} | W1/W2/W3")
for r in sorted(million, key=lambda x: -x["cal"])[:12]:
    print(f"{r['vt']:>4.1f} {r['cap']:>4.1f} {r['sm']:>3d} {r['bd']:>5.2f} | ${r['final']:>12,.0f} {r['cagr']*100:>4.0f}% {r['sh']:>5.2f} {r['cal']:>5.2f} {r['dd']*100:>5.0f}% {r['me']:>4.1f}x {r['liq']:>3d} | {r['ww'][0]:>3.0f}/{r['ww'][1]:>3.0f}/{r['ww'][2]:>3.0f}%")
if million:
    best_dd = min(million, key=lambda x: abs(x["dd"]))
    print(f"\nShallowest-drawdown $1M+ config: vt{best_dd['vt']} cap{best_dd['cap']} sm{best_dd['sm']} bd{best_dd['bd']} "
          f"-> ${best_dd['final']:,.0f} @50bp, maxDD {best_dd['dd']*100:.0f}%, liq {best_dd['liq']}")
