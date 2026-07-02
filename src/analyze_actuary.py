"""ACTUARY: mine the full dataset, fit a walk-forward linear 'formula' predicting the forward
5-day return (sign = long/short signal). Reports out-of-sample skill (IC, directional accuracy),
the discovered coefficients (the relationships), and a backtest vs the B model. Honest: causal
z-scores, expanding-window refits (no look-ahead), 5bp fees + slippage in the backtest.
"""
import os
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le

ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
c = df["close"]; close = c.to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
vol = df["volume"]; n = len(df); i0 = 260; dstr = df["Date"].tolist(); dates = pd.to_datetime(df["Date"])
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
HERE = os.path.dirname(os.path.abspath(__file__))
def lmap(p, col):
    if not os.path.exists(p): return {}
    f = pd.read_csv(p); return dict(zip(f.iloc[:, 0].astype(str), f[col]))
mvrv = pd.Series([lmap(os.path.join(HERE, "..", "data", "onchain.csv"), "mvrv").get(d, np.nan) for d in dstr]).astype(float)
fng = pd.Series([lmap(os.path.join(HERE, "..", "data", "fng.csv"), "fng").get(d, np.nan) for d in dstr]).astype(float)
ofl = pd.Series([lmap(os.path.join(HERE, "..", "data", "orderflow.csv"), "buy_frac").get(d, np.nan) for d in dstr]).astype(float)
fund = pd.Series([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr]).astype(float)

# ---- raw features (causal) ----
RSI = df["RSI"]; MACD = df["MACD"]; SIG = df["SignalLine"]; MFI = df["MFI"]
OBV = (np.sign(c.diff()).fillna(0) * vol).cumsum()          # numeric OBV (df['OBV'] is a label)
ADX = df["ADX"]; PDI = df["PDI"]; MDI = df["MDI"]; ATRp = df["ATRpct"]; bbw = df["bbw"]; slope50 = df["slope50"]
bbmid = (df["BB_Upper"] + df["BB_Lower"]) / 2
raw = pd.DataFrame({
    "rsi": (RSI - 50) / 50,
    "macd_h": (MACD - SIG) / c,
    "mfi": (MFI - 50) / 50,
    "roc": df["ROC"],
    "adx_dir": (PDI - MDI) / 100 * (ADX / 50),
    "atr": ATRp,
    "bb_pos": (c - bbmid) / (df["BB_Upper"] - df["BB_Lower"] + 1e-9),
    "sma20r": c / df["SMA20"] - 1, "sma50r": c / df["SMA50"] - 1, "sma200r": c / df["SMA200"] - 1,
    "slope50": slope50,
    "mom5": c / c.shift(5) - 1, "mom10": c / c.shift(10) - 1, "mom20": c / c.shift(20) - 1,
    "obv_slope": (OBV - OBV.shift(10)) / vol.rolling(20).mean(),
    "mvrv": mvrv, "mvrv_z": (mvrv - mvrv.rolling(365).mean()) / mvrv.rolling(365).std(),
    "fng": (fng.fillna(50) - 50) / 50,
    "oflow": (ofl - 0.5) * 2, "oflow_z": (ofl - ofl.rolling(60).mean()) / ofl.rolling(60).std(),
    "oflow_mom": ofl.rolling(5).mean() - 0.5,
    "fund_z": (fund - fund.rolling(180).mean()) / fund.rolling(180).std(),
})
# causal z-score + clip
Z = ((raw - raw.rolling(365, min_periods=120).mean()) / raw.rolling(365, min_periods=120).std()).clip(-4, 4)
Z["fund_z"] = raw["fund_z"].clip(-4, 4)            # already a z; keep (NaN pre-2020 -> filled 0 below)
feat_cols = list(Z.columns)
X = Z.to_numpy();
TARGET = (c.shift(-5) / c - 1).to_numpy()           # forward 5d return

# valid rows: order-flow start (2017-08) is the binding constraint; need finite features+target
def fillz(a):
    a = a.copy(); a[~np.isfinite(a)] = 0.0; return a   # missing feature -> neutral 0 (z)
Xf = np.column_stack([fillz(X[:, j]) for j in range(X.shape[1])])
have_of = np.isfinite(ofl.to_numpy())
valid = np.zeros(n, bool)
for i in range(i0, n - 5):
    if have_of[i] and np.isfinite(TARGET[i]) and np.isfinite(rv[i]):
        valid[i] = True
idxs = np.where(valid)[0]
print(f"Actuary dataset: {len(idxs)} days | {dstr[idxs[0]]} -> {dstr[idxs[-1]]} | {len(feat_cols)} features")

# ---- walk-forward expanding-window OLS ----
step = 90; min_train = 400
preds = np.full(n, np.nan); coef_accum = []
t = idxs[0] + min_train
while t < n - 5:
    tr = idxs[(idxs >= idxs[0]) & (idxs < t)]
    te = idxs[(idxs >= t) & (idxs < t + step)]
    if len(tr) < min_train or len(te) == 0:
        t += step; continue
    A = np.column_stack([np.ones(len(tr)), Xf[tr]]); y = TARGET[tr]
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    coef_accum.append(beta)
    B = np.column_stack([np.ones(len(te)), Xf[te]]); preds[te] = B @ beta
    t += step

pm = np.isfinite(preds) & valid
ic = np.corrcoef(preds[pm], TARGET[pm])[0, 1]
diracc = np.mean(np.sign(preds[pm]) == np.sign(TARGET[pm]))
print(f"\nOUT-OF-SAMPLE skill: IC(pred,fwd5) = {ic:.3f} | directional accuracy = {diracc*100:.1f}%")
print(f"  (IC>0.05 = usable; ensemble baseline below for comparison)")
# baseline: does the existing ensemble predict fwd5?
em = np.isfinite(expf) & pm
print(f"  existing ensemble exp vs fwd5: IC = {np.corrcoef(expf[em], TARGET[em])[0,1]:.3f} | dir acc {np.mean(np.sign(expf[em])==np.sign(TARGET[em]))*100:.1f}%")

# ---- discovered formula (avg standardized coefficients) ----
bavg = np.mean(np.array(coef_accum), axis=0)[1:]
order = np.argsort(-np.abs(bavg))
print("\nDISCOVERED RELATIONSHIPS (avg coefficient, standardized; + => higher feature -> higher fwd return):")
for j in order[:12]:
    print(f"  {feat_cols[j]:10s} {bavg[j]:+.5f}")

# ---- backtest the Actuary signal (vol-targeted) ----
def bt(signal, lev, slip, vt=0.60):
    sig = pd.Series(signal).rolling(3).mean().to_numpy()          # smooth
    sd = pd.Series(sig).rolling(120, min_periods=30).std().to_numpy()
    pos = np.clip(sig / (sd * 1.5 + 1e-9), -1, 1)                 # scale to [-1,1]
    eq = np.full(n, 500.0); equity = peak = 500.0; held = 0.0
    for i in range(i0, n):
        if not (np.isfinite(pos[i-1]) and np.isfinite(rv[i-1]) and rv[i-1] > 0):
            eq[i] = equity; continue
        tgt = pos[i-1] * lev * min(1.0, vt / rv[i-1])
        if equity < peak*0.70: tgt *= 0.5
        e = tgt; ret = close[i]/close[i-1]-1
        equity *= (1+e*ret); equity -= equity*abs(e-held)*(0.0005+slip)
        held = e; eq[i]=max(equity,1e-6); peak=max(peak,equity)
    s = pd.Series(eq[i0:], index=dates.iloc[i0:].values); s = s[s.index >= dates.iloc[idxs[0]]]
    r = s.pct_change().dropna(); yrs=len(s)/ANN
    cagr=(s.iloc[-1]/s.iloc[0])**(1/yrs)-1 if s.iloc[-1]>0 else -1
    sh=r.mean()*ANN/(r.std(ddof=1)*np.sqrt(ANN)) if r.std()>0 else float('nan')
    dd=(s/s.cummax()-1).min()
    return s.iloc[-1]/s.iloc[0], sh, (cagr/abs(dd) if dd<0 else float('nan')), dd
print("\nBACKTEST (over Actuary period, @50bp):")
print(f"{'model':22s} {'x':>9s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s}")
for nm, lev in [("Actuary 1x", 1), ("Actuary 2x", 2)]:
    x, sh, cal, dd = bt(preds, lev, 0.005); print(f"{nm:22s} {x:>8,.0f}x {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}%")
for nm, lev in [("Ensemble(B) 1x", 1), ("Ensemble(B) 2x", 2)]:
    x, sh, cal, dd = bt(expf, lev, 0.005); print(f"{nm:22s} {x:>8,.0f}x {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}%")

# ---- standalone predictive IC of each feature vs fwd5 (does order-flow/depth/exotics help?) ----
print("\nSTANDALONE feature IC vs forward-5d return (|IC|>0.05 = some signal):")
fwd = TARGET
rows = []
for j, name in enumerate(feat_cols):
    a = Xf[:, j]; mok = valid & np.isfinite(a) & np.isfinite(fwd)
    if mok.sum() > 200:
        rows.append((name, np.corrcoef(a[mok], fwd[mok])[0, 1]))
for name, v in sorted(rows, key=lambda x: -abs(x[1])):
    flag = " <-- new/exotic" if name in ("oflow","oflow_z","oflow_mom","mvrv","mvrv_z","fng","fund_z") else ""
    print(f"  {name:10s} IC {v:+.3f}{flag}")
