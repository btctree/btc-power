"""Does a per-trade CUT-LOSS help control slippage? Test it honestly on real data.
Adds a fixed cut-loss: when price moves -stop from the entry of a direction-spell, exit at the
stop (go flat, PAY exit slippage), stay flat until the ensemble direction flips. Compares the
8B (5x) and B (2x) with/without stops at 0bp and 50bp. Reports final, maxDD, #stops, turnover.
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

def sim(lev, slip, stop=0.0, smooth=0, band=0.0, vol_target=0.60, dd_kill=0.30, fee=0.0005, maint=0.01):
    e_in = pd.Series(expf).ewm(span=smooth, adjust=False).mean().to_numpy() if smooth > 1 else expf.copy()
    equity = peak = 500.0; held = 0.0; liqs = 0; stops = 0; turn_tot = 0.0
    entry_ref = None; stopped_dir = 0
    eq = np.full(n, 500.0)
    for i in range(i0, n):
        sig = e_in[i - 1]
        sdir = 1 if sig > 0 else (-1 if sig < 0 else 0)
        # release the stop-flat block only when signal direction flips away from stopped dir
        if stopped_dir != 0 and sdir != stopped_dir:
            stopped_dir = 0
        tgt = sig * lev
        if vol_target > 0 and rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt = np.clip(tgt, -abs(sig) * lev, abs(sig) * lev); tgt *= min(1.0, vol_target / rv[i - 1])
        if dd_kill > 0 and equity < peak * (1 - dd_kill):
            tgt *= 0.5
        if stopped_dir != 0:
            tgt = 0.0                       # forced flat after a stop until direction flips
        e = tgt
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0):
            e = held
        # set entry reference on a fresh entry
        if held == 0 and e != 0:
            entry_ref = close[i - 1]
        # ---- cut-loss check (intraday, before normal P&L) ----
        if stop > 0 and e != 0 and entry_ref:
            if e > 0 and low[i] <= entry_ref * (1 - stop):
                fill = entry_ref * (1 - stop)
                equity *= (1 + e * (fill / close[i - 1] - 1)); equity -= equity * abs(e) * (fee + slip)
                held = 0.0; stops += 1; stopped_dir = sdir; turn_tot += abs(e)
                eq[i] = equity; peak = max(peak, equity); continue
            if e < 0 and high[i] >= entry_ref * (1 + stop):
                fill = entry_ref * (1 + stop)
                equity *= (1 + e * (fill / close[i - 1] - 1)); equity -= equity * abs(e) * (fee + slip)
                held = 0.0; stops += 1; stopped_dir = sdir; turn_tot += abs(e)
                eq[i] = equity; peak = max(peak, equity); continue
        # ---- honest liquidation ----
        adverse = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adverse, 0) >= (1 - maint):
            equity *= 0.01; liqs += 1; held = 0.0; eq[i] = equity; peak = max(peak, equity); continue
        ret = close[i] / close[i - 1] - 1
        turn = abs(e - held); turn_tot += turn
        equity *= (1 + e * ret); equity -= equity * turn * (fee + slip)
        held = e; eq[i] = equity; peak = max(peak, equity)
    eq = eq[i0:]; dd = (eq / np.maximum.accumulate(eq) - 1).min()
    return eq[-1], dd, liqs, stops, turn_tot / ((n - i0) / ANN)

print("8B (5x, no turnover control) — effect of a cut-loss:")
print(f"  {'stop':>6s} | {'@0bp final':>15s} {'DD':>5s} {'liq':>4s} {'stops':>6s} | {'@50bp final':>13s} {'DD':>5s}")
for stop in [0.0, 0.10, 0.15, 0.20, 0.30]:
    f0, d0, l0, s0, t0 = sim(5, 0.0, stop=stop)
    f5, d5, l5, s5, t5 = sim(5, 0.005, stop=stop)
    lbl = "none" if stop == 0 else f"{int(stop*100)}%"
    print(f"  {lbl:>6s} | ${f0:>14,.0f} {d0*100:>4.0f}% {l0:>4d} {s0:>6d} | ${f5:>12,.0f} {d5*100:>4.0f}%")

print("\n2x B (turnover-controlled) — effect of a cut-loss:")
print(f"  {'stop':>6s} | {'@0bp final':>15s} {'DD':>5s} {'stops':>6s} {'turn/yr':>7s} | {'@50bp final':>13s} {'DD':>5s}")
for stop in [0.0, 0.10, 0.15, 0.20, 0.30]:
    f0, d0, l0, s0, t0 = sim(2, 0.0, stop=stop, smooth=5, band=0.15)
    f5, d5, l5, s5, t5 = sim(2, 0.005, stop=stop, smooth=5, band=0.15)
    lbl = "none" if stop == 0 else f"{int(stop*100)}%"
    print(f"  {lbl:>6s} | ${f0:>14,.0f} {d0*100:>4.0f}% {s0:>6d} {t0:>6.0f}x | ${f5:>12,.0f} {d5*100:>4.0f}%")
