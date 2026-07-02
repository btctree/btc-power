"""Given a 60% max-drawdown budget, find the HIGHEST honest CAGR (BTC-only crypto + global products,
various weights x leverage) and show what $500 actually becomes in 10y vs the $1,000,000 target.
Honest: daily ruin, borrow cost on leverage, no look-ahead, no curve-fitting.
"""
import numpy as np, pandas as pd
from global_engine import fetch_yahoo, UNIVERSE, sleeve
ANN = 365; DD_BUDGET = 0.60; TARGET = 1_000_000; START = 500
U = {k: v for k, v in UNIVERSE.items() if k != "ETH"}            # crypto = BTC only
S = {}
for name, (tk, reg, slip) in U.items():
    sl = sleeve(fetch_yahoo(tk), slip); S[name] = pd.Series(sl["rnet"], index=pd.to_datetime(sl["dates"]))
R = pd.DataFrame(S).sort_index().loc["2017-01-01":].fillna(0.0)   # closed market = 0 return that day
GLOB = [c for c in R.columns if c != "BTC"]
yrs = len(R) / ANN

def stats(r, L, borrow=0.06):
    d = L * r - (L - 1) * borrow / ANN; e = 1.0; arr = []
    for x in d:
        e *= (1 + x); e = max(e, 1e-12); arr.append(e)
    s = pd.Series(arr, index=r.index); cagr = s.iloc[-1] ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1
    dd = (s / s.cummax() - 1).min(); final = START * s.iloc[-1]
    yv = [(1 + d[(d.index >= f"{y}-01-01") & (d.index < f"{y+1}-01-01")]).prod() - 1
          for y in range(2017, 2027) if len(d[(d.index >= f"{y}-01-01") & (d.index < f"{y+1}-01-01")]) > 20]
    return cagr, dd, final, yv

def blend(wbtc):
    return wbtc * R["BTC"] + (1 - wbtc) * R[GLOB].mean(axis=1)

print(f"Target: $500 -> $1,000,000 in 10y  =  {(TARGET/START)**(1/10)-1:.0%}/yr.  DD budget: {DD_BUDGET:.0%}\n")
print(f"{'config':26s} {'lev':>4} {'CAGR':>6} {'maxDD':>6} {'$500-> (10y)':>14} {'best/worst yr':>14}")
best = None
for wbtc, lbl in [(1.0, "100% BTC"), (0.7, "70% BTC + 30% global"), (0.5, "50% BTC + 50% global"),
                  (1/len(R.columns) * len(R.columns), None)]:
    pass
configs = [(1.0, "100% BTC"), (0.7, "70% BTC/30% global"), (0.5, "50% BTC/50% global"),
           (0.30, "30% BTC/70% global"), (1.0 / len(R.columns), "equal-weight all")]
for wbtc, lbl in configs:
    r = blend(wbtc) if lbl != "equal-weight all" else R.mean(axis=1)
    # max leverage within DD budget (scan)
    chosen = None
    for L in np.arange(1.0, 8.01, 0.25):
        c, dd, fin, yv = stats(r, L)
        if dd >= -DD_BUDGET:
            chosen = (L, c, dd, fin, yv)
        else:
            break
    if chosen is None:
        c, dd, fin, yv = stats(r, 1.0); chosen = (1.0, c, dd, fin, yv)
    L, c, dd, fin, yv = chosen
    print(f"{lbl:26s} {L:>3.2f}x {c*100:>+5.0f}% {dd*100:>5.0f}% ${fin:>12,.0f} {max(yv)*100:>+5.0f}%/{min(yv)*100:>+5.0f}%")
    if best is None or fin > best[1]: best = (lbl, fin, c, dd, L)

print(f"\nBEST within {DD_BUDGET:.0%} DD: {best[0]} at {best[4]:.2f}x -> CAGR {best[2]*100:.0f}%, maxDD {best[3]*100:.0f}%,")
print(f"  $500 -> ${best[1]:,.0f} in 10y.   TARGET $1,000,000 -> {'REACHED' if best[1]>=TARGET else f'SHORT by {TARGET/best[1]:.0f}x'}.")
need = (TARGET / START) ** (1 / 10) - 1
print(f"  To hit $1M you need {need:.0%}/yr; the honest ceiling here is ~{best[2]*100:.0f}%/yr. Gap is {need/best[2]:.1f}x the achievable rate.")
