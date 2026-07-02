"""8B +VOL+FUND loss-period autopsy: find the big-loss periods, characterize their market type
in detail, and test whether loss days are SEPARABLE from normal/profit days.
Model = 5x, no turnover control, VOL+FUND overlays, 0bp (isolates directional losses from slippage).
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
c = df["close"]; close = c.to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
h, l = df["high"], df["low"]
ATRpct = (pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1).rolling(14).mean() / c).to_numpy()
ADX, PDI, MDI = (x.to_numpy() for x in r2.wilder_adx(h, l, c, 14))
sma50 = df["SMA50"].to_numpy(); sma200 = df["SMA200"].to_numpy()
dates = pd.to_datetime(df["Date"]); dstr = df["Date"].tolist()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
n = len(df); i0 = 260
HERE = os.path.dirname(os.path.abspath(__file__))

def lmap(p, col):
    if not os.path.exists(p): return {}
    f = pd.read_csv(p); return dict(zip(f.iloc[:, 0].astype(str), f[col]))
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
fng = np.array([lmap(os.path.join(HERE, "..", "data", "fng.csv"), "fng").get(d, np.nan) for d in dstr])

def trail_rank(a, win=365):
    return pd.Series(a).rolling(win, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vol_rank = trail_rank(rv); fund_rank = trail_rank(funding)

# VOL+FUND gates
gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vol_rank[i] == vol_rank[i] and vol_rank[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fund_rank[i] == fund_rank[i]:
        if fund_rank[i] > 0.90: gl[i] *= 0.5
        if fund_rank[i] < 0.10: gs[i] *= 0.5

# 8B sim (5x, no turn-ctrl), 0bp, record daily
equity = peak = 500.0; held = 0.0
E = np.zeros(n); PNL = np.zeros(n); EQ = np.full(n, 500.0)
for i in range(i0, n):
    sig = expf[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
    tgt = sig * g * 5.0; base = abs(sig * g) * 5.0
    if rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
        tgt = np.clip(tgt, -base, base); tgt *= min(1.0, 0.60 / rv[i - 1])
    if equity < peak * 0.70: tgt *= 0.5
    e = tgt
    ret = close[i] / close[i - 1] - 1
    equity *= (1 + e * ret); equity -= equity * abs(e - held) * 0.0005
    held = e; E[i] = e; PNL[i] = e * ret; EQ[i] = equity; peak = max(peak, equity)

# ---- slice to active range ----
s = slice(i0, n)
D = pd.DataFrame(dict(date=dates.iloc[s].values, equity=EQ[s], pos=E[s], pnl=PNL[s], ret=(close[s] / np.roll(close, 1)[s] - 1),
                      reg=np.array(reg)[s], ADX=ADX[s], ATRpct=ATRpct[s], PDI=PDI[s], MDI=MDI[s],
                      price=close[s], sma50=sma50[s], sma200=sma200[s], vol_rank=vol_rank[s],
                      funding=funding[s], fng=fng[s])).reset_index(drop=True)
D["uw"] = D["equity"] / D["equity"].cummax() - 1
D["below200"] = D.price < D.sma200
D["dir"] = np.sign(D.pos)

# ---- worst drawdown episodes ----
print("=== worst drawdown episodes (8B+VOL+FUND, 0bp) ===")
eq = D.equity.values; idx = D.date.values
cp = eq[0]; cpi = 0; tr = eq[0]; tri = 0; eps = []
for k in range(1, len(eq)):
    if eq[k] > cp:
        if (tr / cp - 1) < -0.25: eps.append((cpi, tri, cp, tr, tr / cp - 1))
        cp = eq[k]; cpi = k; tr = eq[k]; tri = k
    elif eq[k] < tr:
        tr = eq[k]; tri = k
if (tr / cp - 1) < -0.25: eps.append((cpi, tri, cp, tr, tr / cp - 1))
eps.sort(key=lambda x: x[4])
loss_mask = np.zeros(len(D), bool)
for cpi, tri, cpv, trv, d in eps[:6]:
    loss_mask[cpi:tri + 1] = True
    print(f"  {str(idx[cpi])[:10]} -> {str(idx[tri])[:10]}  {d*100:+.0f}%   (regime at peak: {D.reg[cpi]})")

# ---- groups: LOSS-period days vs PROFIT days vs NORMAL ----
D["grp"] = np.where(loss_mask, "LOSS", np.where(D.pnl > 0, "PROFIT", "FLAT/NEU"))
print("\n=== day counts ===")
print(D.grp.value_counts().to_string())

def summ(g):
    x = D[D.grp == g]
    return dict(days=len(x), pnl_sum=x.pnl.sum()*100,
                pct_long=(x.pos > 0).mean()*100, pct_short=(x.pos < 0).mean()*100, pct_flat=(x.pos == 0).mean()*100,
                long_in_dn=((x.pos > 0) & x.below200).mean()*100, short_in_up=((x.pos < 0) & ~x.below200).mean()*100,
                ADX=x.ADX.mean(), ATRpct=x.ATRpct.mean()*100, vol_rank=x.vol_rank.mean(),
                fng=x.fng.mean(), funding=x.funding.mean())
print("\n=== feature comparison (LOSS vs PROFIT vs FLAT) ===")
rows = {g: summ(g) for g in ["LOSS", "PROFIT", "FLAT/NEU"]}
keys = ["days", "pnl_sum", "pct_long", "pct_short", "pct_flat", "long_in_dn", "short_in_up", "ADX", "ATRpct", "vol_rank", "fng", "funding"]
print(f"{'feature':12s} {'LOSS':>10s} {'PROFIT':>10s} {'FLAT':>10s}")
for k in keys:
    print(f"{k:12s} {rows['LOSS'][k]:>10.2f} {rows['PROFIT'][k]:>10.2f} {rows['FLAT/NEU'][k]:>10.2f}")

# ---- regime mix in loss periods ----
print("\n=== regime mix: LOSS-period days vs all-other days (% of group) ===")
lr = D[loss_mask].reg.value_counts(normalize=True) * 100
orr = D[~loss_mask].reg.value_counts(normalize=True) * 100
allreg = sorted(set(lr.index) | set(orr.index))
print(f"{'regime':12s} {'LOSS%':>7s} {'OTHER%':>7s}")
for rg in allreg:
    print(f"{rg:12s} {lr.get(rg,0):>7.1f} {orr.get(rg,0):>7.1f}")

# ---- P&L attribution within loss periods by positioning ----
print("\n=== loss-period P&L attribution by positioning ===")
L = D[loss_mask]
for label, m in [("LONG in downtrend (price<SMA200)", (L.pos > 0) & L.below200),
                 ("LONG in uptrend", (L.pos > 0) & ~L.below200),
                 ("SHORT in downtrend", (L.pos < 0) & L.below200),
                 ("SHORT in uptrend (squeeze)", (L.pos < 0) & ~L.below200)]:
    print(f"  {label:34s}: pnl {L[m].pnl.sum()*100:+7.1f}%   days {int(m.sum())}")

# ---- separability: simple rule flag ----
print("\n=== separability: candidate flags (share of days flagged) ===")
for label, cond in [("price<SMA200 & pos>0 (knife)", (D.pos > 0) & D.below200),
                     ("vol_rank>0.85 (high vol)", D.vol_rank > 0.85),
                     ("ADX>30 & MDI>PDI & pos>0 (long vs strong downtrend)", (D.ADX > 30) & (D.MDI > D.PDI) & (D.pos > 0)),
                     ("price<SMA50<SMA200 & pos>0 (long vs full downtrend)", (D.pos > 0) & (D.price < D.sma50) & (D.sma50 < D.sma200))]:
    inl = cond[loss_mask].mean()*100; ino = cond[~loss_mask].mean()*100
    pnl_flag = D[cond].pnl.sum()*100
    print(f"  {label:52s} LOSS {inl:5.1f}%  OTHER {ino:5.1f}%  | total pnl on flagged days {pnl_flag:+.1f}%")

# ================= TEST a targeted fix: block LONG in strong established downtrend =================
def run(block_dn_long=False, slip=0.0):
    equity = peak = 500.0; held = 0.0; eqA = np.full(n, 500.0); turn = 0.0
    for i in range(i0, n):
        sig = expf[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if block_dn_long and sig > 0 and ADX[i - 1] > 30 and MDI[i - 1] > PDI[i - 1]:
            g = 0.0                                   # no long into a strong established downtrend
        tgt = sig * g * 5.0; base = abs(sig * g) * 5.0
        if rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt = np.clip(tgt, -base, base); tgt *= min(1.0, 0.60 / rv[i - 1])
        if equity < peak * 0.70: tgt *= 0.5
        e = tgt; ret = close[i] / close[i - 1] - 1
        equity *= (1 + e * ret); equity -= equity * abs(e - held) * (0.0005 + slip)
        held = e; eqA[i] = equity; peak = max(peak, equity)
    return pd.Series(eqA[i0:], index=dates.iloc[i0:].values)

def m2(eq):
    r = eq.pct_change().dropna(); yrs = len(eq) / ANN
    cagr = (eq.iloc[-1] / 500) ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dd = (eq / eq.cummax() - 1).min()
    return eq.iloc[-1], sh, (cagr / abs(dd) if dd < 0 else float("nan")), dd

print("\n=== TEST: block LONG in strong downtrend (ADX>30 & -DI>+DI) on 8B+VOL+FUND ===")
print(f"{'variant':22s} {'@0bp':>15s} {'@50bp':>13s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s}")
for nm, bl in [("8B+VOL+FUND", False), ("+ block dn-long", True)]:
    e0 = run(bl, 0.0); e5 = run(bl, 0.005)
    f0, _, _, _ = m2(e0); f5, sh, cal, dd = m2(e5)
    print(f"{nm:22s} ${f0:>14,.0f} ${f5:>12,.0f} {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}%")

# overextension proxy for cycle tops: trailing percentile of price/SMA200
ext = pd.Series(close / sma200)
ext_rank = ext.rolling(365, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
def run2(mode=None, slip=0.0):
    equity = peak = 500.0; held = 0.0; eqA = np.full(n, 500.0)
    for i in range(i0, n):
        sig = expf[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if mode == "overext" and sig > 0 and ext_rank[i - 1] == ext_rank[i - 1] and ext_rank[i - 1] > 0.90:
            g *= 0.3                                  # cut long when price is overextended vs SMA200 (top proxy)
        tgt = sig * g * 5.0; base = abs(sig * g) * 5.0
        if rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt = np.clip(tgt, -base, base); tgt *= min(1.0, 0.60 / rv[i - 1])
        if equity < peak * 0.70: tgt *= 0.5
        e = tgt; ret = close[i] / close[i - 1] - 1
        equity *= (1 + e * ret); equity -= equity * abs(e - held) * (0.0005 + slip)
        held = e; eqA[i] = equity; peak = max(peak, equity)
    return pd.Series(eqA[i0:], index=dates.iloc[i0:].values)
print("\n=== TEST: cut LONG when overextended vs SMA200 (price-only top proxy) ===")
print(f"{'variant':22s} {'@0bp':>15s} {'@50bp':>13s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s} | {'W1':>5s} {'W2':>5s} {'W3':>5s}")
W = [("W1","2017-12-16","2018-11-18"),("W2","2021-10-20","2022-03-09"),("W3","2025-05-22","2025-12-01")]
for nm, md in [("8B+VOL+FUND", None), ("+cut overext-long", "overext")]:
    e0 = run2(md, 0.0); e5 = run2(md, 0.005)
    f0, _, _, _ = m2(e0); f5, sh, cal, dd = m2(e5)
    ww = [(e5.loc[a:b]/e5.loc[a:b].cummax()-1).min()*100 for _,a,b in W]
    print(f"{nm:22s} ${f0:>14,.0f} ${f5:>12,.0f} {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}% | {ww[0]:>4.0f}% {ww[1]:>4.0f}% {ww[2]:>4.0f}%")
