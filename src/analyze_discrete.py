"""Does running the strategy as DISCRETE trades with its own trailing cut-loss (instead of
continuous daily rebalancing) control slippage? Compares:
  CONTINUOUS-B : daily-rebalanced exposure (current model, smooth+band)
  DISCRETE     : enter on signal at frozen size, HOLD, exit only on (a) trailing cut-loss
                 (10% long / 7% short, no look-ahead) or (b) signal flip / conviction loss.
Turnover = entry+exit only (no daily churn). Honest: 2014+, fees, slippage on turnover, liquidation.
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
FEE, MAINT = 0.0005, 0.01

def continuous(lev, slip, smooth=5, band=0.15):
    e_in = pd.Series(expf).ewm(span=smooth, adjust=False).mean().to_numpy()
    equity = peak = 500.0; held = 0.0; liq = 0; turn = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        tgt = e_in[i - 1] * lev
        if rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
            tgt = np.clip(tgt, -abs(e_in[i - 1]) * lev, abs(e_in[i - 1]) * lev); tgt *= min(1.0, 0.60 / rv[i - 1])
        if equity < peak * 0.70:
            tgt *= 0.5
        e = tgt
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0):
            e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= 1 - MAINT:
            equity *= 0.01; liq += 1; held = 0.0; eq[i] = equity; peak = max(peak, equity); continue
        t = abs(e - held); turn += t
        equity *= (1 + e * (close[i] / close[i - 1] - 1)); equity -= equity * t * (FEE + slip)
        held = e; eq[i] = equity; peak = max(peak, equity)
    eq = eq[i0:]; return eq[-1], (eq / np.maximum.accumulate(eq) - 1).min(), liq, turn / ((n - i0) / ANN), None

def discrete(lev, slip, trail_l=0.10, trail_s=0.07):
    equity = peak = 500.0; liq = 0; turn = 0.0; trades = 0; eq = np.full(n, 500.0)
    pos = None   # dict(dir, size, stop, ref)
    for i in range(i0, n):
        # ---- manage open position FIRST (no look-ahead: check stop before trailing) ----
        if pos is not None:
            d, size = pos["dir"], pos["size"]; exit_px = None
            # liquidation intraday
            adv = (-(low[i] / close[i - 1] - 1)) if d > 0 else (high[i] / close[i - 1] - 1)
            if abs(size) * max(adv, 0) >= 1 - MAINT:
                equity *= 0.01; liq += 1; pos = None; eq[i] = equity; peak = max(peak, equity); continue
            if d > 0 and low[i] <= pos["stop"]:
                exit_px = pos["stop"]
            elif d < 0 and high[i] >= pos["stop"]:
                exit_px = pos["stop"]
            else:                                   # trail the stop with today's extreme
                if d > 0:
                    pos["ref"] = max(pos["ref"], high[i]); pos["stop"] = max(pos["stop"], pos["ref"] * (1 - trail_l))
                else:
                    pos["ref"] = min(pos["ref"], low[i]); pos["stop"] = min(pos["stop"], pos["ref"] * (1 + trail_s))
                # signal exit at close if direction flips / conviction lost
                sd = 1 if expf[i] > 0 else (-1 if expf[i] < 0 else 0)
                if sd != d:
                    exit_px = close[i]
            if exit_px is not None:
                equity *= (1 + size * (exit_px / close[i - 1] - 1)); equity -= equity * abs(size) * (FEE + slip)
                pos = None; eq[i] = equity; peak = max(peak, equity)
            else:
                equity *= (1 + size * (close[i] / close[i - 1] - 1))
                eq[i] = equity; peak = max(peak, equity)
            if pos is not None:
                continue
        # ---- flat: look for an entry ----
        sd = 1 if expf[i - 1] > 0 else (-1 if expf[i - 1] < 0 else 0)
        if sd != 0 and equity > 0.05:
            vs = min(1.0, 0.60 / rv[i - 1]) if (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0) else 1.0
            size = expf[i - 1] * lev * vs
            entry = close[i - 1]
            stop = entry * (1 - trail_l) if sd > 0 else entry * (1 + trail_s)
            pos = dict(dir=sd, size=size, stop=stop, ref=entry)
            equity -= equity * abs(size) * (FEE + slip); turn += abs(size); trades += 1
            equity *= (1 + size * (close[i] / close[i - 1] - 1))
        eq[i] = equity; peak = max(peak, equity)
    eq = eq[i0:]; return eq[-1], (eq / np.maximum.accumulate(eq) - 1).min(), liq, turn / ((n - i0) / ANN), trades

for lev in (2, 5):
    print(f"\n================  leverage {lev}x  ================")
    print(f"{'model':28s} {'@0bp final':>15s} {'@50bp final':>14s} {'maxDD':>6s} {'turn/yr':>7s} {'liq':>4s} {'trades':>7s}")
    for nm, fn in [("CONTINUOUS-B (rebalance daily)", continuous), ("DISCRETE (hold + trailing stop)", discrete)]:
        f0, d0, l0, t0, n0 = fn(lev, 0.0)
        f5, d5, l5, t5, n5 = fn(lev, 0.005)
        tr = "" if n5 is None else f"{n5}"
        print(f"{nm:28s} ${f0:>14,.0f} ${f5:>13,.0f} {d5*100:>5.0f}% {t5:>6.0f}x {l5:>4d} {tr:>7s}")
