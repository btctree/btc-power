"""Honest 'where's the Billion?' frontier. Shows that the Billion only exists at 0 slippage and/or
extreme leverage, and always with catastrophic drawdown — and evaporates under real costs.
"""
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le

ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
n = len(df); i0 = 260

def sim(exp, lev, slip, smooth, band, vol_target=0.60, dd_kill=0.30, fee=0.0005, maint=0.01):
    e_in = pd.Series(exp).ewm(span=smooth, adjust=False).mean().to_numpy() if smooth > 1 else exp.copy()
    equity = peak = 500.0; held = 0.0; liqs = 0
    eq = np.full(n, 500.0)
    for i in range(i0, n):
        tgt = e_in[i - 1] * lev
        if vol_target > 0 and rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt = np.clip(tgt, -abs(e_in[i - 1]) * lev, abs(e_in[i - 1]) * lev)
            tgt *= min(1.0, vol_target / rv[i - 1])
        if dd_kill > 0 and equity < peak * (1 - dd_kill):
            tgt *= 0.5
        e = tgt
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0):
            e = held
        adverse = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adverse, 0) >= (1 - maint):
            equity *= 0.01; liqs += 1; held = 0.0; eq[i] = equity; peak = max(peak, equity); continue
        ret = close[i] / close[i - 1] - 1
        turn = abs(e - held)
        equity *= (1 + e * ret); equity -= equity * turn * (fee + slip)
        held = e; eq[i] = equity; peak = max(peak, equity)
        if equity <= 0.05:
            eq[i:] = equity; break
    eq = eq[i0:]
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    return eq[-1], dd, liqs

CONF = [
    ("RAW ensemble 5x (high-turnover, the old '8B')", exp_raw, 5, 0, 0.0),
    ("RAW ensemble 8x", exp_raw, 8, 0, 0.0),
    ("B 5x (turnover-controlled)", expf, 5, 5, 0.15),
    ("B 8x", expf, 8, 5, 0.15),
    ("B 10x", expf, 10, 5, 0.15),
    ("B 15x", expf, 15, 5, 0.15),
]
print(f"{'config':46s} | {'@0bp final':>16s} {'DD':>5s} {'liq':>4s} | {'@50bp final':>14s} {'DD':>5s} {'liq':>4s}")
for name, exp, lev, sm, bd in CONF:
    f0, d0, l0 = sim(exp, lev, 0.0, sm, bd)
    f5, d5, l5 = sim(exp, lev, 0.005, sm, bd)
    print(f"{name:46s} | ${f0:>15,.0f} {d0*100:>4.0f}% {l0:>4d} | ${f5:>13,.0f} {d5*100:>4.0f}% {l5:>4d}")
