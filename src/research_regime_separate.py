"""Can we separate the losing-year 'market type' and cash it out, greening all years WITHOUT hurting
good years? Test: (A) PERFECT-HINDSIGHT (cash in calendar 2018/2022/2025 = look-ahead CHEAT, shows the
ceiling), vs (B) REAL-TIME regime detectors (no look-ahead). Base = Growth A leveraged (cap5,vt1.5).
The gap between A and B = the cost of not knowing the future. 50bp.
"""
import os, numpy as np, pandas as pd
import stable_combo as sc, live_engine as le
ANN = 365
df, reg0, memb = sc.prep(); reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy(); sma200 = df["SMA200"].to_numpy()
n = len(df); i0 = 260; dstr = df["Date"].tolist(); dates = pd.to_datetime(df["Date"]); yrarr = dates.dt.year.to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
HERE = os.path.dirname(os.path.abspath(__file__))
def lmap(p, c): return dict(zip(pd.read_csv(p).iloc[:, 0].astype(str), pd.read_csv(p)[c])) if os.path.exists(p) else {}
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); fr = trk(funding); gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5
esm = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()

def sim(mask_flat, cap=5, vt=1.5, band=0.15, slip=0.005, dd_kill=0.30, fee=0.0005, maint=0.01):
    # mask_flat[i]=True -> forced flat that day
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        s = 0.0 if mask_flat[i - 1] else esm[i - 1]
        g = gl[i - 1] if s > 0 else (gs[i - 1] if s < 0 else 1.0)
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        e = s * g * min(cap, vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint): eqv *= 0.01; held = 0.0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv)
    return eq
YEARS = list(range(2014, 2027))
def yr(eq):
    s = pd.Series(eq, index=dates); return {y: (s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")].iloc[-1] /
        s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")].iloc[0] - 1) if len(s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]) > 20 else np.nan for y in YEARS}

# masks
none = np.zeros(n, bool)
hindsight = np.isin(yrarr, [2018, 2022, 2025])                                  # CHEAT: knows bad years
badreg = np.array([reg[i] in ("CHOP_HIVOL", "RANGE") for i in range(n)])        # real-time: cash in chop/range
bear = np.array([(reg[i] in ("CHOP_HIVOL", "RANGE", "STRONG_DOWN", "TREND_DOWN", "BOUNCE_DOWN")) or close[i] < sma200[i] for i in range(n)])  # real-time: only clean uptrends

tests = [("Growth A base (no mask)", none), ("A) PERFECT-HINDSIGHT cash 18/22/25 [CHEAT]", hindsight),
         ("B1) real-time: cash in CHOP/RANGE", badreg), ("B2) real-time: only clean uptrends", bear)]
print(f"{'variant':40s} " + "".join(f"{y:>6}" for y in YEARS) + " | FINAL  neg")
for nm, mask in tests:
    eq = sim(mask); Y = yr(eq); neg = sum(1 for y in YEARS if Y[y] == Y[y] and Y[y] < 0)
    row = "".join((f"{Y[y]*100:>+5.0f}%" if Y[y] == Y[y] else f"{'—':>6}") for y in YEARS)
    print(f"{nm:40s} {row} | ${eq[-1]:>10,.0f} {neg}")
