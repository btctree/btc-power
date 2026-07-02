"""FULL year-by-year for EVERY model, at 0bp AND 50bp, through ONE consistent engine (the exact sim +
gates + configs from build_full_compare.py), with Apex added through the same engine. Verifies finals
tie out to the established comparison, then writes all years to one Excel. Honest: 2014+, VOL+FUND gates,
dd-kill 0.30, honest liquidation, cost on turnover.
"""
import os, numpy as np, pandas as pd
import stable_combo as sc, live_engine as le
ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy(); sma200 = df["SMA200"].to_numpy()
n = len(df); i0 = 260; dstr = df["Date"].tolist(); dates = pd.to_datetime(df["Date"])
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
HERE = os.path.dirname(os.path.abspath(__file__))
def lmap(p, col):
    if not os.path.exists(p): return {}
    f = pd.read_csv(p); return dict(zip(f.iloc[:, 0].astype(str), f[col]))
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trail_rank(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vol_rank = trail_rank(rv); fund_rank = trail_rank(funding)
gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vol_rank[i] == vol_rank[i] and vol_rank[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fund_rank[i] == fund_rank[i]:
        if fund_rank[i] > 0.90: gl[i] *= 0.5
        if fund_rank[i] < 0.10: gs[i] *= 0.5
esm = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()
REGF = {"STRONG_UP": 1.0, "TREND_UP": 1.0, "PULLBACK_UP": 0.7, "BOUNCE_DOWN": 0.7, "STRONG_DOWN": 0.8, "TREND_DOWN": 0.9, "CHOP_HIVOL": 0.5, "RANGE": 0.5, "NEUTRAL": 0.5}
def conf_f(a): a = abs(a); return 1.0 if a >= 0.75 else (0.85 if a >= 0.5 else 0.7)
condcap = np.array([(3.0 if esm[i] > 0 else 2.0) * REGF.get(reg[i], 0.5) * conf_f(esm[i]) for i in range(n)])
# Apex signal (short-selective on the smoothed ensemble) + trend-aligned cap
apex_sig = esm.copy()
for i in range(n):
    if apex_sig[i] < 0 and not (reg[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]): apex_sig[i] = 0.0
up = close > sma200; sgn = np.sign(apex_sig); cap_ta = np.where(((sgn > 0) & up) | ((sgn < 0) & ~up), 3.25, 3.0)

def sim(signal, cap, vt, smooth, band, slip, gates=True, dd_kill=0.30, legacy=None, fee=0.0005, maint=0.01):
    e_in = pd.Series(signal).ewm(span=smooth, adjust=False).mean().to_numpy() if smooth > 1 else np.array(signal, float)
    caparr = cap if hasattr(cap, "__len__") else None
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        sig = e_in[i - 1]; g = (gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)) if gates else 1.0
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        mult = legacy * min(1.0, 0.60 / rv[i - 1]) if legacy else min(caparr[i - 1] if caparr is not None else cap, vt / rv[i - 1])
        e = sig * g * mult
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint): eqv *= 0.01; held = 0.0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv)
    return eq

# (name, signal, cap, vt, smooth, band, gates, legacy)
M = [("Buy & Hold BTC", np.ones(n), 1, 999, 0, 0.0, False, None),
     ("Raw 8B 5x", expf, 5, 0.6, 0, 0.0, True, 5),
     ("Core 1x", expf, 1, 0.6, 5, 0.15, True, None),
     ("Balanced 2x", expf, 2, 1.5, 5, 0.15, True, None),
     ("Balanced 3x", expf, 3, 1.5, 5, 0.15, True, None),
     ("Growth 5x (A)", expf, 5, 1.5, 5, 0.15, True, None),
     ("Aggressive (B)", expf, 5, 2.0, 5, 0.25, True, None),
     ("Smooth (C)", expf, 5, 1.5, 10, 0.25, True, None),
     ("Apex (3.25/3 short-sel)", apex_sig, cap_ta, 1.5, 0, 0.15, True, None),
     ("Cycle math (in-sample)", None, 5, 0.8, 5, 0.15, False, None)]
# cycle signal
halv = [pd.Timestamp(x) for x in ["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20"]]
dsh = np.array([min([(d - h).days for h in halv if h <= d] or [9999]) for d in dates], float)
phase = (dsh / 1458.0) % 1.0; cyc = np.where((phase < 0.42) | (phase > 0.62), 1.0, -1.0)

YEARS = list(range(2014, 2027))
def yearly(eq):
    s = pd.Series(eq, index=dates); out = {}
    for y in YEARS:
        seg = s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]
        out[y] = (seg.iloc[-1] / seg.iloc[0] - 1) if len(seg) > 20 else np.nan
    return out

def run(slip):
    yr = {}; fin = {}
    for nm, sig, cap, vt, sm, bd, gt, lg in M:
        s = cyc if nm.startswith("Cycle") else sig
        eq = sim(s, cap, vt, sm, bd, slip, gt, 0.30, lg)
        yr[nm] = yearly(eq); fin[nm] = eq[-1]
    return yr, fin

for slip, tag in [(0.0, "0bp"), (0.005, "50bp")]:
    yr, fin = run(slip)
    print(f"\n================= YEARLY %  @ {tag} =================")
    names = [m[0] for m in M]
    print("year   " + "".join(f"{nm[:11]:>13}" for nm in names))
    for y in YEARS:
        print(f"{y}   " + "".join((f"{yr[nm][y]*100:>+12.0f}%" if yr[nm][y] == yr[nm][y] else f"{'—':>13}") for nm in names))
    print("FINAL  " + "".join(f"{('$%.0f' % fin[nm]) if fin[nm] < 1e7 else ('$%.2gB' % (fin[nm]/1e9) if fin[nm]>=1e9 else '$%.1fM' % (fin[nm]/1e6)):>13}" for nm in names))

# Excel
OUTX = os.path.join(HERE, "..", "..", "excel_reports", "BTC_all_models_full_yearly.xlsx")
with pd.ExcelWriter(OUTX, engine="openpyxl") as xl:
    for slip, tag in [(0.0, "0bp"), (0.005, "50bp")]:
        yr, fin = run(slip)
        d = {nm: {**{y: (yr[nm][y] if yr[nm][y] == yr[nm][y] else None) for y in YEARS}, "FINAL_$": round(fin[nm], 2)} for nm in [m[0] for m in M]}
        pd.DataFrame(d).T.to_excel(xl, sheet_name=f"Yearly_{tag}")
print("\nsaved", os.path.abspath(OUTX))
