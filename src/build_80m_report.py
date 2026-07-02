"""Full trade-by-trade report for the ORIGINAL leveraged '$80M' model (M1-vs-M5 X/Y engine:
50% deploy x 5x long / 2x short, 7% trailing stop, 2014+). Logs EVERY trade's PnL and shows how
50bp / 100bp slippage compounds to destroy the headline. Writes an Excel with per-trade sheets +
a summary, and prints the story. Honest: same fills, slippage charged on notional at entry AND exit.
"""
import os, numpy as np, pandas as pd
import compare_m1m5 as cm, regime_system as rs, regime_switch_sim as rss, signals as sg, backtest as bt, fast_search as fs
FEE = 0.0005
df = cm.prep(cm.build_combined()); reg = rs.classify(df)
sigs = sg.run_all(df, single_lookahead=False); memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
close = df["close"].to_numpy(); high = df["high"].to_numpy(); low = df["low"].to_numpy()
dates = df["Date"].tolist(); n = len(df)
i0 = max(next(i for i, d in enumerate(dates) if d >= "2014-01-01"), 260)
SM = {(r, 1): (0.5, 5, 0.07) for r in fs.LONG_REGIMES}
for r in fs.SHORT_REGIMES: SM[(r, -1)] = (0.5, 2, 0.07)

def run(slip):
    base = 500.0; eq = 500.0; pos = None; trades = []; eqarr = []
    for i in range(i0, n):
        rg = reg[i]
        if pos is not None:
            d = pos["dir"]; cl = pos["cl"]; ex = False; fillp = None; reason = ""
            if d == 1:
                if low[i] <= pos["stop"]: fillp = pos["stop"]; ex = True; reason = "trailing stop"
                elif high[i] > pos["hi"]: pos["hi"] = high[i]; pos["stop"] = max(pos["stop"], pos["hi"] * (1 - cl))
            else:
                if high[i] >= pos["stop"]: fillp = pos["stop"]; ex = True; reason = "trailing stop"
                elif low[i] < pos["lo"]: pos["lo"] = low[i]; pos["stop"] = min(pos["stop"], pos["lo"] * (1 + cl))
            if not ex:
                m = memb[pos["strat"]][i]
                su = (rg in rss.TREND_GROUP) if (pos["kind"] == "trend" and pos["regime"] in rss.TREND_GROUP) \
                    else ((rg in rss.BEAR_GROUP) if pos["regime"] in rss.BEAR_GROUP else rg == pos["regime"])
                sigx = (m * d < 0) if pos["kind"] == "trend" else (m * d <= 0)
                if (not su) or sigx: fillp = close[i]; ex = True; reason = "signal/regime exit"
            if ex:
                ret = (fillp / pos["entry"] - 1.0) * d
                gross = pos["nw"] * ret; exit_cost = pos["nw"] * (FEE + slip)
                eq = base + gross - exit_cost; base = eq
                trades.append(dict(entry_date=pos["entry_dt"], exit_date=dates[i], market=pos["regime"],
                                   direction="LONG" if d == 1 else "SHORT", leverage=pos["lev"],
                                   entry_px=round(pos["entry"], 2), exit_px=round(fillp, 2),
                                   notional=round(pos["nw"], 2), price_move_pct=round(ret * 100, 2),
                                   gross_pnl=round(gross, 2), entry_cost=round(pos["entry_cost"], 2),
                                   exit_cost=round(exit_cost, 2),
                                   net_pnl=round(gross - pos["entry_cost"] - exit_cost, 2),
                                   equity_after=round(eq, 2), exit_reason=reason))
                pos = None
            else:
                eq = base + pos["nw"] * ((close[i] / pos["entry"] - 1.0) * d)
        if pos is None and base > 1:
            strat, kind, cs = rss.MAP.get(rg, (None, "flat", 0))
            if strat and cs >= 0.5:
                m = memb[strat][i]; d = 1 if m > 0 else (-1 if m < 0 else 0)
                if d == -1 and (rg, -1) not in SM: d = 0
                if d != 0:
                    sz, lev, cl = SM[(rg, d)]; entry = close[i]; nw = sz * base * lev
                    ecost = nw * (FEE + slip); base = base - ecost
                    pos = dict(entry=entry, dir=d, strat=strat, kind=kind, regime=rg, cl=cl, lev=lev,
                               hi=entry, lo=entry, stop=(entry * (1 - cl) if d == 1 else entry * (1 + cl)),
                               nw=nw, entry_cost=ecost, entry_dt=dates[i])
                    eq = base
        eqarr.append(max(eq, 1e-9))
    s = pd.Series(eqarr); dd = (s / s.cummax() - 1).min()
    return eqarr[-1], dd, trades

OUTX = os.path.join(cm.DATA, "..", "..", "excel_reports", "BTC_80M_model_trade_report.xlsx")
res = {}
for slip, tag in [(0.0, "0bp"), (0.005, "50bp"), (0.010, "100bp")]:
    fin, dd, trades = run(slip); res[tag] = (fin, dd, trades)
    tot_slip = sum(t["entry_cost"] + t["exit_cost"] for t in trades)
    print(f"{tag:>5}: final ${fin:,.0f}   maxDD {dd*100:.0f}%   trades {len(trades)}   total fees+slip paid ${tot_slip:,.0f}")

with pd.ExcelWriter(OUTX, engine="openpyxl") as xl:
    summ = pd.DataFrame([{"slippage": tag, "final_$": round(res[tag][0], 2), "maxDD_%": round(res[tag][1] * 100, 1),
                          "trades": len(res[tag][2]),
                          "total_cost_$": round(sum(t["entry_cost"] + t["exit_cost"] for t in res[tag][2]), 2),
                          "vs_0bp_%": round((res[tag][0] / res["0bp"][0] - 1) * 100, 2)} for tag in ["0bp", "50bp", "100bp"]])
    summ.to_excel(xl, sheet_name="Summary", index=False)
    for tag in ["0bp", "50bp", "100bp"]:
        pd.DataFrame(res[tag][2]).to_excel(xl, sheet_name=f"Trades_{tag}", index=False)
print("\nsaved", os.path.abspath(OUTX))
# sample: biggest winners/losers at 0bp
T = pd.DataFrame(res["0bp"][2])
print(f"\n0bp trade log: {len(T)} trades. Top 5 by gross PnL:")
for _, r in T.nlargest(5, "gross_pnl").iterrows():
    print(f"  {r.entry_date}->{r.exit_date} {r.direction} {r.market} lev{r.leverage} move {r.price_move_pct:+.0f}%  gross ${r.gross_pnl:,.0f}")
