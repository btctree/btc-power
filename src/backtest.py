"""Honest backtest engine.
- Position from signals: pos[t] = sign(cumBuy - cumSell) through close[t]  (in {-1,0,+1}).
- NO look-ahead: position decided at close[t] earns the return of t->t+1.
- Fees charged on turnover |pos[t]-pos[t-1]| * fee_rate (per side).
- Reports % equity metrics (the honest view) AND the user's $-per-position sum (parity).
"""
import numpy as np
import pandas as pd

ANN = 365  # daily crypto


def signals_to_position(sig):
    """sig: list of 'Buy'/'Sell'/'Hold+'/'Hold-'/'0'/''. Returns int position series."""
    pos = np.zeros(len(sig), dtype=float)
    nb = ns = 0
    for i, s in enumerate(sig):
        if s == "Buy":
            nb += 1
        elif s == "Sell":
            ns += 1
        net = nb - ns
        pos[i] = 1.0 if net > 0 else (-1.0 if net < 0 else 0.0)
    return pos


def backtest(close, sig, fee_rate=0.0005, lev_long=1.0, lev_short=1.0):
    """Returns dict of results incl equity curve, daily returns, metrics."""
    close = np.asarray(close, dtype=float)
    pos = signals_to_position(sig)
    # apply asymmetric leverage
    lev_pos = np.where(pos > 0, pos * lev_long, pos * lev_short)
    n = len(close)
    ret = np.zeros(n)
    px_ret = np.zeros(n)
    px_ret[1:] = close[1:] / close[:-1] - 1.0
    # position held from t-1 into t earns px_ret[t]
    held = np.zeros(n)
    held[1:] = lev_pos[:-1]
    gross = held * px_ret
    # fees on turnover at time t (when we change position at close[t])
    turn = np.zeros(n)
    turn[1:] = np.abs(lev_pos[1:] - lev_pos[:-1])
    turn[0] = np.abs(lev_pos[0])
    fee = turn * fee_rate
    ret = gross - fee
    equity = np.cumprod(1.0 + ret)
    return dict(close=close, pos=pos, lev_pos=lev_pos, ret=ret, equity=equity,
                px_ret=px_ret, fee_total=fee.sum())


def trades_from_signals(close, sig):
    """Reconstruct closed trades. Returns list of dicts with entry/exit, pct, dollars, side."""
    close = np.asarray(close, dtype=float)
    trades = []
    nb = ns = 0
    entry_px = None
    entry_i = None
    side = 0
    for i, s in enumerate(sig):
        prev_net = nb - ns
        if s == "Buy":
            nb += 1
        elif s == "Sell":
            ns += 1
        net = nb - ns
        # opening
        if prev_net == 0 and net != 0 and s in ("Buy", "Sell"):
            entry_px = close[i]; entry_i = i; side = 1 if net > 0 else -1
        # closing (net returns to 0 via an actionable signal)
        elif prev_net != 0 and net == 0 and s in ("Buy", "Sell"):
            exit_px = close[i]
            if side == 1:
                pct = exit_px / entry_px - 1.0
                doll = exit_px - entry_px
            else:
                pct = entry_px / exit_px - 1.0
                doll = entry_px - exit_px
            trades.append(dict(entry_i=entry_i, exit_i=i, side=side,
                               entry=entry_px, exit=exit_px, pct=pct, dollars=doll,
                               bars=i - entry_i))
            entry_px = None; side = 0
            # could immediately re-open if same signal flips? In these strategies a
            # close brings net to 0 (flat); re-entry happens on a later row.
    return trades


def metrics(res, trades, dates=None):
    eq = res["equity"]
    ret = res["ret"]
    pos = res["pos"]
    n = len(eq)
    years = n / ANN
    total = eq[-1] - 1.0
    cagr = eq[-1] ** (1 / years) - 1.0 if years > 0 and eq[-1] > 0 else float("nan")
    vol = ret.std(ddof=1) * np.sqrt(ANN)
    sharpe = (ret.mean() * ANN) / (ret.std(ddof=1) * np.sqrt(ANN)) if ret.std() > 0 else float("nan")
    downside = ret[ret < 0].std(ddof=1) * np.sqrt(ANN) if (ret < 0).sum() > 1 else float("nan")
    sortino = (ret.mean() * ANN) / downside if downside and downside > 0 else float("nan")
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    maxdd = dd.min()
    calmar = cagr / abs(maxdd) if maxdd < 0 else float("nan")
    exposure = (pos != 0).mean()
    pcts = [t["pct"] for t in trades]
    winrate = np.mean([p > 0 for p in pcts]) if pcts else float("nan")
    avg_win = np.mean([p for p in pcts if p > 0]) if any(p > 0 for p in pcts) else float("nan")
    avg_loss = np.mean([p for p in pcts if p <= 0]) if any(p <= 0 for p in pcts) else float("nan")
    gross_win = sum(p for p in pcts if p > 0)
    gross_loss = -sum(p for p in pcts if p < 0)
    pf = gross_win / gross_loss if gross_loss > 0 else float("nan")
    dollars = sum(t["dollars"] for t in trades)
    return dict(total_return=total, cagr=cagr, vol=vol, sharpe=sharpe, sortino=sortino,
                maxdd=maxdd, calmar=calmar, exposure=exposure, n_trades=len(trades),
                winrate=winrate, avg_win=avg_win, avg_loss=avg_loss, profit_factor=pf,
                dollars_sum=dollars, final_equity=eq[-1])


def buyhold_metrics(close):
    close = np.asarray(close, float)
    ret = np.zeros(len(close)); ret[1:] = close[1:] / close[:-1] - 1.0
    eq = close / close[0]
    years = len(close) / ANN
    cagr = eq[-1] ** (1 / years) - 1.0
    sharpe = (ret.mean() * ANN) / (ret.std(ddof=1) * np.sqrt(ANN))
    peak = np.maximum.accumulate(eq); dd = eq / peak - 1.0
    return dict(total_return=eq[-1] - 1, cagr=cagr, sharpe=sharpe, maxdd=dd.min(),
                calmar=cagr / abs(dd.min()), final_equity=eq[-1])
