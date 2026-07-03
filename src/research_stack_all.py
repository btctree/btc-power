"""1) 2025-chop fix: chop-ADAPTIVE deadband (trailing Kaufman efficiency-ratio rank; low trendiness ->
   wider deadband 0.15->0.30 = trade less in chop). Cost-control, not signal mining; continuous, no
   magic threshold. Tested on Steady-A and Max-B first.
2) Apply the protection stack (200WMA floor + Pi Cycle x0.5/365d [+adaptive band if it works]) to ALL
   legacy models: Raw 8B 5x, Balanced 3x, Aggressive B, Smooth C, Apex.
3) Full all-year compare, 0bp and 50bp, for the 7 models -> console + Excel.
"""
import os, numpy as np, pandas as pd
from live_engine import setup, ensemble_ctx, HERE
from global_engine import fetch_yahoo
ANN = 365
df, reg0, memb = setup(); reg, emap, exp_raw = ensemble_ctx(df, memb)
dates = pd.to_datetime(df["Date"]); dstr = df["Date"].tolist(); n = len(df); i0 = 260
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy(); sma200 = df["SMA200"].to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
esm5 = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()
esm10 = pd.Series(expf).ewm(span=10, adjust=False).mean().to_numpy()
apex_sig = esm5.copy()
for i in range(n):
    if apex_sig[i] < 0 and not (reg[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]): apex_sig[i] = 0.0
up = close > sma200; sgA = np.sign(apex_sig)
cap_ta = np.where(((sgA > 0) & up) | ((sgA < 0) & ~up), 3.25, 3.0)
def lmap(p, c): return dict(zip(pd.read_csv(p).iloc[:, 0].astype(str), pd.read_csv(p)[c])) if os.path.exists(p) else {}
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); fr = trk(funding); gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5
u = fetch_yahoo("UUP", refresh=False)
uup = pd.Series(u["close"].values, index=pd.to_datetime(u["date"])).reindex(dates).ffill()
dollar_strong = (uup > uup.rolling(200).mean()).shift(1).fillna(False).to_numpy()
c_ = pd.Series(close, index=dates)
wma200 = c_.rolling(1400).mean(); below_200w = (c_ < wma200).shift(1).fillna(False).to_numpy()
m111 = c_.rolling(111).mean(); m350x2 = 2 * c_.rolling(350).mean()
above = (m111 > m350x2).to_numpy(); pi_alarm = np.zeros(n, bool); lc = -10**9
for i in range(1, n):
    if above[i] and not above[i - 1]: lc = i
    if i - lc <= 365: pi_alarm[i] = True
pi_alarm = np.roll(pi_alarm, 1); pi_alarm[0] = False
# chop-adaptive deadband input: Kaufman ER(20d), trailing 1y rank, shifted (no look-ahead)
er20 = (c_.diff(20).abs() / c_.diff().abs().rolling(20).sum())
er_rank = er20.rolling(252, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).shift(1).fillna(0.5).to_numpy()

def sim(sig, cap, vt, band, slip, legacy=None, dgate=0.0, floor=False, pi=False, adband=False,
        dd_kill=0.30, fee=0.0005, maint=0.01):
    caparr = cap if hasattr(cap, "__len__") else None
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        s = sig[i - 1]; g = gl[i - 1] if s > 0 else (gs[i - 1] if s < 0 else 1.0)
        if dgate and dollar_strong[i - 1]: g *= dgate
        if floor and s < 0 and below_200w[i]: g = 0.0
        if pi and pi_alarm[i]: g *= 0.5
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        mult = legacy * min(1.0, 0.60 / rv[i - 1]) if legacy else min(caparr[i - 1] if caparr is not None else cap, vt / rv[i - 1])
        e = s * g * mult
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        b = band
        if adband and band > 0: b = band * (1.0 + (1.0 - er_rank[i]))     # 0.15 trending -> 0.30 full chop
        if b > 0 and abs(e - held) < b and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint): eqv *= 0.01; held = 0.0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv)
    return eq

def yearly(eq):
    s = pd.Series(eq[i0:], index=dates[i0:]); out = {}
    for y in range(2014, 2027):
        seg = s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]
        if len(seg) > 20: out[y] = seg.iloc[-1] / seg.iloc[0] - 1
    return out, float(s.iloc[-1])

# ---- step 1: does the adaptive band fix 2025 (without hurting elsewhere)? on A and B ----
print("=== 2025 FIX TEST: chop-adaptive deadband ===")
A = dict(sig=esm5, cap=2, vt=1.5, band=0.15, dgate=0.5, floor=True, pi=True)
B = dict(sig=esm5, cap=5, vt=1.5, band=0.15, floor=True, pi=True)
for nm, kw in [("A Steady", A), ("B Max", B)]:
    for ab in (False, True):
        y, f = yearly(sim(slip=0.005, adband=ab, **kw))
        tag = "+adaptive-band" if ab else "fixed band    "
        print(f"{nm} {tag}: 2024 {y.get(2024,0)*100:+.0f}%  2025 {y.get(2025,0)*100:+.0f}%  2026 {y.get(2026,0)*100:+.0f}%  FINAL ${f:,.0f}")

# ---- step 2+3: stack on every legacy model; full yearly 0bp+50bp -> console + Excel ----
MODELS = [
    ("Steady Million (A)", dict(sig=esm5, cap=2, vt=1.5, band=0.15, dgate=0.5, floor=True, pi=True)),
    ("Max (B)", dict(sig=esm5, cap=5, vt=1.5, band=0.15, floor=True, pi=True)),
    ("Raw 8B 5x +stack", dict(sig=expf, cap=5, vt=0.6, band=0.0, legacy=5, floor=True, pi=True)),
    ("Balanced 3x +stack", dict(sig=esm5, cap=3, vt=1.5, band=0.15, floor=True, pi=True)),
    ("Aggressive B +stack", dict(sig=esm5, cap=5, vt=2.0, band=0.25, floor=True, pi=True)),
    ("Smooth C +stack", dict(sig=esm10, cap=5, vt=1.5, band=0.25, floor=True, pi=True)),
    ("Apex +stack", dict(sig=apex_sig, cap=cap_ta, vt=1.5, band=0.15, floor=True, pi=True)),
]
BASE_FINALS = {"Raw 8B 5x +stack": ("$13,331", "base Raw 8B"), "Balanced 3x +stack": ("$931,379", "base Bal3x"),
               "Aggressive B +stack": ("$3,978,428", "base AggrB"), "Smooth C +stack": ("$1,768,003", "base SmoothC"),
               "Apex +stack": ("$1,198,372", "base Apex")}
OUTX = os.path.join(HERE, "..", "..", "excel_reports", "BTC_stack_all_models.xlsx")
sheets = {}
for slip, tag in [(0.0, "0bp"), (0.005, "50bp")]:
    print(f"\n================ FULL YEARLY @ {tag} (all models WITH floor+Pi stack) ================")
    names = [m[0] for m in MODELS]
    tbl = {}
    ys_all = {}
    for nm, kw in MODELS:
        y, f = yearly(sim(slip=slip, **kw)); ys_all[nm] = (y, f)
        tbl[nm] = {**{yy: y.get(yy) for yy in range(2014, 2027)}, "FINAL_$": f}
    print("year   " + "".join(f"{nm[:14]:>16}" for nm in names))
    for yy in range(2014, 2027):
        print(f"{yy}   " + "".join((f"{ys_all[nm][0].get(yy, float('nan'))*100:>+15.0f}%" if ys_all[nm][0].get(yy) is not None else f"{'—':>16}") for nm in names))
    print("FINAL  " + "".join(f"{('$%.0f' % ys_all[nm][1]) if ys_all[nm][1] < 1e6 else ('$%.2fM' % (ys_all[nm][1]/1e6) if ys_all[nm][1] < 1e9 else '$%.2fB' % (ys_all[nm][1]/1e9)):>16}" for nm in names))
    sheets[tag] = pd.DataFrame(tbl)
with pd.ExcelWriter(OUTX, engine="openpyxl") as xl:
    for tag, d in sheets.items():
        d.T.to_excel(xl, sheet_name=f"Yearly_{tag}")
print("\nlegacy base finals @50bp for comparison:", {k: v[0] for k, v in BASE_FINALS.items()})
print("saved", os.path.abspath(OUTX))
