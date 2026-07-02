"""Trade-level autopsy of the DEPLOYED 8B (conviction-filtered ensemble, 5x, vol-target 60%,
DD-kill 30%, NO turnover control) — total trades + how many slippage kills at 50bp.

A 'trade' = a spell of constant position direction (entry when direction opens/flips, exit when it
flips or goes flat). Slippage hits the daily rebalancing turnover within each spell. A trade is
'killed by 50bp' if it was a winner net of 5bp fees but a loser once 50bp slippage is charged.
Honest: real data 2014+, daily-rebalanced exposure path.
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
dates = pd.to_datetime(df["Date"])
n = len(df); i0 = 260
LEV, FEE, MAINT = 5.0, 0.0005, 0.01

def run(slip):
    """Deployed-8B sim; returns final eq + per-day position/return/turnover arrays."""
    equity = peak = 500.0; held = 0.0; liqs = 0
    E = np.zeros(n); R = np.zeros(n); T = np.zeros(n); eq = np.full(n, 500.0)
    for i in range(i0, n):
        tgt = expf[i - 1] * LEV
        if rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt = np.clip(tgt, -abs(expf[i - 1]) * LEV, abs(expf[i - 1]) * LEV)
            tgt *= min(1.0, 0.60 / rv[i - 1])
        if equity < peak * 0.70:          # dd_kill 30%
            tgt *= 0.5
        e = tgt
        adverse = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adverse, 0) >= (1 - MAINT):
            equity *= 0.01; liqs += 1; held = 0.0; eq[i] = equity; peak = max(peak, equity)
            E[i] = 0.0; continue
        ret = close[i] / close[i - 1] - 1
        turn = abs(e - held)
        equity *= (1 + e * ret); equity -= equity * turn * (FEE + slip)
        held = e; eq[i] = equity; peak = max(peak, equity)
        E[i] = e; R[i] = ret; T[i] = turn
    return eq[-1], liqs, E, R, T

f0, liq0, E, R, T = run(0.0)
f5, liq5, _, _, _ = run(0.005)
print(f"RECONCILE deployed 8B: @0bp ${f0:,.0f} (liq {liq0}) | @50bp ${f5:,.0f} (liq {liq5})")
print(f"(live_engine prints ~$899,566,610 @0bp and ~$873 @50bp)\n")

# ---- decompose into trades (direction spells) using the position path ----
Es, Rs, Ts = E[i0:], R[i0:], T[i0:]
m = len(Es); i = 0
n_trades = 0; win0 = 0; win50 = 0; killed = 0; flat_days = int(np.sum(Es == 0))
slip_cost_total = 0.0; rebal_days = int(np.sum(Ts > 1e-9))
spell_lens = []
while i < m:
    s = 1 if Es[i] > 0 else (-1 if Es[i] < 0 else 0)
    if s == 0:
        i += 1; continue
    j = i
    while j + 1 < m and (1 if Es[j + 1] > 0 else (-1 if Es[j + 1] < 0 else 0)) == s:
        j += 1
    # compound the spell two ways: net of fees only (≈0bp) vs net of fees+50bp slippage
    g0 = 1.0; g5 = 1.0; sc_cost = 0.0
    for k in range(i, j + 1):
        g0 *= (1 + Es[k] * Rs[k] - Ts[k] * FEE)
        g5 *= (1 + Es[k] * Rs[k] - Ts[k] * (FEE + 0.005))
        sc_cost += Ts[k] * 0.005
    g0 -= 1; g5 -= 1
    n_trades += 1; spell_lens.append(j - i + 1)
    if g0 > 0: win0 += 1
    if g5 > 0: win50 += 1
    if g0 > 0 and g5 <= 0:
        killed += 1
    slip_cost_total += sc_cost
    i = j + 1

print(f"TOTAL TRADES (direction spells):        {n_trades}")
print(f"  avg spell length:                     {np.mean(spell_lens):.1f} days")
print(f"  flat days (no position):              {flat_days} of {m}")
print(f"  daily rebalance events (turn>0):      {rebal_days}  -> turnover/yr {np.sum(Ts)/((m)/ANN):.0f}x")
print()
print(f"Winners net of 5bp fees only (~0bp):    {win0}/{n_trades}  ({win0/n_trades*100:.0f}%)")
print(f"Winners net of 50bp slippage:           {win50}/{n_trades}  ({win50/n_trades*100:.0f}%)")
print(f"==> TRADES KILLED BY 50bp SLIPPAGE:     {killed}  (winner@0bp -> loser@50bp)")
print(f"    i.e. {killed/n_trades*100:.0f}% of all trades flipped from profit to loss")
print(f"    total slippage drag @50bp (sum of turn*50bp): {slip_cost_total*100:.0f}% of equity-units")
