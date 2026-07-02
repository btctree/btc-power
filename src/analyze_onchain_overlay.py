"""Decisive MVRV test: (1) AUC at cycle horizons (30/60d), (2) apply an MVRV cycle-top long-cut
overlay to B 2x + 8B(5x) (on top of VOL+FUND) and see if it cuts the big drawdowns. Train/test.
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
n = len(df); i0 = 260; dstr = df["Date"].tolist(); dates = pd.to_datetime(df["Date"])
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
HERE = os.path.dirname(os.path.abspath(__file__))

o = pd.read_csv(os.path.join(HERE, "..", "data", "onchain.csv"))
mvmap = dict(zip(o["date"].astype(str), pd.to_numeric(o["mvrv"], errors="coerce")))
mvrv = pd.Series([mvmap.get(d, np.nan) for d in dstr])
mvrv_pct_exp = mvrv.expanding(min_periods=200).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
mvrv_pct_730 = mvrv.rolling(730, min_periods=200).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()

# ---- AUC at longer horizons ----
def auc_h(hd):
    fwd = (c.shift(-hd) / c - 1).to_numpy()
    m = np.zeros(n, bool); m[i0:] = True
    ld = m & (expf > 0) & np.isfinite(fwd)
    fl = fwd[ld]; GOOD = fl > 0.10; BAD = fl < -0.10
    out = {}
    for nm, arr in [("mvrv", mvrv.to_numpy()), ("mvrv_pct730", mvrv_pct_730), ("mvrv_pctexp", mvrv_pct_exp)]:
        a = arr[ld][BAD]; b = arr[ld][GOOD]; a = a[np.isfinite(a)]; b = b[np.isfinite(b)]
        allv = np.concatenate([a, b]); r = pd.Series(allv).rank().values
        u = r[:len(a)].sum() - len(a) * (len(a) + 1) / 2; out[nm] = u / (len(a) * len(b))
    return ld.sum(), int(GOOD.sum()), int(BAD.sum()), out
print("AUC of MVRV by forward horizon (long days; GOOD>+10% / BAD<-10%):")
for hd in (10, 30, 60, 90):
    nd, g, bd, out = auc_h(hd)
    print(f"  fwd {hd:>2d}d (cont {g}/rev {bd}): " + " ".join(f"{k} {v:.3f}" for k, v in out.items()))

# ---- VOL+FUND gates ----
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

def sim(lev, slip, smooth, band, mvrv_cut=0.0, mvrv_thr=0.90, src=mvrv_pct_730, i_from=i0, i_to=n):
    e_in = pd.Series(expf).ewm(span=smooth, adjust=False).mean().to_numpy() if smooth and smooth > 1 else expf.copy()
    equity = peak = 500.0; held = 0.0; eq = np.full(n, 500.0)
    for i in range(i_from, i_to):
        sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if mvrv_cut and sig > 0 and src[i - 1] == src[i - 1] and src[i - 1] > mvrv_thr:
            g *= mvrv_cut
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

for label, lev, sm, bd in [("B 2x +VOL+FUND", 2, 5, 0.15), ("8B 5x +VOL+FUND", 5, 0, 0.0)]:
    print(f"\n================ {label} + MVRV cycle-top long-cut ================")
    print(f"{'variant':22s} {'@0bp x':>11s} {'@50bp x':>9s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s} | {'W1':>4s} {'W2':>4s} {'W3':>4s}")
    for nm, cut, thr, src in [("base", 0.0, 0, mvrv_pct_730),
                              ("MVRV730>0.9 x0.3", 0.3, 0.90, mvrv_pct_730),
                              ("MVRV730>0.9 x0.0", 0.0001, 0.90, mvrv_pct_730),
                              ("MVRVexp>0.85 x0.3", 0.3, 0.85, mvrv_pct_exp)]:
        e0 = sim(lev, 0.0, sm, bd, cut, thr, src); e5 = sim(lev, 0.005, sm, bd, cut, thr, src)
        x0, _, _, _ = M(e0); x5, sh, cal, dd = M(e5)
        ww = [(e5.loc[a:b] / e5.loc[a:b].cummax() - 1).min() * 100 for _, a, b in W]
        print(f"{nm:22s} {x0:>10,.0f}x {x5:>8,.0f}x {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}% | {ww[0]:>3.0f}% {ww[1]:>3.0f}% {ww[2]:>3.0f}%")
    mid = (i0 + n) // 2
    for half, a_, b_ in [("train", i0, mid), ("test", mid, n)]:
        eb = sim(lev, 0.005, sm, bd, 0.0, 0, mvrv_pct_730, a_, b_)
        ec = sim(lev, 0.005, sm, bd, 0.3, 0.90, mvrv_pct_730, a_, b_)
        _, shb, _, ddb = M(eb); _, shc, _, ddc = M(ec)
        print(f"   {half:5s}: base Sh {shb:.2f}/DD {ddb*100:.0f}%  ->  MVRV-cut Sh {shc:.2f}/DD {ddc*100:.0f}%")
