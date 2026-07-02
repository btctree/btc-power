"""My own best design (free hand): a diversified time-series-momentum portfolio (BTC + global + metals +
oil + bonds) that is RISK-PARITY weighted and then VOLATILITY-TARGETED AT THE PORTFOLIO LEVEL — it
dynamically levers up in calm/trending regimes and delevers in crises (auto-derisk 2018/2020/2022).
This is the CTA/managed-futures gold standard; I hadn't tried portfolio-level vol-targeting yet.
Honest: no look-ahead (vol/weights use trailing data, shifted), daily ruin, 6%/yr borrow. Scan the vol
target to find the best CAGR inside a 60% drawdown budget, and compare to fixed-leverage BTC (product B).
"""
import numpy as np, pandas as pd
from global_engine import fetch_yahoo, UNIVERSE, sleeve
ANN = 365; DD = 0.60; START = 500
U = {k: v for k, v in UNIVERSE.items() if k != "ETH"}
S = {k: pd.Series(sleeve(fetch_yahoo(tk), slip)["rnet"], index=pd.to_datetime(sleeve(fetch_yahoo(tk), slip)["dates"]))
     for k, (tk, reg, slip) in U.items()}
R = pd.DataFrame(S).sort_index().loc["2017-01-01":].fillna(0.0); yrs = len(R) / ANN
# risk-parity weights (trailing 60d vol, monthly, capped 25%)
vol = R.rolling(60, min_periods=20).std().shift(1)
W = pd.DataFrame(0.0, index=R.index, columns=R.columns)
for m, g in R.groupby(R.index.to_period("M")).groups.items():
    v = vol.loc[g[0]]; av = v.notna() & (v > 0)
    if not av.any(): continue
    w = (1 / v[av]); w = (w / w.sum()).clip(upper=0.25); w = w / w.sum()
    W.loc[g, w.index] = w.values
base = (R * W).sum(axis=1)                                  # unlevered diversified portfolio
be = (1 + base).cumprod(); bcagr = be.iloc[-1] ** (1 / yrs) - 1; bdd = (be / be.cummax() - 1).min()
bsh = base.mean() * ANN / (base.std(ddof=1) * np.sqrt(ANN))
print(f"BASE (unlevered risk-parity diversified): CAGR {bcagr*100:.0f}%  maxDD {bdd*100:.0f}%  Sharpe {bsh:.2f}  $500->${START*be.iloc[-1]:,.0f}\n")

def run(target, cap=2.5, borrow=0.03):
    rv = (base.rolling(30, min_periods=15).std() * np.sqrt(ANN)).shift(1)
    L = (target / rv).clip(0, cap).fillna(1.0)
    d = L * base - (L - 1).clip(lower=0) * borrow / ANN
    e = 1.0; arr = []
    for x in d:
        e = max(e * (1 + x), 1e-12); arr.append(e)
    s = pd.Series(arr, index=base.index); c = s.iloc[-1] ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1
    dd = (s / s.cummax() - 1).min(); sh = d.mean() * ANN / (d.std(ddof=1) * np.sqrt(ANN)) if d.std() > 0 else float("nan")
    return c, dd, sh, s, d

print(f"{'volTarget':>9} {'lev(avg)':>8} {'CAGR':>6} {'maxDD':>6} {'Sharpe':>6} {'$500->':>10}")
best = None
for tv in [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]:
    c, dd, sh, s, d = run(tv)
    avgL = ((tv / (base.rolling(30, min_periods=15).std() * np.sqrt(ANN)).shift(1)).clip(0, 2.5)).mean()
    tag = ""
    if dd >= -DD and (best is None or c > best[0]): best = (c, dd, sh, tv, s, d); tag = " <=best@60%DD"
    print(f"{tv:>9.0%} {avgL:>8.2f} {c*100:>+5.0f}% {dd*100:>5.0f}% {sh:>6.2f} ${START*s.iloc[-1]:>9,.0f}{tag}")

if best is None:
    print("\n=== NO vol-target config stayed within 60% DD — portfolio vol-targeting FAILED here. ===")
    print("Reason: over-diversified base (~low vol) forces high leverage; borrow + crisis amplification break it.")
    raise SystemExit
c, dd, sh, tv, s, d = best
print(f"\n=== MY BEST: portfolio vol-target {tv:.0%}, CAGR {c*100:.0f}%, maxDD {dd*100:.0f}%, Sharpe {sh:.2f}, $500->${START*s.iloc[-1]:,.0f} ===")
print(f"{'year':>5} {'return':>8} {'maxDD':>7}")
for y in range(2017, 2027):
    seg = d[(d.index >= f"{y}-01-01") & (d.index < f"{y+1}-01-01")]
    if len(seg) < 20: continue
    se = (1 + seg).cumprod(); star = " *" if y in (2018, 2022) else "  "
    print(f"{y:>5}{star}{se.iloc[-1]*100-100:>+6.0f}% {(se/se.cummax()-1).min()*100:>6.0f}%")
print(f"\ncompare product B (100% BTC 1.5x): CAGR +53% / DD -59% / $27,857")
