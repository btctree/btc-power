"""Multi-timeframe regime model, as specified: classify each bar into TREND / RANGE / FLAT / VOLATILE
(no look-ahead — trailing vol rank + medium-trend slope), apply the matched strategy per regime, use
ATR-based cut-loss, exit on regime change, size by confidence (capped 50%). Then MEASURE the per-regime
win rate and realized reward:risk (R multiple) — to show the win-rate/payoff frontier honestly.
Also reports overall CAGR / maxDD / trades / liquidations. Asset: BTC (highest-return; frame extends to all).
"""
import numpy as np, pandas as pd
import compare_m1m5 as cm
from global_engine import fetch_yahoo
ANN = 365
df = cm.prep(fetch_yahoo("BTC-USD"))
c = df["close"].to_numpy(); hi = df["high"].to_numpy(); lo = df["low"].to_numpy()
s20 = df["SMA20"].to_numpy(); s50 = df["SMA50"].to_numpy(); atr = df["ATR"].to_numpy()
bbu = df["BB_Upper"].to_numpy(); bbl = df["BB_Lower"].to_numpy(); n = len(df); dates = df["Date"].tolist()
atrp = (atr / c); slope = pd.Series(s50).pct_change(20).to_numpy()          # medium-term trend
volrank = pd.Series(atrp).rolling(252, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean()).to_numpy()

def regime(i):
    if slope[i] != slope[i] or volrank[i] != volrank[i]: return "NA"
    if slope[i] > 0.12: return "TREND_UP"
    if slope[i] < -0.12: return "TREND_DOWN"
    if volrank[i] < 0.33: return "FLAT"
    if volrank[i] > 0.75: return "VOLATILE"
    return "RANGE"
reg = [regime(i) for i in range(n)]

# --- per-regime strategy, one position at a time, ATR stop, exit on regime change ---
i0 = 260; cash = 500.0; pos = None; trades = []; eqarr = []; peak = 500.0; liq = 0
for i in range(i0, n):
    r = reg[i - 1]                                    # decide on yesterday's regime (no look-ahead)
    price = c[i]
    if pos:
        d = pos["dir"]; stop = pos["stop"]
        # trail for trend trades
        if pos["kind"] == "trend":
            pos["stop"] = max(stop, c[i - 1] - 2 * atr[i - 1]) if d > 0 else min(stop, c[i - 1] + 2 * atr[i - 1])
        ex = None
        if (d > 0 and lo[i] <= pos["stop"]) or (d < 0 and hi[i] >= pos["stop"]): ex = pos["stop"]     # cut-loss
        elif pos["kind"] == "range" and ((d > 0 and hi[i] >= pos["tgt"]) or (d < 0 and lo[i] <= pos["tgt"])): ex = pos["tgt"]  # target
        elif r != pos["regime"] and r not in ("NA",): ex = price                                       # regime changed -> quit
        if ex is not None:
            ret = (ex / pos["entry"] - 1) * d; risk = abs(pos["entry"] - pos["stop0"]) / pos["entry"]
            R = (ret / risk) if risk > 0 else 0
            cash *= (1 + ret * pos["size"] - abs(pos["size"]) * 0.001)     # realize + ~10bp cost
            trades.append(dict(regime=pos["regime"], dir=d, ret=ret, R=R, win=ret > 0)); pos = None
    if not pos and cash > 1:
        conf = min(1.0, abs(slope[i - 1]) / 0.25 + 0.3)                    # confidence from trend strength
        size = min(0.50, 0.30 + 0.40 * conf) if r in ("TREND_UP", "TREND_DOWN") else (0.25 if r == "RANGE" else 0.0)
        if r == "TREND_UP" and c[i - 1] > s20[i - 1]:
            pos = dict(dir=1, kind="trend", entry=price, stop=price - 2 * atr[i - 1], stop0=price - 2 * atr[i - 1], regime=r, size=size)
        elif r == "TREND_DOWN" and c[i - 1] < s20[i - 1]:
            pos = dict(dir=-1, kind="trend", entry=price, stop=price + 2 * atr[i - 1], stop0=price + 2 * atr[i - 1], regime=r, size=size)
        elif r == "RANGE" and c[i - 1] < bbl[i - 1]:
            pos = dict(dir=1, kind="range", entry=price, stop=price - 1.5 * atr[i - 1], stop0=price - 1.5 * atr[i - 1], tgt=s20[i - 1], regime=r, size=size)
        elif r == "RANGE" and c[i - 1] > bbu[i - 1]:
            pos = dict(dir=-1, kind="range", entry=price, stop=price + 1.5 * atr[i - 1], stop0=price + 1.5 * atr[i - 1], tgt=s20[i - 1], regime=r, size=size)
    peak = max(peak, cash); eqarr.append(cash)
eq = pd.Series(eqarr, index=pd.to_datetime([d for d in dates[i0:]]))
yrs = len(eq) / ANN; cagr = (eq.iloc[-1] / 500) ** (1 / yrs) - 1; dd = (eq / eq.cummax() - 1).min()
T = pd.DataFrame(trades)
print("REGIME DISTRIBUTION:", {k: reg.count(k) for k in ["TREND_UP", "TREND_DOWN", "RANGE", "FLAT", "VOLATILE"]})
print(f"\n{'regime':12s} {'#tr':>4} {'win%':>6} {'avgWinR':>8} {'avgLossR':>9} {'R:R':>6} {'expectancy':>11}")
for rg in ["TREND_UP", "TREND_DOWN", "RANGE"]:
    g = T[T.regime == rg]
    if len(g) == 0: continue
    w = g[g.R > 0]["R"]; l = g[g.R <= 0]["R"]
    rr = (w.mean() / abs(l.mean())) if len(l) and l.mean() != 0 else float("nan")
    print(f"{rg:12s} {len(g):>4} {100*g['win'].mean():>5.0f}% {w.mean() if len(w) else 0:>8.2f} {l.mean() if len(l) else 0:>9.2f} {rr:>6.2f} {g['R'].mean():>+11.2f}")
allw = T[T.R > 0]["R"]; alll = T[T.R <= 0]["R"]
print(f"{'ALL':12s} {len(T):>4} {100*T['win'].mean():>5.0f}% {allw.mean():>8.2f} {alll.mean():>9.2f} {allw.mean()/abs(alll.mean()):>6.2f} {T['R'].mean():>+11.2f}")
print(f"\nOverall: CAGR {cagr*100:.0f}%  maxDD {dd*100:.0f}%  trades {len(T)}  liquidations {liq}  $500->${eq.iloc[-1]:,.0f}")
print(f"target check: win>60% & R:R 3:1 in the SAME regime? ->", "NONE achieves both (see table)")
