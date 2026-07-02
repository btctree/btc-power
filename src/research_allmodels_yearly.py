"""Year-by-year % for every leveraged BTC model, at 0bp AND 50bp, on the same data (2013-2026).
Models via the same volatility-targeting engine (stable_combo.simulate) except Apex (its own sim).
Cycle-timing excluded: it's in-sample/look-ahead (not a real deployable model). Saves an Excel too.
"""
import os, numpy as np, pandas as pd
import live_engine as le, stable_combo as sc
ANN = 365
df, reg, memb = le.setup(); r2, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
dates = pd.to_datetime(df["Date"]); n = len(df); i0 = 260
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy(); sma200 = df["SMA200"].to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)

# --- Apex sim (own engine) ---
e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy().copy()
for i in range(n):
    if e_in[i] < 0 and not (reg[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]): e_in[i] = 0.0
up = close > sma200; sg = np.sign(e_in); cap_ta = np.where(((sg > 0) & up) | ((sg < 0) & ~up), 3.25, 3.0)
p = os.path.join(le.HERE, "..", "data", "funding.csv")
fm = dict(zip(*[pd.read_csv(p)[c] for c in ["date", "funding_rate"]])) if os.path.exists(p) else {}
fund = np.array([fm.get(d, np.nan) for d in df["Date"]])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean()).to_numpy()
vr = trk(rv); fr = trk(fund); gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5
def apex(slip, vt=1.5):
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        s = e_in[i - 1]; g = gl[i - 1] if s > 0 else (gs[i - 1] if s < 0 else 1.0)
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        e = s * g * min(cap_ta[i - 1], vt / rv[i - 1])
        if eqv < peak * 0.70: e *= 0.5
        if abs(e - held) < 0.15 and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= 0.99: eqv *= 0.01; held = 0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (0.0005 + slip); held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv)
    return eq

MODELS = {
    "Raw 8B 5x": lambda sl: np.array(sc.simulate(df, expf, lev=5, slip=sl, vol_target=0.60, dd_kill=0.0)[0]),
    "8B 5x (dd-kill)": lambda sl: np.array(sc.simulate(df, expf, lev=5, slip=sl, vol_target=0.60, dd_kill=0.30)[0]),
    "Growth 5x (A)": lambda sl: np.array(sc.simulate(df, expf, lev=5, slip=sl, vol_target=1.5, smooth=5, band=0.15, dd_kill=0.30)[0]),
    "Aggressive (B)": lambda sl: np.array(sc.simulate(df, expf, lev=5, slip=sl, vol_target=2.0, smooth=5, band=0.25, dd_kill=0.30)[0]),
    "Smooth (C)": lambda sl: np.array(sc.simulate(df, expf, lev=5, slip=sl, vol_target=1.5, smooth=10, band=0.25, dd_kill=0.30)[0]),
    "Apex": lambda sl: apex(sl),
}
YEARS = list(range(2014, 2027))
def yearly(eq):
    s = pd.Series(eq, index=dates); out = {}
    for y in YEARS:
        seg = s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]
        out[y] = (seg.iloc[-1] / seg.iloc[0] - 1) if len(seg) > 20 else np.nan
    return out, s.iloc[-1]

for sl, tag in [(0.0, "0bp"), (0.005, "50bp")]:
    print(f"\n================ YEARLY RETURN %  @ {tag} ================")
    yr = {}; fin = {}
    for name, fn in MODELS.items():
        yr[name], fin[name] = yearly(fn(sl))
    hdr = "year  " + "".join(f"{m[:13]:>15}" for m in MODELS)
    print(hdr)
    for y in YEARS:
        print(f"{y}  " + "".join(f"{yr[m][y]*100:>+14.0f}%" if yr[m][y] == yr[m][y] else f"{'—':>15}" for m in MODELS))
    print("FINAL " + "".join(f"${fin[m]:>14,.0f}" for m in MODELS))

# Excel
OUTX = os.path.join(le.HERE, "..", "..", "excel_reports", "BTC_all_models_yearly.xlsx")
with pd.ExcelWriter(OUTX, engine="openpyxl") as xl:
    for sl, tag in [(0.0, "0bp"), (0.005, "50bp")]:
        rows = {}
        for name, fn in MODELS.items():
            y, f = yearly(fn(sl)); y["FINAL_$"] = f; rows[name] = y
        pd.DataFrame(rows).to_excel(xl, sheet_name=f"yearly_{tag}")
print("\nsaved", os.path.abspath(OUTX))
