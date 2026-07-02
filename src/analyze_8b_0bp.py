"""8B (5x, no turnover control) at 0bp slippage — with VOL and FUND overlays. Full metrics.
0bp is the unrealistic 'perfect fill' fantasy; shown because that's where the billions live.
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
HERE = os.path.dirname(os.path.abspath(__file__))

def load_map(path, col):
    if not os.path.exists(path): return {}
    f = pd.read_csv(path); return dict(zip(f.iloc[:, 0].astype(str), f[col]))
funding = np.array([load_map(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])

def trail_rank(arr, win=365):
    return pd.Series(arr).rolling(win, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vol_rank = trail_rank(rv); fund_rank = trail_rank(funding)

def gates(vol, fund):
    gl = np.ones(n); gs = np.ones(n)
    for i in range(n):
        if vol and vol_rank[i] == vol_rank[i] and vol_rank[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
        if fund and fund_rank[i] == fund_rank[i]:
            if fund_rank[i] > 0.90: gl[i] *= 0.5
            if fund_rank[i] < 0.10: gs[i] *= 0.5
    return gl, gs

def sim(lev, slip, gl=None, gs=None, smooth=0, band=0.0, vol_target=0.60, dd_kill=0.30, fee=0.0005, maint=0.01):
    e_sm = pd.Series(expf).ewm(span=smooth, adjust=False).mean().to_numpy() if smooth and smooth > 1 else expf.copy()
    equity = peak = 500.0; held = 0.0; liq = 0; turn = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        sig = e_sm[i - 1]; g = 1.0
        if gl is not None and sig > 0: g = gl[i - 1]
        elif gs is not None and sig < 0: g = gs[i - 1]
        tgt = sig * g * lev; base = abs(sig * g) * lev
        if vol_target > 0 and rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt = np.clip(tgt, -base, base); tgt *= min(1.0, vol_target / rv[i - 1])
        if dd_kill > 0 and equity < peak * (1 - dd_kill): tgt *= 0.5
        e = tgt
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
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
    dn = r[r < 0].std(ddof=1) * np.sqrt(ANN) if (r < 0).sum() > 1 else float("nan")
    so = r.mean() * ANN / dn if dn and dn > 0 else float("nan")
    dd = (eq / eq.cummax() - 1).min()
    return cagr, sh, so, (cagr / abs(dd) if dd < 0 else float("nan")), dd

WIN = [("W1", "2017-12-16", "2018-11-18"), ("W2", "2021-10-20", "2022-03-09"), ("W3", "2025-05-22", "2025-12-01")]
def wdd(eq):
    return [(eq.loc[a:b] / eq.loc[a:b].cummax() - 1).min() * 100 if len(eq.loc[a:b]) else float("nan") for _, a, b in WIN]

glv, gsv = gates(True, False); gld, gsd = gates(False, True); glvf, gsvf = gates(True, True)
VAR = [("8B baseline", None, None), ("8B +VOL", glv, gsv), ("8B +FUND", gld, gsd), ("8B +VOL+FUND", glvf, gsvf)]
print("8B = 5x leverage, NO turnover control, at 0bp slippage (perfect-fill fantasy). Excludes funding cost.\n")
print(f"{'variant':14s} {'final $':>18s} {'CAGR':>5s} {'Shrp':>5s} {'Sort':>5s} {'Calm':>5s} {'maxDD':>6s} {'turn':>5s} {'liq':>4s} | {'W1':>5s} {'W2':>5s} {'W3':>5s}")
for nm, gl, gs in VAR:
    eq, liq, turn = sim(5, 0.0, gl, gs)
    cagr, sh, so, cal, dd = met(eq); w = wdd(eq)
    print(f"{nm:14s} ${eq.iloc[-1]:>17,.0f} {cagr*100:>4.0f}% {sh:>5.2f} {so:>5.2f} {cal:>5.2f} {dd*100:>5.0f}% {turn:>4.0f}x {liq:>4d} | {w[0]:>4.0f}% {w[1]:>4.0f}% {w[2]:>4.0f}%")
print("\n(reminder: 0bp is unreachable in real trading; the same 8B at 50bp = ~$3k-$19k. See realistic columns.)")
