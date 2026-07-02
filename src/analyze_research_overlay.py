"""Apply the research overlays to the B model and measure if they help the 3 drops.
Overlays (all no-look-ahead: prior-day values, trailing percentiles):
  VOL gate  : cut size 50% when 20d realised-vol is in its trailing-365d top 15% (HMM-spirit
              'high-volatility regime -> don't trade' — full history).
  F&G gate  : cut LONGs 60% when Fear&Greed >=80 (greed); cut SHORTs 60% when <=20 (fear). 2018+.
  FUND gate : cut LONGs 50% when funding in trailing top decile (hot); cut SHORTs 50% when in
              bottom decile (negative). 2020+.
Each tested alone and combined, at 1x and 2x, vs baseline B. Honest: 2014+, fees, slippage, liq.
"""
import os
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le

ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
dates = pd.to_datetime(df["Date"]); dstr = df["Date"].tolist()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
n = len(df); i0 = 260

# ---- align external series ----
def load_map(path, col):
    if not os.path.exists(path):
        return {}
    f = pd.read_csv(path)
    return dict(zip(f.iloc[:, 0].astype(str), f[col]))
HERE = os.path.dirname(os.path.abspath(__file__))
fundm = load_map(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate")
fngm = load_map(os.path.join(HERE, "..", "data", "fng.csv"), "fng")
funding = np.array([fundm.get(d, np.nan) for d in dstr])
fng = np.array([fngm.get(d, np.nan) for d in dstr])

# ---- trailing percentile ranks (no look-ahead) ----
def trail_rank(arr, win=365):
    s = pd.Series(arr)
    return s.rolling(win, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vol_rank = trail_rank(rv)
fund_rank = trail_rank(pd.Series(funding).to_numpy())

# ---- gate arrays (long-gate gl, short-gate gs), decided from prior-day data ----
def build_gates(vol=True, fg=True, fund=True):
    gl = np.ones(n); gs = np.ones(n)
    for i in range(n):
        if vol and vol_rank[i] == vol_rank[i] and vol_rank[i] > 0.85:
            gl[i] *= 0.5; gs[i] *= 0.5
        if fg and fng[i] == fng[i]:
            if fng[i] >= 80: gl[i] *= 0.4
            if fng[i] <= 20: gs[i] *= 0.4
        if fund and fund_rank[i] == fund_rank[i]:
            if fund_rank[i] > 0.90: gl[i] *= 0.5
            if fund_rank[i] < 0.10: gs[i] *= 0.5
    return gl, gs

def sim(lev, slip, gl=None, gs=None, smooth=5, band=0.15, vol_target=0.60, dd_kill=0.30, fee=0.0005, maint=0.01):
    e_sm = pd.Series(expf).ewm(span=smooth, adjust=False).mean().to_numpy() if smooth and smooth > 1 else expf.copy()
    equity = peak = 500.0; held = 0.0; liq = 0; turn = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        sig = e_sm[i - 1]
        g = 1.0
        if gl is not None and sig > 0: g = gl[i - 1]
        elif gs is not None and sig < 0: g = gs[i - 1]
        tgt = sig * g * lev
        base = abs(sig * g) * lev
        if vol_target > 0 and rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt = np.clip(tgt, -base, base); tgt *= min(1.0, vol_target / rv[i - 1])
        if dd_kill > 0 and equity < peak * (1 - dd_kill):
            tgt *= 0.5
        e = tgt
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0):
            e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= 1 - maint:
            equity *= 0.01; liq += 1; held = 0.0; eq[i] = equity; peak = max(peak, equity); continue
        t = abs(e - held); turn += t
        equity *= (1 + e * (close[i] / close[i - 1] - 1)); equity -= equity * t * (fee + slip)
        held = e; eq[i] = equity; peak = max(peak, equity)
    return pd.Series(eq[i0:], index=dates.iloc[i0:]), liq, turn / ((n - i0) / ANN)

def met(eq):
    r = eq.pct_change().dropna(); yrs = len(eq) / ANN
    cagr = (eq.iloc[-1] / 500) ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dd = (eq / eq.cummax() - 1).min()
    return eq.iloc[-1], cagr, sh, (cagr / abs(dd) if dd < 0 else float("nan")), dd

WIN = [("W1", "2017-12-16", "2018-11-18"), ("W2", "2021-10-20", "2022-03-09"), ("W3", "2025-05-22", "2025-12-01")]
def wdd(eq):
    return [ (eq.loc[a:b] / eq.loc[a:b].cummax() - 1).min()*100 if len(eq.loc[a:b]) else float('nan') for _,a,b in WIN ]

glv, gsv = build_gates(True, False, False)
glf, gsf = build_gates(False, True, False)
gld, gsd = build_gates(False, False, True)
gla, gsa = build_gates(True, True, True)
print("gate fire counts (entries <1.0):")
print("  VOL  long", int(np.sum(glv < 1)), "short", int(np.sum(gsv < 1)))
print("  F&G  long", int(np.sum(glf < 1)), "short", int(np.sum(gsf < 1)))
print("  FUND long", int(np.sum(gld < 1)), "short", int(np.sum(gsd < 1)))
glvf, gsvf = build_gates(True, False, True)   # VOL+FUND (no F&G) = the best combo
VARIANTS = [
    ("baseline", None, None),
    ("+VOL", glv, gsv),
    ("+FUND", gld, gsd),
    ("+F&G", glf, gsf),
    ("+VOL+FUND", glvf, gsvf),
]
# (name, leverage, smooth, band) — B = turnover-controlled; 8B = deployed 5x, no turnover control
MODELS = [
    ("B 1x", 1, 5, 0.15),
    ("B 2x", 2, 5, 0.15),
    ("B 3x", 3, 5, 0.15),
    ("8B 5x (no turn-ctrl)", 5, 0, 0.0),
]
print("\n(all overlays no-look-ahead; sims exclude funding cost, so 8B 0bp is higher than the")
print(" funding-inclusive dashboard ~$899M; relative overlay comparison is what matters)\n")
for mname, lev, sm, bd in MODELS:
    print(f"================  {mname}  ================")
    print(f"{'variant':12s} {'@0bp':>16s} {'@50bp':>14s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s} {'turn':>5s} {'liq':>4s} | {'W1':>5s} {'W2':>5s} {'W3':>5s}")
    for nm, gl, gs in VARIANTS:
        eq0, _, _ = sim(lev, 0.0, gl, gs, smooth=sm, band=bd)
        eq5, liq, turn = sim(lev, 0.005, gl, gs, smooth=sm, band=bd)
        f0 = eq0.iloc[-1]; fin, cagr, sh, cal, dd = met(eq5); w = wdd(eq5)
        print(f"{nm:12s} ${f0:>15,.0f} ${fin:>13,.0f} {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}% {turn:>4.0f}x {liq:>4d} | {w[0]:>4.0f}% {w[1]:>4.0f}% {w[2]:>4.0f}%")
    print()
