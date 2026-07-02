"""Run the M1-vs-M5 X/Y engine (50% deploy x 5x long/2x short, 7% trailing stop = our trade_log_2014
reproduction of the famous $1.6B) through the SAME slippage/metrics framework, with daily mark-to-market.
Prints all fields at 0/50/100bp for the 3-way table vs 3.25/3 short-selective and original 8B.
"""
import numpy as np, pandas as pd
import compare_m1m5 as cm, regime_system as rs, regime_switch_sim as rss, signals as sg, backtest as bt, fast_search as fs
ANN = 365; FEE = 0.0005
df = cm.prep(cm.build_combined()); reg = rs.classify(df)
sigs = sg.run_all(df, single_lookahead=False)
memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
close = df["close"].to_numpy(); high = df["high"].to_numpy(); low = df["low"].to_numpy()
dates = df["Date"].tolist(); n = len(df); dts = pd.to_datetime(df["Date"])
i0 = max(next(i for i, d in enumerate(dates) if d >= "2014-01-01"), 260)
SM = {(r, 1): (0.5, 5, 0.07) for r in fs.LONG_REGIMES}
for r in fs.SHORT_REGIMES: SM[(r, -1)] = (0.5, 2, 0.07)
WIN = [("2017-12-16","2018-11-18"),("2021-10-20","2022-03-09"),("2025-05-22","2025-12-01")]

def run(slip):
    base = 500.0; eq = 500.0; pos = None; trets = []; eqarr = []; ddates = []
    for i in range(i0, n):
        rg = reg[i]
        if pos is not None:
            d = pos["dir"]; cl = pos["cl"]; ex = False; fillp = None
            if d == 1:
                if low[i] <= pos["stop"]: fillp = pos["stop"]; ex = True
                elif high[i] > pos["hi"]: pos["hi"] = high[i]; pos["stop"] = max(pos["stop"], pos["hi"] * (1 - cl))
            else:
                if high[i] >= pos["stop"]: fillp = pos["stop"]; ex = True
                elif low[i] < pos["lo"]: pos["lo"] = low[i]; pos["stop"] = min(pos["stop"], pos["lo"] * (1 + cl))
            if not ex:
                m = memb[pos["strat"]][i]
                su = (rg in rss.TREND_GROUP) if (pos["kind"] == "trend" and pos["regime"] in rss.TREND_GROUP) \
                    else ((rg in rss.BEAR_GROUP) if pos["regime"] in rss.BEAR_GROUP else rg == pos["regime"])
                sigx = (m * d < 0) if pos["kind"] == "trend" else (m * d <= 0)
                if (not su) or sigx: fillp = close[i]; ex = True
            if ex:
                ret = (fillp / pos["entry"] - 1.0) * d
                eq = base + pos["nw"] * ret - pos["nw"] * (FEE + slip)   # realize + exit cost
                base = eq; trets.append(ret); pos = None
            else:
                eq = base + pos["nw"] * ((close[i] / pos["entry"] - 1.0) * d)  # daily MTM
        if pos is None and base > 1:
            strat, kind, cs = rss.MAP.get(rg, (None, "flat", 0))
            if strat and cs >= 0.5:
                m = memb[strat][i]; d = 1 if m > 0 else (-1 if m < 0 else 0)
                if d == -1 and (rg, -1) not in SM: d = 0
                if d != 0:
                    sz, lev, cl = SM[(rg, d)]; entry = close[i]; nw = sz * base * lev
                    base = base - nw * (FEE + slip)                     # entry cost
                    pos = dict(entry=entry, dir=d, strat=strat, kind=kind, regime=rg, cl=cl, lev=lev,
                               hi=entry, lo=entry, stop=(entry*(1-cl) if d == 1 else entry*(1+cl)), nw=nw)
                    eq = base
        eqarr.append(max(eq, 1e-9)); ddates.append(dts.iloc[i])
    return np.array(eqarr), trets, ddates

def metrics(eqarr, ddates, trets):
    s = pd.Series(eqarr, index=pd.to_datetime(ddates)); r = s.pct_change().dropna(); yrs = len(s) / ANN
    cagr = (s.iloc[-1] / 500) ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dd = (s / s.cummax() - 1).min(); ww = [(s.loc[a:b]/s.loc[a:b].cummax()-1).min()*100 for a, b in WIN]
    wr = np.mean(np.array(trets) > 0) if trets else 0
    return s.iloc[-1], cagr, sh, (cagr/abs(dd) if dd < 0 else 0), dd, wr, len(trets), ww

print("M1-vs-M5 X/Y engine (50% x 5x/2x, 7% trail) through honest slippage:")
out = {}
for slip in (0.0, 0.005, 0.010):
    eqarr, trets, ddates = run(slip); out[slip] = metrics(eqarr, ddates, trets)
m0 = out[0.0]; m5 = out[0.005]; m1 = out[0.010]
print(f"  $@0bp  ${m0[0]:,.0f}   (sanity vs famous ~$1.6B)")
print(f"  $@50bp ${m5[0]:,.0f}")
print(f"  $@100bp ${m1[0]:,.0f}")
print(f"  CAGR {m5[1]*100:.0f}% | Sharpe {m5[2]:.2f} | Calmar {m5[3]:.2f} | maxDD {m5[4]*100:.0f}% | win {m5[5]*100:.0f}% | trades {m5[6]} ({m5[6]*2} in&out) | trades/yr {m5[6]/((n-i0)/ANN):.0f}")
print(f"  3 drops W1/W2/W3: {[round(x) for x in m5[7]]}")
