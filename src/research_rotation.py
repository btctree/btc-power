"""Push the strategy harder, honestly: trend-following on HIGH-OCTANE real products (3x ETFs: TQQQ/SOXL/
SPXL/FNGU) + BTC + diversifiers, with cross-sectional MOMENTUM ROTATION (each month hold the strongest
trending products), levered to the 60% drawdown budget. The trend filter sidesteps the -80% leveraged-ETF
crashes while riding the +100-200% bull runs. No look-ahead (rank uses only trailing data; act next day).
Full year-by-year detail. Honest costs + daily ruin.
"""
import numpy as np, pandas as pd
from global_engine import fetch_yahoo, sleeve
ANN = 365; DD = 0.60; START = 500
# real tradeable products: 3x US leveraged ETFs (since ~2016 here) + BTC + commodity/intl diversifiers
UNI = {"BTC": ("BTC-USD", 0.005), "TQQQ": ("TQQQ", 0.0008), "SOXL": ("SOXL", 0.0010),
       "SPXL": ("SPXL", 0.0008), "FNGU": ("FNGU", 0.0012), "GLD": ("GLD", 0.0006),
       "SLV": ("SLV", 0.0008), "USO": ("USO", 0.0012), "EWJ": ("EWJ", 0.0008), "EWG": ("EWG", 0.0010)}
S = {}; A = {}
for k, (tk, slip) in UNI.items():
    try:
        sl = sleeve(fetch_yahoo(tk), slip)
        S[k] = pd.Series(sl["rnet"], index=pd.to_datetime(sl["dates"]))
        A[k] = pd.Series(sl["close"], index=pd.to_datetime(sl["dates"]))
        print(f"  {k:5s} {len(sl['dates'])}d")
    except Exception as e:
        print("  skip", k, repr(e)[:50])
R = pd.DataFrame(S).sort_index().fillna(0.0); P = pd.DataFrame(A).reindex(R.index).ffill()
R = R.loc["2017-01-01":]; P = P.loc["2017-01-01":]; yrs = len(R) / ANN

def rotation_weights(K=3, look=63):
    mom = P.pct_change(look).shift(1)                  # trailing momentum, known yesterday
    trend = R.rolling(look, min_periods=20).mean().shift(1)   # is the sleeve making money lately
    W = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for m, g in R.groupby(R.index.to_period("M")).groups.items():
        mm = mom.loc[g[0]]; tr = trend.loc[g[0]]
        cand = mm[(mm > 0) & (tr > 0)].dropna()       # only rising, profitable-trend products
        sel = cand.nlargest(K).index
        if len(sel): W.loc[g, sel] = 1.0 / len(sel)
    return W

def run(r, L, borrow=0.06):
    d = L * r - (L - 1) * borrow / ANN; e = 1.0; arr = []
    for x in d:
        e *= (1 + x); e = max(e, 1e-12); arr.append(e)
    s = pd.Series(arr, index=r.index); c = s.iloc[-1] ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1
    mdd = (s / s.cummax() - 1).min(); return c, mdd, s, d

def max_lev(r):
    best = (1.0,) + run(r, 1.0)[:2]
    for L in np.arange(1.0, 6.01, 0.25):
        c, mdd, _, _ = run(r, L)
        if mdd >= -DD: best = (L, c, mdd)
        else: break
    return best

# scan concentration K and lookback to find the strongest honest config within 60% DD
best = None
for K in (1, 2, 3, 4):
    for look in (42, 63, 90, 126):
        rot = (R * rotation_weights(K, look)).sum(axis=1)
        L, c, mdd = max_lev(rot)
        _, _, s, _ = run(rot, L); fin = START * s.iloc[-1]
        if best is None or fin > best[0]:
            best = (fin, K, look, L, c, mdd)
fin, K, look, _, _, _ = best
print(f"\nbest config: top-{K} momentum, {look}d lookback  (scanned K x lookback)")
rot = (R * rotation_weights(K, look)).sum(axis=1)
L, c, mdd = max_lev(rot); _, _, s, d = run(rot, L)
print(f"\n=== MOMENTUM-ROTATION (top-{K} trending, {look}d), levered to {DD:.0%} DD: {L:.2f}x ===")
print(f"CAGR {c*100:.0f}%   maxDD {mdd*100:.0f}%   $500 -> ${START*s.iloc[-1]:,.0f} in 10y")
print(f"\n{'year':>5} {'return':>8} {'maxDD':>7} {'$ at year-end (from $500)':>26}")
eq = START
for y in range(2017, 2027):
    seg = d[(d.index >= f"{y}-01-01") & (d.index < f"{y+1}-01-01")]
    if len(seg) < 20: continue
    se = (1 + seg).cumprod(); ret = se.iloc[-1] - 1; ddy = (se / se.cummax() - 1).min()
    eq *= (1 + ret)
    print(f"{y:>5} {ret*100:>+7.0f}% {ddy*100:>6.0f}% {eq:>26,.0f}")
print(f"\nTarget $1,000,000: {'REACHED' if START*s.iloc[-1] >= 1e6 else f'short by {1e6/(START*s.iloc[-1]):.0f}x'}.")
need = (1e6 / START) ** (1 / 10) - 1
print(f"need {need:.0%}/yr; achieved {c:.0%}/yr.")

print("\n=== ROBUSTNESS: does the 'best' config survive out-of-sample? (unlevered rotation CAGR) ===")
def cagr_period(r, a, b):
    seg = r[(r.index >= a) & (r.index < b)]; e = (1 + seg).cumprod(); yy = len(seg) / ANN
    return e.iloc[-1] ** (1 / yy) - 1 if e.iloc[-1] > 0 else -1
rows = []
for K in (1, 2, 3, 4):
    for look in (42, 63, 90, 126):
        r = (R * rotation_weights(K, look)).sum(axis=1)
        rows.append((K, look, cagr_period(r, "2017-01-01", "2021-01-01"), cagr_period(r, "2021-01-01", "2027-01-01")))
rows.sort(key=lambda x: -x[2])
print(f"{'K':>2}{'look':>6}{'TRAIN 17-20':>12}{'TEST 21-26':>11}")
for K, look, tr, te in rows:
    print(f"{K:>2}{look:>6}{tr*100:>11.0f}%{te*100:>10.0f}%")
b = rows[0]
print(f"\nbest-on-TRAIN = top-{b[0]} {b[1]}d: train {b[2]*100:.0f}%/yr  ->  out-of-sample test {b[3]*100:.0f}%/yr")
ta = np.array([x[2] for x in rows]); tb = np.array([x[3] for x in rows])
print(f"train-vs-test CAGR correlation across configs: {np.corrcoef(ta, tb)[0,1]:+.2f}")
print("(near 0 or negative = the winning params are luck; they do NOT carry forward = overfit)")
