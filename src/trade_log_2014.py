"""Excel trade report from 2014 matching the ~$1.6B leverage backtest.
Config = 50% margin x 5x long / 2x short, 7% trailing stop, perfect fills (the exact
config behind $1.6B). Columns: market/strategy/confidence/cut-loss/sizing/margin and
PnL both WITHOUT margin (50% at 1x) and WITH margin (50% x 5/2 -> ~$1.6B). Daily
fidelity (pre-2017 = CoinGecko daily, no intraday minute). 2014-01 -> now.

Output: New setup for BTC/BTC_Power_trade_report_2014_leverage.xlsx
"""
import os
import numpy as np
import pandas as pd
import compare_m1m5 as cm
import regime_system as rs
import regime_switch_sim as rss
import signals as sg
import backtest as bt
import fast_search as fs
import trade_log as tl  # reuse _format

HERE = os.path.dirname(__file__)
OUTXLSX = os.path.join(HERE, "..", "..", "BTC_Power_trade_report_2014_leverage.xlsx")
FEE = 0.0005


def main():
    df = cm.prep(cm.build_combined()); reg = rs.classify(df)
    sigs = sg.run_all(df, single_lookahead=False)
    memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
    close = df["close"].to_numpy(); high = df["high"].to_numpy(); low = df["low"].to_numpy()
    dates = df["Date"].tolist(); n = len(df)
    i0 = max(next(i for i, d in enumerate(dates) if d >= "2014-01-01"), 260)
    SM = {(r, 1): (0.5, 5, 0.07) for r in fs.LONG_REGIMES}
    for r in fs.SHORT_REGIMES:
        SM[(r, -1)] = (0.5, 2, 0.07)

    eq_nm = eq_wm = 500.0; pos = None; trades = []
    for i in range(i0, n):
        rg = reg[i]
        if pos is not None:
            d = pos["dir"]; cl = pos["cl"]; ex = False; fillp = None; reason = None
            if d == 1:
                if low[i] <= pos["stop"]:                       # check existing stop FIRST (no look-ahead)
                    fillp = pos["stop"]; reason = "Trailing stop"; ex = True
                elif high[i] > pos["hi"]:                       # else raise the trailing stop
                    pos["hi"] = high[i]; pos["stop"] = max(pos["stop"], pos["hi"] * (1 - cl))
            else:
                if high[i] >= pos["stop"]:
                    fillp = pos["stop"]; reason = "Trailing stop"; ex = True
                elif low[i] < pos["lo"]:
                    pos["lo"] = low[i]; pos["stop"] = min(pos["stop"], pos["lo"] * (1 + cl))
            if not ex:
                m = memb[pos["strat"]][i]
                su = (rg in rss.TREND_GROUP) if (pos["kind"] == "trend" and pos["regime"] in rss.TREND_GROUP) \
                    else ((rg in rss.BEAR_GROUP) if pos["regime"] in rss.BEAR_GROUP else rg == pos["regime"])
                sigx = (m * d < 0) if pos["kind"] == "trend" else (m * d <= 0)
                if (not su) or sigx:
                    fillp = close[i]; reason = "Regime-change" if not su else "Signal-exit"; ex = True
            if ex:
                ret = (fillp / pos["entry"] - 1.0) * d
                pnl_nm = pos["nn"] * ret - pos["nn"] * FEE * 2; eq_nm += pnl_nm
                pnl_wm = pos["nw"] * ret - pos["nw"] * FEE * 2; eq_wm += pnl_wm
                trades.append(dict(entry_dt=pos["edt"], exit_dt=dates[i], days=i - pos["ei"],
                                   market=pos["regime"], strategy=pos["strat"],
                                   direction="LONG" if d == 1 else "SHORT", confidence=pos["bucket"],
                                   entry=round(pos["entry"], 2), exit=round(float(fillp), 2), ret=ret,
                                   cutloss_lvl=round(pos["cutloss"], 2), cutloss_pct=cl,
                                   sizing=0.5, margin=round(pos["mw"], 2), lev=pos["lev"],
                                   pnl_nm=round(pnl_nm, 2), pnl_wm=round(pnl_wm, 2), reason=reason,
                                   eq_nm=round(eq_nm, 2), eq_wm=round(eq_wm, 2)))
                pos = None
        if pos is None and eq_nm > 1:
            strat, kind, cs = rss.MAP.get(rg, (None, "flat", 0))
            cell = SM.get((rg, 1 if (strat and memb[strat][i] > 0) else -1))
            if strat and cs >= 0.5:
                m = memb[strat][i]; d = 1 if m > 0 else (-1 if m < 0 else 0)
                if d == -1 and (rg, -1) not in SM:
                    d = 0
                if d != 0:
                    sz, lev, cl = SM[(rg, d)]
                    bk = "High" if cs >= 1.8 else ("Med" if cs >= 1.0 else "Low")
                    entry = close[i]; nn = sz * eq_nm; mw = sz * eq_wm; nw = mw * lev
                    cutloss = entry * (1 - cl) if d == 1 else entry * (1 + cl)
                    pos = dict(entry=entry, edt=dates[i], ei=i, dir=d, strat=strat, kind=kind,
                               regime=rg, bucket=bk, cl=cl, lev=lev, hi=entry, lo=entry, stop=cutloss,
                               cutloss=cutloss, nn=nn, nw=nw, mw=mw)
    export(trades)
    w = sum(1 for t in trades if t["ret"] > 0)
    print(f"trades {len(trades)} | win {w/len(trades)*100:.1f}% | no-margin ${eq_nm:,.0f} | with-margin ${eq_wm:,.0f}")
    print("->", OUTXLSX)


def export(trades):
    tdf = pd.DataFrame(trades); tdf.insert(0, "#", range(1, len(tdf) + 1))
    cols = {"#": "#", "entry_dt": "Entry Date", "exit_dt": "Exit Date", "days": "Days Held",
            "market": "Market Type", "strategy": "Strategy", "direction": "Direction",
            "confidence": "Confidence", "entry": "Entry $", "exit": "Exit $", "ret": "Return %",
            "cutloss_lvl": "Cut-Loss $", "cutloss_pct": "Cut-Loss %", "sizing": "Sizing % equity",
            "margin": "Margin $ used", "lev": "Leverage (margin)", "pnl_nm": "PnL no-margin $",
            "pnl_wm": "PnL with-margin $", "reason": "Exit Reason", "eq_nm": "Equity no-margin $",
            "eq_wm": "Equity with-margin $"}
    tdf = tdf[list(cols)].rename(columns=cols)
    wins = (tdf["Return %"] > 0).sum(); ntr = len(tdf)
    lw = ((tdf["Direction"] == "LONG") & (tdf["Return %"] > 0)).sum(); ln = (tdf["Direction"] == "LONG").sum()
    sw = ((tdf["Direction"] == "SHORT") & (tdf["Return %"] > 0)).sum(); sn = (tdf["Direction"] == "SHORT").sum()
    summ = pd.DataFrame({"Metric": ["Config", "Period", "Total trades", "Win ratio (overall)",
                                    "Win ratio LONG", "Win ratio SHORT", "Final WITH-margin $ (≈$1.6B)",
                                    "Final NO-margin $ (50% at 1x)", "", "NOTES",
                                    "WITH-margin = 50% margin x 5x long / 2x short, PERFECT fills (optimistic).",
                                    "Real crash slippage collapses it massively (150bp -> ~$35k from 2014).",
                                    "NO-margin = same trades, 50% of equity at 1x (no leverage).",
                                    "Pre-2017 uses CoinGecko daily (no intraday minute). Hypothetical; not advice."],
                         "Value": ["50% margin · 5x long / 2x short · 7% trailing · perfect fills",
                                   f"{tdf['Entry Date'].iloc[0]} .. {tdf['Exit Date'].iloc[-1]}", ntr,
                                   f"{wins/ntr*100:.1f}%", f"{(lw/ln*100 if ln else 0):.1f}% ({lw}/{ln})",
                                   f"{(sw/sn*100 if sn else 0):.1f}% ({sw}/{sn})",
                                   f"{tdf['Equity with-margin $'].iloc[-1]:,.0f}",
                                   f"{tdf['Equity no-margin $'].iloc[-1]:,.0f}", "", "", "", "", "", ""]})
    tdf["_y"] = tdf["Exit Date"].str[:4]
    yr = []
    for y, g in tdf.groupby("_y"):
        w = (g["Return %"] > 0).sum()
        yr.append(dict(Year=y, Trades=len(g), **{"Win %": f"{w/len(g)*100:.1f}%"},
                       **{"PnL no-margin $": round(g["PnL no-margin $"].sum(), 0),
                          "PnL with-margin $": round(g["PnL with-margin $"].sum(), 0)}))
    ydf = pd.DataFrame(yr); tdf = tdf.drop(columns=["_y"])
    with pd.ExcelWriter(OUTXLSX, engine="openpyxl") as xw:
        summ.to_excel(xw, sheet_name="Summary", index=False)
        ydf.to_excel(xw, sheet_name="By Year", index=False)
        tdf.to_excel(xw, sheet_name="Trades", index=False)
        tl._format(xw, tdf, summ, ydf, tdf)


if __name__ == "__main__":
    main()
