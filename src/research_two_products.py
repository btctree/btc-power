"""All-year RETURN vs RISK report for the two honest products:
  A) ALL-WEATHER  = BTC-only crypto + global products, equal-weight, 1x (bear years stay green)
  B) AGGRESSIVE   = highest honest CAGR within the 60% drawdown budget (scan weight x leverage)
Correct weekend handling (fillna 0), honest costs, daily ruin, 6%/yr borrow on leverage. No look-ahead.
Outputs a side-by-side year-by-year table (return + drawdown) + summary stats -> printed + saved JSON.
"""
import os, json, numpy as np, pandas as pd
from global_engine import fetch_yahoo, UNIVERSE, sleeve
import live_engine as le
ANN = 365; DD_BUDGET = 0.60; START = 500
U = {k: v for k, v in UNIVERSE.items() if k != "ETH"}          # BTC-only crypto + global
S = {}
for k, (tk, reg, slip) in U.items():
    sl = sleeve(fetch_yahoo(tk), slip); S[k] = pd.Series(sl["rnet"], index=pd.to_datetime(sl["dates"]))
R = pd.DataFrame(S).sort_index().loc["2017-01-01":].fillna(0.0)
GLOB = [c for c in R.columns if c != "BTC"]; yrs = len(R) / ANN

def run(r, L, borrow=0.06):
    d = L * r - (L - 1) * borrow / ANN; e = 1.0; arr = []
    for x in d:
        e = max(e * (1 + x), 1e-12); arr.append(e)
    return pd.Series(arr, index=r.index), pd.Series(d, index=r.index)

def summary(s, d):
    c = s.iloc[-1] ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1
    dd = (s / s.cummax() - 1).min(); sh = d.mean() * ANN / (d.std(ddof=1) * np.sqrt(ANN)) if d.std() > 0 else float("nan")
    yr = []
    for y in range(2017, 2027):
        seg = d[(d.index >= f"{y}-01-01") & (d.index < f"{y+1}-01-01")]
        if len(seg) < 20: continue
        se = (1 + seg).cumprod(); yr.append((y, float(se.iloc[-1] - 1), float((se / se.cummax() - 1).min())))
    return dict(cagr=c, maxdd=dd, sharpe=sh, calmar=(c / abs(dd) if dd < 0 else 0),
                final=START * s.iloc[-1], yearly=yr,
                worst=min(v[1] for v in yr), best=max(v[1] for v in yr),
                pos=sum(1 for v in yr if v[1] > 0), n=len(yr))

# A) all-weather
sA, dA = run(R.mean(axis=1), 1.0); A = summary(sA, dA)
# B) aggressive: scan weight (BTC share) x leverage, max final within DD budget
def blend(w): return w * R["BTC"] + (1 - w) * R[GLOB].mean(axis=1)
bestB = None
for w in (1.0, 0.8, 0.7, 0.6, 0.5, 0.4, 1.0 / len(R.columns)):
    r = R.mean(axis=1) if abs(w - 1.0 / len(R.columns)) < 1e-9 else blend(w)
    for L in np.arange(1.0, 8.01, 0.25):
        s, d = run(r, L)
        if (s / s.cummax() - 1).min() >= -DD_BUDGET: chosen = (w, L, s, d)
        else: break
    sm = summary(chosen[2], chosen[3])
    if bestB is None or sm["final"] > bestB[1]["final"]: bestB = (chosen, sm)
(chB, B) = bestB; wB, LB = chB[0], chB[1]

lbl = f"{'100% BTC' if wB==1.0 else (f'{wB*100:.0f}% BTC/{(1-wB)*100:.0f}% global' if wB>0.12 else 'equal-weight')}"
print(f"A) ALL-WEATHER  = equal-weight BTC+global, 1.0x")
print(f"B) AGGRESSIVE   = {lbl} at {LB:.2f}x  (max CAGR within {DD_BUDGET:.0%} DD)\n")
print(f"{'YEAR':>5} | {'A return':>9} {'A maxDD':>8} | {'B return':>9} {'B maxDD':>8}")
print("-" * 52)
for (y, ra, dda), (_, rb, ddb) in zip(A["yearly"], B["yearly"]):
    flag = " *" if y in (2018, 2022) else "  "
    print(f"{y:>5}{flag}| {ra*100:>+8.0f}% {dda*100:>7.0f}% | {rb*100:>+8.0f}% {ddb*100:>7.0f}%")
print("-" * 52)
print(f"{'CAGR':>5} | {A['cagr']*100:>+8.0f}% {'':>8} | {B['cagr']*100:>+8.0f}%")
print(f"{'maxDD':>5} | {'':>9} {A['maxdd']*100:>7.0f}% | {'':>9} {B['maxdd']*100:>7.0f}%")
print(f"{'Sharpe':>5}| {A['sharpe']:>8.2f} {'':>8} | {B['sharpe']:>8.2f}")
print(f"{'Calmar':>5}| {A['calmar']:>8.2f} {'':>8} | {B['calmar']:>8.2f}")
print(f"{'$500->':>5}| ${A['final']:>8,.0f} {'':>8} | ${B['final']:>8,.0f}")
print(f"{'best/worst yr':>5}: A {A['best']*100:+.0f}%/{A['worst']*100:+.0f}%   B {B['best']*100:+.0f}%/{B['worst']*100:+.0f}%")
print(f"{'positive years':>5}: A {A['pos']}/{A['n']}   B {B['pos']}/{B['n']}   (* = bear year 2018/2022)")
json.dump({"all_weather": A, "aggressive": dict(B, weight_btc=wB, leverage=LB)},
          open(os.path.join(le.OUT, "two_products.json"), "w"), indent=1, default=float)
print("\nsaved out/two_products.json")
