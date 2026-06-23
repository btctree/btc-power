"""Real-trade simulation on $500 using 1-minute data for intraday fills.

Decision: at each daily close, the validated 9-strategy 'Consensus Long' ensemble
gives a confidence (0..1). That drives entry / sizing / leverage. The open position
is then managed INTRADAY on 1-min bars: trailing stop, take-profit, hard cut-loss,
and explicit LIQUIDATION — a resting stop fires intraday, not only at the daily close.

Config is in CONFIG so the 4-role review loop can tune it. No look-ahead: a day's
1-min bars only manage a position opened at a prior daily close.
"""
import os, json
import numpy as np
import pandas as pd
import datetime as dt
import indicators as ind
import signals as sg
import backtest as bt

HERE = os.path.dirname(__file__)
DATADIR = os.path.join(HERE, "..", "data")
MEMBERS = ["OBV", "DSAM", "MACD", "RSI", "EMA", "BB", "MFI", "OBV_ROC", "MACD_SIG"]

CONFIG = dict(
    start=500.0,
    fee=0.0005,            # taker, per side, on notional
    lev_long=5.0,          # framework reference 5x long
    maint=0.005,           # maintenance margin rate (liquidation buffer)
    trail=0.07,            # 7% trailing ratchet behind high-water
    cutloss=0.07,          # initial hard stop below entry
    entry_thresh=0.15,     # open when consensus >= this
    exit_thresh=0.10,      # signal-exit when consensus falls below this
    size_high=0.60, size_med=0.50, size_low=0.45,   # margin % of equity by confidence
    conf_high=0.50, conf_med=0.30,                  # bucket cutoffs (low = entry_thresh..conf_med)
    use_funding=True,
    use_regime_tp=True,    # ranging -> take profit at SMA20 (channel mid)
)


def load_daily():
    raw = pd.read_csv(os.path.join(DATADIR, "btc_daily.csv"))
    df = ind.compute(raw[["date", "close", "volume", "high", "low", "open"]]
                     .rename(columns={"date": "Date"})).reset_index(drop=True)
    df["SMA50"] = df["close"].rolling(50).mean()
    return df


def load_intraday():
    z = np.load(os.path.join(DATADIR, "intraday_1m.npz"))
    day = z["day"]; h = z["h"]; l = z["l"]; c = z["c"]
    udays, starts = np.unique(day, return_index=True)
    ends = np.append(starts[1:], len(day))
    day_index = {int(d): (int(s), int(e)) for d, s, e in zip(udays, starts, ends)}
    return dict(h=h, l=l, c=c, day_index=day_index)


def load_funding():
    p = os.path.join(DATADIR, "funding.csv")
    if not os.path.exists(p):
        return {}
    f = pd.read_csv(p)
    return dict(zip(f["date"], f["funding_rate"]))


def consensus(df):
    sigs = sg.run_all(df, single_lookahead=False)
    memb = {k: bt.signals_to_position(sigs[k]) for k in MEMBERS}
    pos = np.clip(np.mean([memb[k] for k in MEMBERS], axis=0), 0.0, None)
    return pos


def date_to_ord(s):
    y, m, d = map(int, s.split("-"))
    return (dt.date(y, m, d) - dt.date(1970, 1, 1)).days


def size_for(conf, cfg):
    if conf >= cfg["conf_high"]:
        return cfg["size_high"], "High"
    if conf >= cfg["conf_med"]:
        return cfg["size_med"], "Med"
    return cfg["size_low"], "Low"


def simulate(cfg=CONFIG, verbose=False):
    df = load_daily()
    intr = load_intraday()
    funding = load_funding()
    conf = consensus(df)
    close = df["close"].to_numpy()
    sma20 = df["SMA20"].to_numpy()
    dates = df["Date"].tolist()
    di = intr["day_index"]; IH = intr["h"]; IL = intr["l"]; IC = intr["c"]

    equity = cfg["start"]
    pos = None              # open position dict
    trades = []
    eq_curve = []
    liquidations = 0
    fees_paid = 0.0
    funding_paid = 0.0

    def intraday_arrays(date_str):
        o = date_to_ord(date_str)
        if o not in di:
            return None
        s, e = di[o]
        return IL[s:e], IH[s:e], IC[s:e]

    start_i = 260  # warmup for all signals
    for i in range(len(df)):
        date_i = dates[i]
        # ---------- 1. intraday management of an OPEN position on day i ----------
        if pos is not None:
            arr = intraday_arrays(date_i)
            exited = False
            if arr is not None:
                lows, highs, closes = arr
                # walk minute bars in order
                for bl, bh in zip(lows, highs):
                    # update trailing stop on new highs (long)
                    if bh > pos["hi"]:
                        pos["hi"] = bh
                        pos["stop"] = max(pos["stop"], pos["hi"] * (1 - cfg["trail"]))
                    # liquidation first (worst case within the bar)
                    if bl <= pos["liq"]:
                        equity -= pos["margin"]           # lose entire margin
                        fee = pos["notional"] * cfg["fee"]
                        equity -= fee; fees_paid += fee
                        trades.append(_close_trade(pos, pos["liq"], i, date_i, "LIQUIDATED", -pos["margin"] - fee))
                        liquidations += 1; pos = None; exited = True; break
                    # stop (cut-loss or trailing)
                    if bl <= pos["stop"]:
                        exited = _exit(pos, pos["stop"], i, date_i,
                                       "TRAIL/STOP", trades, cfg)
                        equity += exited["pnl"]; fees_paid += exited["fee"]; pos = None; exited = True; break
                    # take-profit
                    if pos["tp"] is not None and bh >= pos["tp"]:
                        ex = _exit(pos, pos["tp"], i, date_i, "TAKE-PROFIT", trades, cfg)
                        equity += ex["pnl"]; fees_paid += ex["fee"]; pos = None; exited = True; break
            # funding for the day if still open
            if pos is not None:
                fr = funding.get(date_i, 0.00011 * 3) if cfg["use_funding"] else 0.0
                fcost = pos["notional"] * fr
                equity -= fcost; funding_paid += fcost

        # ---------- 2. end-of-day i close decision ----------
        if i >= start_i:
            ci = close[i]; cf = conf[i]
            if pos is None:
                if cf >= cfg["entry_thresh"] and equity > 1:
                    frac, bucket = size_for(cf, cfg)
                    margin = equity * frac
                    notional = margin * cfg["lev_long"]
                    fee = notional * cfg["fee"]
                    equity -= fee; fees_paid += fee
                    liq = ci * (1 - (1.0 / cfg["lev_long"]) + cfg["maint"])
                    stop = ci * (1 - cfg["cutloss"])
                    # regime-aware TP: ranging -> SMA20 (mid); else none (ride trail)
                    tp = None
                    reg = _regime(df, i)
                    if cfg["use_regime_tp"] and reg == "RANGING" and sma20[i] > ci:
                        tp = sma20[i]
                    pos = dict(entry=ci, entry_i=i, entry_date=date_i, margin=margin,
                               notional=notional, lev=cfg["lev_long"], conf=cf, bucket=bucket,
                               hi=ci, stop=max(stop, liq * 1.001), liq=liq, tp=tp, regime=reg)
            else:
                # signal exit when consensus collapses
                if cf < cfg["exit_thresh"]:
                    ex = _exit(pos, ci, i, date_i, "SIGNAL-EXIT", trades, cfg)
                    equity += ex["pnl"]; fees_paid += ex["fee"]; pos = None
        eq_curve.append(equity)

    # close any residual position at last close
    if pos is not None:
        ex = _exit(pos, close[-1], len(df) - 1, dates[-1], "EOD-CLOSE", trades, cfg)
        equity += ex["pnl"]; fees_paid += ex["fee"]; pos = None
        eq_curve[-1] = equity

    return _report(cfg, df, eq_curve, trades, liquidations, fees_paid, funding_paid, conf)


def _exit(pos, price, i, date, reason, trades, cfg):
    notional = pos["notional"]
    fee = notional * cfg["fee"]
    pnl_gross = notional * (price / pos["entry"] - 1.0)   # long
    pnl = pnl_gross - fee
    t = _close_trade(pos, price, i, date, reason, pnl)
    trades.append(t)
    return dict(pnl=pnl, fee=fee)


def _close_trade(pos, price, i, date, reason, pnl):
    return dict(entry=pos["entry"], exit=price, entry_date=pos["entry_date"], exit_date=date,
                bars=i - pos["entry_i"], reason=reason, pnl=pnl, margin=pos["margin"],
                notional=pos["notional"], conf=pos["conf"], bucket=pos["bucket"],
                ret_on_margin=pnl / pos["margin"] if pos["margin"] else 0.0,
                regime=pos.get("regime"))


def _regime(df, i):
    c = df["close"].iloc[i]; s20 = df["SMA20"].iloc[i]
    bbu = df["BB_Upper"].iloc[i]; bbl = df["BB_Lower"].iloc[i]; rsi = df["RSI"].iloc[i]
    if s20 != s20 or bbu != bbu:
        return "NEUTRAL"
    bbw = (bbu - bbl) / s20
    bbw_med = ((df["BB_Upper"] - df["BB_Lower"]) / df["SMA20"]).iloc[max(0, i - 365):i + 1].median()
    ext = (c - s20) / s20
    chg14 = (c - df["close"].iloc[i - 14]) / df["close"].iloc[i - 14] if i >= 14 else 0
    rng14 = (df["close"].iloc[i - 14:i + 1].max() - df["close"].iloc[i - 14:i + 1].min()) / c if i >= 14 else 0
    if bbw > bbw_med * 1.15 and abs(ext) > 0.04:
        return "TREND_UP" if ext > 0 else "TREND_DN"
    if rng14 > 0.12 and abs(chg14) < 0.03:
        return "TOXIC"
    if 38 <= rsi <= 62 and bbw < bbw_med:
        return "RANGING"
    return "NEUTRAL"


def _report(cfg, df, eq_curve, trades, liqs, fees, funding, conf):
    eq = np.array(eq_curve)
    dates = df["Date"].tolist()
    ret = np.zeros(len(eq)); ret[1:] = np.where(eq[:-1] > 0, eq[1:] / eq[:-1] - 1, 0)
    ann = 365
    years = len(eq) / ann
    final = eq[-1]
    total = final / cfg["start"] - 1
    cagr = (final / cfg["start"]) ** (1 / years) - 1 if final > 0 else -1.0
    peak = np.maximum.accumulate(eq); dd = eq / peak - 1; maxdd = dd.min()
    sharpe = ret.mean() * ann / (ret.std(ddof=1) * np.sqrt(ann)) if ret.std() > 0 else float("nan")
    down = ret[ret < 0].std(ddof=1) * np.sqrt(ann) if (ret < 0).sum() > 1 else float("nan")
    sortino = ret.mean() * ann / down if down and down > 0 else float("nan")
    calmar = cagr / abs(maxdd) if maxdd < 0 else float("nan")
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
    winrate = len(wins) / len(pnls) if pnls else float("nan")
    reasons = {}
    for t in trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    rpt = dict(
        start=cfg["start"], final=final, total=total, cagr=cagr, maxdd=maxdd,
        sharpe=sharpe, sortino=sortino, calmar=calmar, n_trades=len(trades),
        winrate=winrate, liquidations=liqs, fees_paid=fees, funding_paid=funding,
        avg_win=np.mean(wins) if wins else 0, avg_loss=np.mean(losses) if losses else 0,
        exit_reasons=reasons, eq=eq, dates=dates,
        exposure=float(np.mean([1 if c >= cfg["exit_thresh"] else 0 for c in conf[260:]])),
        config=cfg,
    )
    return rpt


def print_report(r, title="REAL-TRADE SIM"):
    print(f"\n===== {title} =====")
    c = r["config"]
    print(f"Start ${c['start']:.0f}  Lev {c['lev_long']:.0f}x  trail {c['trail']*100:.0f}%  "
          f"cutloss {c['cutloss']*100:.0f}%  sizing {int(c['size_low']*100)}-{int(c['size_high']*100)}%  "
          f"funding {'on' if c['use_funding'] else 'off'}")
    print(f"  Final equity : ${r['final']:,.0f}   ({r['total']*100:+,.0f}%   from ${c['start']:.0f})")
    print(f"  CAGR {r['cagr']*100:,.1f}%   Sharpe {r['sharpe']:.2f}   Sortino {r['sortino']:.2f}   "
          f"maxDD {r['maxdd']*100:.1f}%   Calmar {r['calmar']:.2f}")
    print(f"  Trades {r['n_trades']}   win {r['winrate']*100:.0f}%   LIQUIDATIONS {r['liquidations']}   "
          f"avgWin ${r['avg_win']:.1f}  avgLoss ${r['avg_loss']:.1f}")
    print(f"  Fees ${r['fees_paid']:,.0f}   Funding ${r['funding_paid']:,.0f}   exits {r['exit_reasons']}")


if __name__ == "__main__":
    r = simulate(CONFIG)
    print_report(r, "ITERATION 1 — framework reference config (5x, 60/50/45, 7% trail)")
