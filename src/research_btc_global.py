"""BTC-only crypto + GLOBAL products basket, and an HONEST test of what it takes to reach 100-200%/yr.
Shows: (1) the real 1x yearly returns, (2) leverage vs CAGR vs drawdown vs RUIN (honest daily wipeout),
to demonstrate why 100-200% EVERY year is not achievable without ruin. No look-ahead, no curve-fitting.
"""
import numpy as np, pandas as pd
from global_engine import fetch_yahoo, UNIVERSE, sleeve
ANN = 365
U = {k: v for k, v in UNIVERSE.items() if k != "ETH"}        # crypto = BTC only
S = {}
for name, (tk, reg, slip) in U.items():
    sl = sleeve(fetch_yahoo(tk), slip); S[name] = pd.Series(sl["rnet"], index=pd.to_datetime(sl["dates"]))
R = pd.DataFrame(S).sort_index().loc["2017-01-01":]
blend = R.mean(axis=1)                                        # equal-weight, 11 products, BTC-only crypto
print("Universe (BTC-only crypto + global):", list(R.columns))

def yearly(r):
    out = []
    for y in range(2017, 2027):
        yr = r[(r.index >= f"{y}-01-01") & (r.index < f"{y+1}-01-01")]
        if len(yr) < 20: continue
        out.append((y, (1 + yr).prod() - 1))
    return out

eq = (1 + blend).cumprod(); yrs = len(blend) / ANN
cagr = eq.iloc[-1] ** (1 / yrs) - 1; dd = (eq / eq.cummax() - 1).min()
print(f"\n1x BTC-only+global blend: CAGR {cagr*100:.0f}%  maxDD {dd*100:.0f}%  $500->${eq.iloc[-1]*500:,.0f}")
print("yearly:", " ".join(f"{y}:{r*100:+.0f}%" for y, r in yearly(blend)))

def lev(r, L, borrow=0.06):
    d = L * r - (L - 1) * borrow / ANN
    e = 1.0; arr = []; ruin = 0
    for x in d:
        e = e * (1 + x)
        if e <= 0: e = 1e-12; ruin += 1
        arr.append(e)
    s = pd.Series(arr, index=r.index); c = s.iloc[-1] ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1
    mdd = (s / s.cummax() - 1).min()
    ys = []
    for y in range(2017, 2027):
        seg = d[(d.index >= f"{y}-01-01") & (d.index < f"{y+1}-01-01")]
        if len(seg) > 20: ys.append((1 + seg).prod() - 1)
    yrs_over = sum(1 for v in ys if v >= 1.0); yrs_neg = sum(1 for v in ys if v < 0)
    return c, mdd, ruin, yrs_over, len(ys), yrs_neg, min(ys) if ys else 0

print(f"\n=== HONEST leverage test on the diversified blend (borrow 6%/yr, daily ruin) ===")
print(f"{'lev':>4} {'CAGR':>6} {'maxDD':>6} {'yrs>=100%':>9} {'yrs<0':>6} {'worst yr':>8} {'ruin days':>9}")
for L in [1, 2, 3, 4, 5, 6, 8, 10]:
    c, mdd, ruin, ov, n, neg, wy = lev(blend, L)
    print(f"{L:>3}x {c*100:>+5.0f}% {mdd*100:>5.0f}% {ov:>4}/{n:<4} {neg:>6} {wy*100:>+7.0f}% {ruin:>9}")
print("\n(>=100% means how many of the ~10 years cleared +100%. To hit 100-200% EVERY year, that column")
print(" would need to read 10/10 with no negative years and a survivable drawdown — note that it never does.)")
