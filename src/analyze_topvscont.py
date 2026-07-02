"""Feature discovery: among the model's LONG days, what distinguishes the ones that became a
REVERSAL (loss) from the ones that CONTINUED (profit)? Label by forward 10d return (analysis only),
compare contemporaneous features, rank by separating power (AUC). This is the search for the 'tell'.
"""
import os
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le
import regime_v2 as r2

ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
print("df columns:", [x for x in df.columns])
c = df["close"]; h = df["high"]; l = df["low"]
vol = df["volume"] if "volume" in df.columns else pd.Series(np.ones(len(df)), index=df.index)
close = c.to_numpy(); n = len(df); i0 = 260
rsi = df["RSI"]
sma20 = df["SMA20"]; sma50 = df["SMA50"]; sma200 = df["SMA200"]
ATRpct = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1).rolling(14).mean() / c
obv = (np.sign(c.diff()).fillna(0) * vol).cumsum()

# ---- contemporaneous features (no look-ahead) ----
F = pd.DataFrame(index=df.index)
F["rsi"] = rsi
F["mom10"] = c / c.shift(10) - 1
F["mom20"] = c / c.shift(20) - 1
F["accel"] = (c / c.shift(10) - 1) - (c.shift(10) / c.shift(20) - 1)          # momentum acceleration
F["ext20"] = c / sma20 - 1
F["ext50"] = c / sma50 - 1
F["ext200"] = c / sma200 - 1                                                   # overextension vs cycle MA
F["atr"] = ATRpct
F["atr_exp"] = ATRpct / ATRpct.shift(20)                                       # volatility expansion
F["rsi_div"] = (c / c.rolling(20).max()) - (rsi / rsi.rolling(20).max())       # bearish RSI divergence (price hi, rsi not)
F["obv_div"] = (c / c.rolling(20).max()) - (obv.rolling(20).rank(pct=True))    # price at high but OBV rank not
F["obv_slope"] = (obv - obv.shift(10)) / vol.rolling(20).mean()                # OBV momentum (vol-normalised)
F["vol_z"] = vol / vol.rolling(20).mean() - 1                                  # volume vs 20d avg
F["dist_hi"] = c / c.rolling(90).max() - 1                                     # distance below 90d high (~0 at highs)
up = (c.diff() > 0).astype(int)
F["up_streak"] = up.groupby((up != up.shift()).cumsum()).cumcount() + 1
F["up_streak"] = F["up_streak"] * up                                           # consecutive up days (0 if down day)

pos = expf                                                                     # sign of intended position
fwd10 = (c.shift(-10) / c - 1).to_numpy()                                      # forward 10d return (LABEL ONLY)

# ---- restrict to LONG days, label by forward outcome ----
mask = np.zeros(n, bool); mask[i0:] = True
longday = mask & (pos > 0) & np.isfinite(fwd10)
sub = F[longday].copy(); fl = fwd10[longday]
GOOD = fl > 0.10      # continuation (next 10d +10%+)
BAD = fl < -0.10      # reversal (next 10d -10%+)
print(f"\nLONG days: {longday.sum()} | continuation(+10%): {GOOD.sum()} | reversal(-10%): {BAD.sum()} | meh: {(~GOOD&~BAD).sum()}")

def auc(feat):
    a = sub[feat][BAD].dropna(); b = sub[feat][GOOD].dropna()
    if len(a) < 10 or len(b) < 10: return np.nan, np.nan, np.nan
    # AUC = P(feat(BAD) > feat(GOOD)) via rank
    allv = np.concatenate([a.values, b.values]); ranks = pd.Series(allv).rank().values
    ra = ranks[:len(a)].sum(); u = ra - len(a) * (len(a) + 1) / 2; aucv = u / (len(a) * len(b))
    return a.mean(), b.mean(), aucv

print(f"\n{'feature':10s} {'BAD(rev)':>10s} {'GOOD(cont)':>11s} {'AUC':>6s}  (AUC>0.5 => higher before reversals)")
res = []
for f in F.columns:
    am, bm, av = auc(f)
    res.append((f, am, bm, av))
for f, am, bm, av in sorted(res, key=lambda x: -abs((x[3] or 0.5) - 0.5)):
    if av == av:
        print(f"{f:10s} {am:>10.3f} {bm:>11.3f} {av:>6.2f}  {'<-- strong' if abs(av-0.5)>0.12 else ('<- mild' if abs(av-0.5)>0.07 else '')}")
