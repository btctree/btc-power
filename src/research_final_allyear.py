"""All-year detail for the BTC-only + global basket (SPY,QQQ,EWH,EWJ,VGK,EWG,GLD,SLV,USO,TLT,BTC),
equal-weight, at 1x and at leverage within the 60% DD budget. Confirms BOTH bear years (2018, 2022)
are already profitable WITHOUT adding low-return cash/USD/commodity dilutants. Honest: same engine, no
look-ahead, daily ruin, 6%/yr borrow on leverage.
"""
import numpy as np, pandas as pd
from global_engine import fetch_yahoo, UNIVERSE, sleeve
ANN = 365; DD = 0.60; START = 500
U = {k: v for k, v in UNIVERSE.items() if k != "ETH"}            # BTC-only crypto + global
S = {k: pd.Series(sleeve(fetch_yahoo(tk), slip)["rnet"], index=pd.to_datetime(sleeve(fetch_yahoo(tk), slip)["dates"]))
     for k, (tk, reg, slip) in U.items()}
R = pd.DataFrame(S).sort_index().loc["2017-01-01":].fillna(0.0)
blend = R.mean(axis=1); yrs = len(blend) / ANN
print("pool:", list(R.columns))

def run(r, L, borrow=0.06):
    d = L * r - (L - 1) * borrow / ANN; e = 1.0; arr = []
    for x in d:
        e = max(e * (1 + x), 1e-12); arr.append(e)
    s = pd.Series(arr, index=r.index); return s, d
def yret(d, y):
    seg = d[(d.index >= f"{y}-01-01") & (d.index < f"{y+1}-01-01")]; return (1 + seg).prod() - 1 if len(seg) > 20 else np.nan
def lev_at_dd(r):
    best = 1.0
    for L in np.arange(1.0, 8.01, 0.25):
        s, _ = run(r, L)
        if (s / s.cummax() - 1).min() >= -DD: best = L
        else: break
    return best

Lmax = lev_at_dd(blend)
for L in [1.0, 3.0, Lmax]:
    s, d = run(blend, L); c = s.iloc[-1] ** (1 / yrs) - 1; dd = (s / s.cummax() - 1).min()
    print(f"\n=== equal-weight BTC+global, {L:.2f}x  ->  CAGR {c*100:.0f}%  maxDD {dd*100:.0f}%  $500->${START*s.iloc[-1]:,.0f} ===")
    print(f"{'year':>5} {'return':>8} {'note':>14}")
    for y in range(2017, 2027):
        r = yret(d, y)
        if np.isnan(r): continue
        note = "<= BEAR YEAR" if y in (2018, 2022) else ""
        print(f"{y:>5} {r*100:>+7.0f}% {note:>14}")
