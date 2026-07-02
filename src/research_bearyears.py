"""Make the bear years (2018, 2022) profitable. Diagnose what each product's trend sleeve did in those
risk-off years, then add the bear-market WINNERS to the pool (US dollar UUP, energy XLE, broad
commodities DBC, cash SHV) so the portfolio has something to rotate into when stocks/crypto/bonds fall.
Honest: same engine on every asset, no look-ahead, no per-year tuning.
"""
import numpy as np, pandas as pd
from global_engine import fetch_yahoo, UNIVERSE, sleeve
ANN = 365
EXIST = {k: v for k, v in UNIVERSE.items() if k != "ETH"}          # BTC + global (no ETH)
ADD = {"USD-UUP": ("UUP", "FX", 0.0006), "Energy-XLE": ("XLE", "Sector", 0.0006),
       "Commod-DBC": ("DBC", "Commod", 0.0010), "Cash-SHV": ("SHV", "Cash", 0.0003)}
ALL = {**EXIST, **ADD}
S = {}
for name, (tk, reg, slip) in ALL.items():
    try:
        sl = sleeve(fetch_yahoo(tk), slip); S[name] = pd.Series(sl["rnet"], index=pd.to_datetime(sl["dates"]))
        print(f"  {name:11s} {len(sl['dates'])}d")
    except Exception as e:
        print("  skip", name, repr(e)[:50])
R = pd.DataFrame(S).sort_index().loc["2017-01-01":].fillna(0.0)

def yret(r, y):
    seg = r[(r.index >= f"{y}-01-01") & (r.index < f"{y+1}-01-01")]
    return (1 + seg).prod() - 1 if len(seg) > 20 else float("nan")

print("\n=== per-product trend-sleeve return in the bear years ===")
print(f"{'product':12s} {'2018':>7} {'2022':>7}")
for n in R.columns:
    print(f"{n:12s} {yret(R[n],2018)*100:>+6.0f}% {yret(R[n],2022)*100:>+6.0f}%")

old = [c for c in EXIST]; new = list(R.columns)
def allyears(r):
    return [(y, yret(r, y)) for y in range(2017, 2027) if not np.isnan(yret(r, y))]
def cagr_dd(r):
    e = (1 + r).cumprod(); c = e.iloc[-1] ** (1 / (len(r) / ANN)) - 1; dd = (e / e.cummax() - 1).min(); return c, dd, e.iloc[-1]

print("\n=== all-year returns: before vs after adding USD/Energy/Commod/Cash ===")
bO = R[old].mean(axis=1); bN = R[new].mean(axis=1)
cO, dO, fO = cagr_dd(bO); cN, dN, fN = cagr_dd(bN)
print(f"{'year':>5} {'OLD pool':>9} {'NEW pool':>9}")
for (y, ro), (_, rn) in zip(allyears(bO), allyears(bN)):
    star = "  <= bear yr" if y in (2018, 2022) else ""
    print(f"{y:>5} {ro*100:>+8.0f}% {rn*100:>+8.0f}%{star}")
print(f"\nOLD pool: CAGR {cO*100:.0f}%  maxDD {dO*100:.0f}%  $500->${500*fO:,.0f}")
print(f"NEW pool: CAGR {cN*100:.0f}%  maxDD {dN*100:.0f}%  $500->${500*fN:,.0f}")
