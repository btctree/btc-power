"""ROUND 2 of the hidden-hint search — NEW information sources (not BTC price derivatives):
  MACRO: S&P trend/momentum, dollar (UUP) trend/momentum, rates (TLT), gold, equity vol
  VOLUME: BTC volume trend, OBV slope
  STRUCTURE: BB-width squeeze rank, price acceleration, up-day ratio
Same discipline: label = Growth-A profitable over next 60d; AUC train(2014-20) vs test(2021-26).
PLUS one hypothesis-driven (not mined) filter: classic RISK-OFF = SPY<SMA200 & UUP>SMA200 -> cut BTC
exposure. Applied directly to Growth A @50bp with yearly breakdown. Multiple-testing warning: ~30
features tested across both rounds -> 1-2 will show test AUC ~0.6 by luck; demand train AND test both
elevated + a plausible mechanism before believing anything.
"""
import os, numpy as np, pandas as pd
import stable_combo as sc, live_engine as le
from global_engine import fetch_yahoo
ANN = 365
df, reg0, memb = sc.prep(); reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
volu = df["volume"].to_numpy() if "volume" in df else np.ones(len(df))
n = len(df); i0 = 260; dstr = df["Date"].tolist(); dates = pd.to_datetime(df["Date"])
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
HERE = os.path.dirname(os.path.abspath(__file__))
def lmap(p, c): return dict(zip(pd.read_csv(p).iloc[:, 0].astype(str), pd.read_csv(p)[c])) if os.path.exists(p) else {}
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr_ = trk(rv); fr_ = trk(funding); gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr_[i] == vr_[i] and vr_[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr_[i] == fr_[i]:
        if fr_[i] > 0.90: gl[i] *= 0.5
        if fr_[i] < 0.10: gs[i] *= 0.5
esm = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()

def sim(mult_arr=None, cap=5, vt=1.5, band=0.15, slip=0.005, dd_kill=0.30, fee=0.0005, maint=0.01):
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); dr = np.zeros(n)
    for i in range(i0, n):
        s = esm[i - 1] * (mult_arr[i - 1] if mult_arr is not None else 1.0)
        g = gl[i - 1] if s > 0 else (gs[i - 1] if s < 0 else 1.0)
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        e = s * g * min(cap, vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        prev = eqv
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint): eqv *= 0.01; held = 0.0; eq[i] = eqv; dr[i] = eqv / prev - 1; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); dr[i] = eqv / prev - 1; peak = max(peak, eqv)
    return eq, dr

eq_base, dr = sim(); sret = pd.Series(dr, index=dates)
H = 60
fwd = (1 + sret).rolling(H).apply(np.prod, raw=True).shift(-H) - 1
label = (fwd > 0).astype(float); label[fwd.isna()] = np.nan

def macro(tk):
    d = fetch_yahoo(tk, refresh=False)
    s = pd.Series(d["close"].values, index=pd.to_datetime(d["date"])).reindex(dates).ffill()
    return s
spy, uup, tlt, gld = macro("SPY"), macro("UUP"), macro("TLT"), macro("GLD")
c_ = pd.Series(close, index=dates); r1 = c_.pct_change()
F = {}
F["spx_trend"] = (spy / spy.rolling(200).mean() - 1)
F["spx_mom60"] = spy.pct_change(60)
F["dxy_trend"] = (uup / uup.rolling(200).mean() - 1)
F["dxy_mom60"] = uup.pct_change(60)
F["tlt_mom60"] = tlt.pct_change(60)
F["gold_mom60"] = gld.pct_change(60)
F["eqvol_20"] = spy.pct_change().rolling(20).std()
F["btc_spx_corr60"] = r1.rolling(60).corr(spy.pct_change())
F["vol_trend"] = pd.Series(volu, index=dates).rolling(20).mean() / pd.Series(volu, index=dates).rolling(100).mean()
obv = (np.sign(r1.fillna(0)) * pd.Series(volu, index=dates)).cumsum()
F["obv_slope20"] = obv.diff(20) / pd.Series(volu, index=dates).rolling(20).mean()
bbw = (pd.Series(df["BB_Upper"].to_numpy(), index=dates) - pd.Series(df["BB_Lower"].to_numpy(), index=dates)) / pd.Series(df["SMA20"].to_numpy(), index=dates)
F["bb_squeeze_rank"] = bbw.rolling(252, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False)
F["accel_20"] = c_.pct_change(20) - c_.pct_change(20).shift(20)
F["updays_20"] = (r1 > 0).rolling(20).mean()
X = pd.DataFrame(F)

def auc(x, y):
    m = x.notna() & y.notna(); x, y = x[m], y[m]
    if y.nunique() < 2 or len(x) < 100: return np.nan
    r = x.rank(); n1 = (y == 1).sum(); n0 = (y == 0).sum()
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)

split = "2021-01-01"; tr = (dates < split).values; te = (dates >= split).values
ytr, yte = label[tr], label[te]
print(f"{'feature':>18s} {'AUC train':>10} {'AUC test':>9}")
for k in X.columns:
    a_tr = auc(X[k][tr], ytr); a_te = auc(X[k][te], yte)
    d = 1 if (a_tr == a_tr and a_tr >= 0.5) else -1
    a_trd = a_tr if d == 1 else 1 - a_tr; a_ted = a_te if d == 1 else 1 - a_te
    print(f"{k:>18s} {a_trd:>10.3f} {a_ted:>9.3f}")

# hypothesis-driven risk-off filter (NOT mined): SPY<SMA200 & UUP>SMA200 -> multiplier 0.3
risk_off = ((spy < spy.rolling(200).mean()) & (uup > uup.rolling(200).mean()))
mult = np.where(risk_off.shift(1).fillna(False), 0.3, 1.0)
eq_f, _ = sim(mult_arr=mult)
def yearly(eq):
    s = pd.Series(eq, index=dates); out = {}
    for y in range(2014, 2027):
        seg = s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]
        out[y] = seg.iloc[-1] / seg.iloc[0] - 1 if len(seg) > 20 else np.nan
    return out
yb, yf = yearly(eq_base), yearly(eq_f)
print(f"\nHYPOTHESIS FILTER: risk-off (SPY<SMA200 & UUP>SMA200) -> cut to 30% | days flagged: {int(risk_off.sum())}")
print(f"{'year':>5} {'GrowthA base':>13} {'macro filter':>13}")
for y in range(2014, 2027):
    if yb[y] != yb[y]: continue
    print(f"{y:>5} {yb[y]*100:>+12.0f}% {yf[y]*100:>+12.0f}%{'  <= loss yr' if y in (2018,2022,2025) else ''}")
print(f"FINAL  ${eq_base[-1]:>12,.0f} ${eq_f[-1]:>12,.0f}")

# FOLLOW-THROUGH: the one cross-validated hint (dollar trend) as a direct filter, two strengths
print("\nDIRECT DOLLAR-TREND FILTER (UUP > SMA200 -> cut exposure):")
for m0, lbl in [(0.5, "gentle 50%"), (0.3, "strong 30%")]:
    mult = np.where((uup > uup.rolling(200).mean()).shift(1).fillna(False), m0, 1.0)
    eq_d, _ = sim(mult_arr=mult); yd = yearly(eq_d)
    row = " ".join(f"{y}:{yd[y]*100:+.0f}%" for y in (2018, 2019, 2020, 2022, 2023, 2025))
    print(f"  {lbl:12s} {row}   FINAL ${eq_d[-1]:,.0f}")
print(f"  {'base':12s} " + " ".join(f"{y}:{yb[y]*100:+.0f}%" for y in (2018, 2019, 2020, 2022, 2023, 2025)) + f"   FINAL ${eq_base[-1]:,.0f}")
