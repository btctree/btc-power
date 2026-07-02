"""Define a composite TREND-EXHAUSTION SCORE from the weak 'tells' (RSI div, OBV div, vol
expansion, weak OBV momentum) and test (a) its combined separating power (AUC) and (b) a tradeable
rule: cut LONG when exhaustion is extreme. Causal (trailing z-scores, no look-ahead). Train/test split.
"""
import os
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le

ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
c = df["close"]; h = df["high"]; l = df["low"]; vol = df["volume"]
close = c.to_numpy(); low = l.to_numpy(); high = h.to_numpy(); n = len(df); i0 = 260
rsi = df["RSI"]
ATRpct = (pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1).rolling(14).mean() / c)
obv = (np.sign(c.diff()).fillna(0) * vol).cumsum()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
dates = pd.to_datetime(df["Date"]); dstr = df["Date"].tolist()
HERE = os.path.dirname(os.path.abspath(__file__))

# ---- tells ----
rsi_div = (c / c.rolling(20).max()) - (rsi / rsi.rolling(20).max())
obv_div = (c / c.rolling(20).max()) - obv.rolling(20).rank(pct=True)
atr_exp = ATRpct / ATRpct.shift(20)
obv_slope = (obv - obv.shift(10)) / vol.rolling(20).mean()
def ztrail(s, w=365):
    return (s - s.rolling(w).mean()) / s.rolling(w).std()
# composite: high = exhausted/reversal-prone
EXH = (ztrail(rsi_div) + ztrail(obv_div) + ztrail(atr_exp) - ztrail(obv_slope)).to_numpy()
exh_pct = pd.Series(EXH).rolling(365, min_periods=120).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()

# ---- AUC of composite on long-day reversal/continuation labels ----
fwd10 = (c.shift(-10) / c - 1).to_numpy()
m = np.zeros(n, bool); m[i0:] = True
ld = m & (expf > 0) & np.isfinite(fwd10) & np.isfinite(EXH)
fl = fwd10[ld]; e = EXH[ld]; GOOD = fl > 0.10; BAD = fl < -0.10
a = e[BAD]; b = e[GOOD]; allv = np.concatenate([a, b]); ranks = pd.Series(allv).rank().values
u = ranks[:len(a)].sum() - len(a) * (len(a) + 1) / 2; AUC = u / (len(a) * len(b))
print(f"Composite EXHAUSTION score AUC (reversal vs continuation longs): {AUC:.3f}  (0.50=coinflip; individual tells were ~0.59)")
print(f"  reversals flagged exhausted(>0.85pct): {np.mean(exh_pct[ld][BAD] > 0.85)*100:.0f}%  vs continuations: {np.mean(exh_pct[ld][GOOD] > 0.85)*100:.0f}%")

# ---- VOL+FUND gates (the 8B+VOL+FUND base) ----
def lmap(p, col):
    if not os.path.exists(p): return {}
    f = pd.read_csv(p); return dict(zip(f.iloc[:, 0].astype(str), f[col]))
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trail_rank(a, w=365):
    return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vol_rank = trail_rank(rv); fund_rank = trail_rank(funding)
gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vol_rank[i] == vol_rank[i] and vol_rank[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fund_rank[i] == fund_rank[i]:
        if fund_rank[i] > 0.90: gl[i] *= 0.5
        if fund_rank[i] < 0.10: gs[i] *= 0.5

def sim(lev, slip, smooth, band, exh_cut=0.0, exh_thr=0.85, i_from=i0, i_to=n):
    e_in = pd.Series(expf).ewm(span=smooth, adjust=False).mean().to_numpy() if smooth and smooth > 1 else expf.copy()
    equity = peak = 500.0; held = 0.0; eq = np.full(n, 500.0)
    for i in range(i_from, i_to):
        sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if exh_cut and sig > 0 and exh_pct[i - 1] == exh_pct[i - 1] and exh_pct[i - 1] > exh_thr:
            g *= exh_cut                                # trim long when exhaustion extreme
        tgt = sig * g * lev; base = abs(sig * g) * lev
        if rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt = np.clip(tgt, -base, base); tgt *= min(1.0, 0.60 / rv[i - 1])
        if equity < peak * 0.70: tgt *= 0.5
        e = tgt; adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= 0.99:
            equity *= 0.01; held = 0.0; eq[i] = equity; peak = max(peak, equity); continue
        equity *= (1 + e * (close[i] / close[i - 1] - 1)); equity -= equity * abs(e - held) * (0.0005 + slip)
        held = e; eq[i] = equity; peak = max(peak, equity)
    return pd.Series(eq[i_from:i_to], index=dates.iloc[i_from:i_to].values)

def M(eq):
    r = eq.pct_change().dropna(); yrs = len(eq) / ANN
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dd = (eq / eq.cummax() - 1).min()
    return eq.iloc[-1] / eq.iloc[0], sh, (cagr / abs(dd) if dd < 0 else float("nan")), dd
W = [("W1", "2017-12-16", "2018-11-18"), ("W2", "2021-10-20", "2022-03-09"), ("W3", "2025-05-22", "2025-12-01")]

for label, lev, sm, bd in [("8B+VOL+FUND (5x)", 5, 0, 0.0), ("B+VOL+FUND (2x)", 2, 5, 0.15)]:
    print(f"\n================ {label} — add exhaustion-cut on longs ================")
    print(f"{'variant':20s} {'@0bp x':>12s} {'@50bp x':>10s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s} | {'W1':>4s} {'W2':>4s} {'W3':>4s}")
    for nm, cut in [("base", 0.0), ("exh-cut x0.3", 0.3), ("exh-cut x0.0", 0.0001)]:
        e0 = sim(lev, 0.0, sm, bd, exh_cut=cut); e5 = sim(lev, 0.005, sm, bd, exh_cut=cut)
        x0, _, _, _ = M(e0); x5, sh, cal, dd = M(e5)
        ww = [(e5.loc[a:b] / e5.loc[a:b].cummax() - 1).min() * 100 for _, a, b in W]
        print(f"{nm:20s} {x0:>11,.0f}x {x5:>9,.0f}x {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}% | {ww[0]:>3.0f}% {ww[1]:>3.0f}% {ww[2]:>3.0f}%")
    # train/test robustness on the x0.3 variant
    mid = (i0 + n) // 2
    for half, a_, b_ in [("train(1st half)", i0, mid), ("test(2nd half)", mid, n)]:
        eb = sim(lev, 0.005, sm, bd, exh_cut=0.0, i_from=a_, i_to=b_)
        ec = sim(lev, 0.005, sm, bd, exh_cut=0.3, i_from=a_, i_to=b_)
        _, shb, _, ddb = M(eb); _, shc, _, ddc = M(ec)
        print(f"   {half:16s} base Sharpe {shb:.2f}/DD {ddb*100:.0f}%  ->  exh-cut Sharpe {shc:.2f}/DD {ddc*100:.0f}%")
