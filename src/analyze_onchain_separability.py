"""Does ON-CHAIN MVRV separate reversal-longs from continuation-longs where price failed (AUC 0.609)?
Same labeling: LONG days, forward-10d return, GOOD>+10% / BAD<-10%. Causal features (no look-ahead).
"""
import os
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le

df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
c = df["close"]; n = len(df); i0 = 260
dstr = df["Date"].tolist()
HERE = os.path.dirname(os.path.abspath(__file__))

# ---- align MVRV ----
o = pd.read_csv(os.path.join(HERE, "..", "data", "onchain.csv"))
mv = dict(zip(o["date"].astype(str), pd.to_numeric(o["mvrv"], errors="coerce")))
mvrv = pd.Series([mv.get(d, np.nan) for d in dstr])
print(f"MVRV aligned: {mvrv.notna().sum()}/{n} days non-NaN")

# ---- on-chain features (causal) ----
mvrv_z = (mvrv - mvrv.rolling(365).mean()) / mvrv.rolling(365).std()
mvrv_pct_exp = mvrv.expanding(min_periods=200).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False)   # causal cycle percentile
mvrv_pct_730 = mvrv.rolling(730, min_periods=200).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False)
mvrv_chg30 = mvrv / mvrv.shift(30) - 1
FEAT = {"mvrv_level": mvrv, "mvrv_z365": mvrv_z, "mvrv_pct_expanding": mvrv_pct_exp,
        "mvrv_pct_730d": mvrv_pct_730, "mvrv_chg30": mvrv_chg30}

# ---- labels: LONG days, forward 10d ----
fwd10 = (c.shift(-10) / c - 1).to_numpy()
m = np.zeros(n, bool); m[i0:] = True
ld = m & (expf > 0) & np.isfinite(fwd10)
fl = fwd10[ld]; GOOD = fl > 0.10; BAD = fl < -0.10
print(f"LONG days {ld.sum()} | continuation {GOOD.sum()} | reversal {BAD.sum()}\n")

def auc(arr):
    a = arr[ld][BAD]; b = arr[ld][GOOD]
    a = a[np.isfinite(a)]; b = b[np.isfinite(b)]
    if len(a) < 20 or len(b) < 20: return np.nan, np.nan, np.nan, (len(a), len(b))
    allv = np.concatenate([a, b]); ranks = pd.Series(allv).rank().values
    u = ranks[:len(a)].sum() - len(a) * (len(a) + 1) / 2
    return np.nanmean(a), np.nanmean(b), u / (len(a) * len(b)), (len(a), len(b))

print(f"{'feature':20s} {'BAD(rev)':>10s} {'GOOD(cont)':>11s} {'AUC':>6s}  (vs price composite 0.609)")
aucs = {}
for name, s in FEAT.items():
    arr = s.to_numpy(); am, bm, av, nn = auc(arr); aucs[name] = av
    tag = "<== CLEARS BAR" if av == av and abs(av - 0.5) > abs(0.609 - 0.5) else ("<- beats coinflip" if av == av and abs(av - 0.5) > 0.07 else "")
    print(f"{name:20s} {am:>10.3f} {bm:>11.3f} {av:>6.3f}  {tag}")

# combined price-exhaustion + mvrv composite (quick): standardize mvrv_z + reuse simple price tells
rsi = df["RSI"]; h = df["high"]; l = df["low"]; vol = df["volume"]
ATRpct = (pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1).rolling(14).mean() / c)
obv = (np.sign(c.diff()).fillna(0) * vol).cumsum()
def zt(s, w=365): return (s - s.rolling(w).mean()) / s.rolling(w).std()
rsi_div = (c / c.rolling(20).max()) - (rsi / rsi.rolling(20).max())
obv_div = (c / c.rolling(20).max()) - obv.rolling(20).rank(pct=True)
price_exh = (zt(rsi_div) + zt(obv_div) + zt(ATRpct / ATRpct.shift(20)) - zt((obv - obv.shift(10)) / vol.rolling(20).mean()))
combo = (zt(mvrv) + price_exh).to_numpy()
am, bm, av, nn = auc(combo)
print(f"\n{'price_exh + mvrv_z':20s} {am:>10.3f} {bm:>11.3f} {av:>6.3f}  (combined)")
am, bm, av, nn = auc(price_exh.to_numpy())
print(f"{'price_exh alone':20s} {am:>10.3f} {bm:>11.3f} {av:>6.3f}  (recompute; was 0.609)")
