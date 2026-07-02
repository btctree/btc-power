"""Tail-hedge overlay prototype: rolling 30d OTM puts on the model's LONG exposure.
Puts priced by Black-Scholes off trailing realized vol x vol-risk-premium markup (IV>RV is why
hedging bleeds). Measures premium cost vs drawdown reduction on B 2x/3x and 8B 5x (+VOL+FUND).
Honest: 2014+, fees+slippage on trading turnover, put premium deducted, payoff at expiry. No look-ahead.
"""
import os
from math import log, sqrt, exp, erf
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le

ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
c = df["close"]; close = c.to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
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

def ncdf(x): return 0.5 * (1 + erf(x / sqrt(2)))
def bs_put(S, K, T, sig):
    if T <= 0 or sig <= 0: return max(K - S, 0.0)
    d1 = (log(S / K) + 0.5 * sig * sig * T) / (sig * sqrt(T)); d2 = d1 - sig * sqrt(T)
    return K * ncdf(-d2) - S * ncdf(-d1)

def sim(lev, smooth, band, slip, hedge=False, k=0.20, cover=1.0, vrp=1.15, roll=30, ivfloor=0.45):
    e_in = pd.Series(expf).ewm(span=smooth, adjust=False).mean().to_numpy() if smooth and smooth > 1 else expf.copy()
    equity = peak = 500.0; held = 0.0; eq = np.full(n, 500.0)
    put = None  # dict(units, K, expiry)
    prem_paid = 0.0; payoff_recv = 0.0
    for i in range(i0, n):
        # ---- settle/roll hedge ----
        if hedge:
            if put is not None and i >= put["expiry"]:
                pay = max(put["K"] - close[i], 0.0) * put["units"]; equity += pay; payoff_recv += pay; put = None
            if put is None and (i - i0) % roll == 0:
                sig0 = e_in[i - 1]
                if sig0 > 0:                                  # only hedge when (intended) net long
                    notional = cover * abs(sig0) * lev * equity   # $ long exposure to insure
                    units = notional / close[i]
                    K = close[i] * (1 - k)
                    iv = max(rv[i - 1] if rv[i - 1] == rv[i - 1] else ivfloor, ivfloor) * vrp
                    prem = bs_put(close[i], K, roll / 365.0, iv) * units
                    equity -= prem; prem_paid += prem
                    put = dict(units=units, K=K, expiry=i + roll)
        # ---- trading model ----
        sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        tgt = sig * g * lev; base = abs(sig * g) * lev
        if rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt = np.clip(tgt, -base, base); tgt *= min(1.0, 0.60 / rv[i - 1])
        if equity < peak * 0.70: tgt *= 0.5
        e = tgt; adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= 0.99:
            equity *= 0.01; held = 0.0; eq[i] = equity; peak = max(peak, equity); continue
        equity *= (1 + e * (close[i] / close[i - 1] - 1)); equity -= equity * abs(e - held) * (0.0005 + slip)
        held = e; eq[i] = max(equity, 1e-6); peak = max(peak, equity)
    return pd.Series(eq[i0:], index=dates.iloc[i0:].values), prem_paid, payoff_recv

def M(eq):
    r = eq.pct_change().dropna(); yrs = len(eq) / ANN
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dd = (eq / eq.cummax() - 1).min()
    return eq.iloc[-1] / eq.iloc[0], sh, (cagr / abs(dd) if dd < 0 else float("nan")), dd
W = [("W1", "2017-12-16", "2018-11-18"), ("W2", "2021-10-20", "2022-03-09"), ("W3", "2025-05-22", "2025-12-01")]

for label, lev, sm, bd in [("B 2x +VOL+FUND", 2, 5, 0.15), ("B 3x +VOL+FUND", 3, 5, 0.15), ("8B 5x +VOL+FUND", 5, 0, 0.0)]:
    print(f"\n================ {label} + rolling-put tail hedge (@50bp) ================")
    print(f"{'variant':22s} {'@50bp x':>9s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s} {'prem%':>6s} {'pay%':>6s} | {'W1':>4s} {'W2':>4s} {'W3':>4s}")
    for nm, hg, k, cov in [("base (no hedge)", False, 0, 0), ("put 10% OTM", True, 0.10, 1.0),
                           ("put 20% OTM", True, 0.20, 1.0), ("put 30% OTM", True, 0.30, 1.0),
                           ("put 20% cover0.5", True, 0.20, 0.5)]:
        eq, prem, pay = sim(lev, sm, bd, 0.005, hedge=hg, k=k, cover=cov)
        x, sh, cal, dd = M(eq); fin = eq.iloc[-1]
        ww = [(eq.loc[a:b] / eq.loc[a:b].cummax() - 1).min() * 100 for _, a, b in W]
        pr = prem / fin * 100 if fin > 0 else 0; py = pay / fin * 100 if fin > 0 else 0
        print(f"{nm:22s} {x:>8,.0f}x {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}% {pr:>6.0f} {py:>6.0f} | {ww[0]:>3.0f}% {ww[1]:>3.0f}% {ww[2]:>3.0f}%")

print("\n================ longer-dated 90d puts (better for grind-downs) @50bp ================")
print(f"{'config':28s} {'@50bp x':>9s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s} {'prem%':>6s} {'pay%':>6s} | W1/W2/W3")
for label, lev, sm, bd in [("B 2x", 2, 5, 0.15), ("8B 5x", 5, 0, 0.0)]:
    for nm, hg, k, roll in [("base", False, 0, 30), ("90d put 20%OTM", True, 0.20, 90), ("90d put 30%OTM", True, 0.30, 90)]:
        eq, prem, pay = sim(lev, sm, bd, 0.005, hedge=hg, k=k, cover=1.0, roll=roll)
        x, sh, cal, dd = M(eq); fin = eq.iloc[-1]
        ww = [(eq.loc[a:b]/eq.loc[a:b].cummax()-1).min()*100 for _,a,b in W]
        pr = prem/fin*100 if fin>0 else 0; py = pay/fin*100 if fin>0 else 0
        print(f"{label+' '+nm:28s} {x:>8,.0f}x {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}% {pr:>6.0f} {py:>6.0f} | {ww[0]:>3.0f}/{ww[1]:>3.0f}/{ww[2]:>3.0f}%")
