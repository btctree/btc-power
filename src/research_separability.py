"""THE USER'S HYPOTHESIS TEST: 'profit markets and loss markets must have some hidden hint that
separates them — find/create new definitions.' Systematic search:
  label[t] = does Growth-A make money over the NEXT 60 days? (the thing we want to separate)
  features[t] = 14 candidate 'new definitions', ALL trailing (no look-ahead):
    efficiency ratios (Kaufman 20/60d), variance-ratio (trending vs mean-reverting), lag-1
    autocorrelation, vol & vol-of-vol, vol ratio 20/60, trend slope & |slope|, dist vs SMA200,
    drawdown depth & duration, strategy's OWN trailing 60d pnl (equity-curve momentum), funding rank.
  Score: AUC (rank separation) on TRAIN 2014-2020 vs TEST 2021-2026.
  AUC 0.5 = no separation. If any feature/combination separates OOS, build it as a filter and show
  the yearly effect. If not, the hint does not exist in observable data. 50bp costs throughout.
"""
import os, numpy as np, pandas as pd
import stable_combo as sc, live_engine as le
ANN = 365
df, reg0, memb = sc.prep(); reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy(); sma200 = df["SMA200"].to_numpy()
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
    """Growth A with optional exposure multiplier array. Returns equity + daily strategy returns."""
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

eq_base, dr = sim()
sret = pd.Series(dr, index=dates)
# ---- label: forward 60d strategy return > 0 ----
H = 60
fwd = (1 + sret).rolling(H).apply(np.prod, raw=True).shift(-H) - 1
label = (fwd > 0).astype(float); label[fwd.isna()] = np.nan

# ---- candidate features (ALL trailing) ----
c_ = pd.Series(close, index=dates); r1 = c_.pct_change()
F = {}
F["eff_ratio_20"] = (c_.diff(20).abs() / r1.abs().rolling(20).sum() / c_.shift(20)).replace([np.inf, -np.inf], np.nan) * c_.shift(20) / 1  # Kaufman ER
F["eff_ratio_20"] = c_.diff(20).abs() / (c_.diff().abs().rolling(20).sum())
F["eff_ratio_60"] = c_.diff(60).abs() / (c_.diff().abs().rolling(60).sum())
v5 = r1.rolling(5).sum().rolling(120).var(); v1 = r1.rolling(120).var()
F["variance_ratio"] = v5 / (5 * v1)                       # >1 trending, <1 mean-reverting
F["autocorr_60"] = r1.rolling(60).apply(lambda x: pd.Series(x).autocorr(1), raw=False)
F["vol_20"] = r1.rolling(20).std()
F["vol_ratio_20_60"] = r1.rolling(20).std() / r1.rolling(60).std()
F["vol_of_vol"] = r1.rolling(20).std().rolling(60).std()
sl = pd.Series(sma200, index=dates)
F["slope50_20"] = pd.Series(df["SMA50"].to_numpy(), index=dates).pct_change(20)
F["abs_slope"] = F["slope50_20"].abs()
F["dist_sma200"] = c_ / sl - 1
F["dd_depth"] = c_ / c_.cummax() - 1
F["dd_duration"] = (c_ != c_.cummax()).astype(int).groupby((c_ == c_.cummax()).cumsum()).cumsum().astype(float)
F["strat_mom_60"] = (1 + sret).rolling(60).apply(np.prod, raw=True) - 1     # equity-curve momentum
F["funding_rank"] = pd.Series(fr_, index=dates)
X = pd.DataFrame(F)

def auc(x, y):
    m = x.notna() & y.notna()
    x, y = x[m], y[m]
    if y.nunique() < 2 or len(x) < 100: return np.nan
    r = x.rank(); n1 = (y == 1).sum(); n0 = (y == 0).sum()
    u = r[y == 1].sum() - n1 * (n1 + 1) / 2
    return u / (n1 * n0)

split = "2021-01-01"
tr = dates < split; te = dates >= split
ytr = label[tr.values]; yte = label[te.values]
print(f"label balance: train {ytr.mean()*100:.0f}% profitable-forward days, test {yte.mean()*100:.0f}%")
print(f"\n{'feature':18s} {'AUC train':>10} {'AUC test':>9}   (0.50 = cannot separate; >0.60 = useful)")
rows = []
for k in X.columns:
    a_tr = auc(X[k][tr.values], ytr); a_te = auc(X[k][te.values], yte)
    a_tr2 = max(a_tr, 1 - a_tr) if a_tr == a_tr else np.nan   # allow inverted direction
    a_te_dir = a_te if a_tr >= 0.5 else (1 - a_te)             # apply TRAIN-chosen direction to test
    rows.append((k, a_tr2, a_te_dir))
    print(f"{k:18s} {a_tr2:>10.3f} {a_te_dir:>9.3f}")
rows.sort(key=lambda x: -(x[1] if x[1] == x[1] else 0))
top3 = [r[0] for r in rows[:3]]
# combined score: mean of train-direction z-scores of top-3
Z = pd.DataFrame()
for k in top3:
    d = 1.0 if auc(X[k][tr.values], ytr) >= 0.5 else -1.0
    mu, sd = X[k][tr.values].mean(), X[k][tr.values].std()
    Z[k] = d * (X[k] - mu) / sd
score = Z.mean(axis=1)
print(f"\ncombined top-3 {top3}: AUC train {auc(score[tr.values], ytr):.3f} | AUC test {auc(score[te.values], yte):.3f}")

# ---- filter test: reduce exposure when score is in the worst train-tercile ----
thr = score[tr.values].quantile(0.33)
mult = np.where(score.shift(1) < thr, 0.3, 1.0)   # act next day on yesterday's score
eq_f, dr_f = sim(mult_arr=mult)
def yearly(eq):
    s = pd.Series(eq, index=dates); out = {}
    for y in range(2014, 2027):
        seg = s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]
        out[y] = seg.iloc[-1] / seg.iloc[0] - 1 if len(seg) > 20 else np.nan
    return out
yb, yf = yearly(eq_base), yearly(eq_f)
print(f"\n{'year':>5} {'GrowthA base':>13} {'with filter':>12}")
for y in range(2014, 2027):
    if yb[y] != yb[y]: continue
    print(f"{y:>5} {yb[y]*100:>+12.0f}% {yf[y]*100:>+11.0f}%{'  <= loss yr' if y in (2018,2022,2025) else ''}")
print(f"FINAL  ${eq_base[-1]:>12,.0f} ${eq_f[-1]:>11,.0f}")
