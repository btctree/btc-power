"""Three products, all-year return vs risk, HONEST (no parameter cherry-picking):
 A) ALL-WEATHER  : equal-weight BTC+global, 1x
 B) AGGRESSIVE   : 100% BTC, 1.5x (max CAGR within 60% DD)
 C) ROTATION     : momentum rotation on high-octane real products (BTC + 3x ETFs TQQQ/SOXL/SPXL +
                   gold/silver/oil/JP/DE), top-3 by momentum AVERAGED over 4 lookbacks (42/63/90/126
                   so no single lookback is cherry-picked), levered to 60% DD. The $450k version used a
                   single cherry-picked 42d lookback (overfit; out-of-sample it decays 70%->30%/yr).
Correct weekend handling, honest costs, daily ruin, 6%/yr borrow. No look-ahead.
"""
import json, os, numpy as np, pandas as pd
from global_engine import fetch_yahoo, UNIVERSE, sleeve
import live_engine as le
ANN = 365; DD = 0.60; START = 500

def run(r, L, borrow=0.06):
    d = L * r - (L - 1) * borrow / ANN; e = 1.0; arr = []
    for x in d:
        e = max(e * (1 + x), 1e-12); arr.append(e)
    return pd.Series(arr, index=r.index), pd.Series(d, index=r.index)
def maxlev(r):
    best = 1.0
    for L in np.arange(1.0, 8.01, 0.25):
        s, _ = run(r, L)
        if (s / s.cummax() - 1).min() >= -DD: best = L
        else: break
    return best
def summ(s, d, yrs):
    c = s.iloc[-1] ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1; dd = (s / s.cummax() - 1).min()
    sh = d.mean() * ANN / (d.std(ddof=1) * np.sqrt(ANN)) if d.std() > 0 else float("nan")
    yr = []
    for y in range(2017, 2027):
        seg = d[(d.index >= f"{y}-01-01") & (d.index < f"{y+1}-01-01")]
        if len(seg) < 20: continue
        se = (1 + seg).cumprod(); yr.append((y, float(se.iloc[-1] - 1), float((se / se.cummax() - 1).min())))
    return dict(cagr=c, dd=dd, sharpe=sh, calmar=c / abs(dd) if dd < 0 else 0, final=START * s.iloc[-1], yr=yr)

# --- C: honest rotation universe (real products; drop FNGU = too little history) ---
ROT = {"BTC": ("BTC-USD", 0.005), "TQQQ": ("TQQQ", 0.0008), "SOXL": ("SOXL", 0.0010), "SPXL": ("SPXL", 0.0008),
       "GLD": ("GLD", 0.0006), "SLV": ("SLV", 0.0008), "USO": ("USO", 0.0012), "EWJ": ("EWJ", 0.0008), "EWG": ("EWG", 0.0010)}
Sr, Pr = {}, {}
for k, (tk, slip) in ROT.items():
    sl = sleeve(fetch_yahoo(tk), slip)
    Sr[k] = pd.Series(sl["rnet"], index=pd.to_datetime(sl["dates"])); Pr[k] = pd.Series(sl["close"], index=pd.to_datetime(sl["dates"]))
Rr = pd.DataFrame(Sr).sort_index().fillna(0.0); Pp = pd.DataFrame(Pr).reindex(Rr.index).ffill()
Rr = Rr.loc["2017-01-01":]; Pp = Pp.loc["2017-01-01":]; yrsC = len(Rr) / ANN
W = pd.DataFrame(0.0, index=Rr.index, columns=Rr.columns)
looks = [42, 63, 90, 126]
mom = sum(Pp.pct_change(L).shift(1) for L in looks) / len(looks)          # AVERAGED momentum (robust)
trend = Rr.rolling(63, min_periods=20).mean().shift(1)
for m, g in Rr.groupby(Rr.index.to_period("M")).groups.items():
    cand = mom.loc[g[0]][(mom.loc[g[0]] > 0) & (trend.loc[g[0]] > 0)].dropna()
    sel = cand.nlargest(3).index
    if len(sel): W.loc[g, sel] = 1.0 / len(sel)
rotR = (Rr * W).sum(axis=1); Lc = maxlev(rotR); sC, dC = run(rotR, Lc); C = summ(sC, dC, yrsC)

# --- A & B from the saved two-product run ---
TP = json.load(open(os.path.join(le.OUT, "two_products.json")))
A = TP["all_weather"]; B = TP["aggressive"]
def yrmap(d): return {int(y): (r, dd) for y, r, dd in d}
ay, by, cy = yrmap(A["yearly"]), yrmap(B["yearly"]), yrmap(C["yr"])

print(f"C) ROTATION = top-3 momentum (avg of {looks}d lookbacks) on BTC+3xETFs+commodities, {Lc:.2f}x\n")
print(f"{'YEAR':>5} | {'A ret':>6} {'A DD':>6} | {'B ret':>7} {'B DD':>6} | {'C ret':>7} {'C DD':>6}")
print("-" * 60)
for y in range(2017, 2027):
    if y not in ay: continue
    f = "*" if y in (2018, 2022) else " "
    print(f"{y:>4}{f} | {ay[y][0]*100:>+5.0f}% {ay[y][1]*100:>5.0f}% | {by[y][0]*100:>+6.0f}% {by[y][1]*100:>5.0f}% | {cy[y][0]*100:>+6.0f}% {cy[y][1]*100:>5.0f}%")
print("-" * 60)
print(f"{'CAGR':>5} | {A['cagr']*100:>+5.0f}% {'':>6} | {B['cagr']*100:>+6.0f}% {'':>6} | {C['cagr']*100:>+6.0f}%")
print(f"{'maxDD':>5} | {'':>6} {A['maxdd']*100:>5.0f}% | {'':>7} {B['maxdd']*100:>5.0f}% | {'':>7} {C['dd']*100:>5.0f}%")
print(f"{'Sharpe':>5}| {A['sharpe']:>6.2f} {'':>6} | {B['sharpe']:>7.2f} {'':>6} | {C['sharpe']:>7.2f}")
print(f"{'Calmar':>5}| {A['calmar']:>6.2f} {'':>6} | {B['calmar']:>7.2f} {'':>6} | {C['calmar']:>7.2f}")
print(f"{'$500->':>5}| ${A['final']:>6,.0f} {'':>5} | ${B['final']:>6,.0f} {'':>5} | ${C['final']:>7,.0f}")
json.dump({"A": A, "B": B, "C": dict(C, leverage=Lc)}, open(os.path.join(le.OUT, "three_products.json"), "w"), indent=1, default=float)
print("\nsaved out/three_products.json")
