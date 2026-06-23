"""Build & evaluate ensemble signals from the robust strategy subset.
Ensemble position = mean of member positions (continuous in [-1,1]); the magnitude
doubles as a confidence/size score (framework: confidence sizes the bet).
Picks the best variant by walk-forward robustness, then emits the live signal.
"""
import os, json
import numpy as np
import pandas as pd
import indicators as ind
import signals as sg
import backtest as bt

HERE = os.path.dirname(__file__)
ANN = 365


def load_binance():
    raw = pd.read_csv(os.path.join(HERE, "..", "data", "btc_daily.csv"))
    df = ind.compute(raw[["date", "close", "volume"]].rename(columns={"date": "Date"})).reset_index(drop=True)
    return df


def member_positions(df, single_lookahead=False):
    sigs = sg.run_all(df, single_lookahead=single_lookahead)
    return {k: bt.signals_to_position(sigs[k]) for k in sigs}, sigs


def bt_position(close, pos, fee_rate=0.0005, long_only=False):
    """Backtest an arbitrary (possibly fractional) position series, no look-ahead."""
    close = np.asarray(close, float)
    pos = np.asarray(pos, float)
    if long_only:
        pos = np.clip(pos, 0, None)
    n = len(close)
    px = np.zeros(n); px[1:] = close[1:] / close[:-1] - 1
    held = np.zeros(n); held[1:] = pos[:-1]
    gross = held * px
    turn = np.zeros(n); turn[1:] = np.abs(pos[1:] - pos[:-1]); turn[0] = abs(pos[0])
    ret = gross - turn * fee_rate
    eq = np.cumprod(1 + ret)
    return ret, eq, pos


def quick_metrics(ret, eq, pos):
    years = len(eq) / ANN
    cagr = eq[-1] ** (1 / years) - 1 if eq[-1] > 0 else float("nan")
    sharpe = ret.mean() * ANN / (ret.std(ddof=1) * np.sqrt(ANN)) if ret.std() > 0 else float("nan")
    peak = np.maximum.accumulate(eq); dd = (eq / peak - 1)
    maxdd = dd.min()
    calmar = cagr / abs(maxdd) if maxdd < 0 else float("nan")
    down = ret[ret < 0].std(ddof=1) * np.sqrt(ANN)
    sortino = ret.mean() * ANN / down if down > 0 else float("nan")
    return dict(total=eq[-1] - 1, cagr=cagr, sharpe=sharpe, sortino=sortino,
                maxdd=maxdd, calmar=calmar, exposure=(np.abs(pos) > 1e-9).mean(),
                final=eq[-1])


# subsets to test
SUBSETS = {
    "all9": ["OBV", "DSAM", "MACD", "RSI", "EMA", "BB", "MFI", "OBV_ROC", "MACD_SIG"],
    "robust3": ["MACD", "MACD_SIG", "MFI"],
    "robust4": ["MACD", "MACD_SIG", "MFI", "EMA"],
    "robust5": ["MACD", "MACD_SIG", "MFI", "EMA", "DSAM"],
}


def ensemble_pos(memb, keys):
    arrs = [memb[k] for k in keys]
    return np.mean(arrs, axis=0)


def evaluate_all():
    df = load_binance()
    close = df["close"].to_numpy()
    memb, sigs = member_positions(df, single_lookahead=False)  # honest DSAM
    mid = len(df) // 2

    print("=== ENSEMBLE VARIANTS (Binance daily, honest, 5bp/side) ===")
    print(f"{'variant':18s} {'tot':>9s} {'CAGR':>7s} {'Shrp':>5s} {'Sort':>5s} {'maxDD':>7s} "
          f"{'Calm':>5s} {'expo':>5s} | {'H1Shrp':>6s} {'H2Shrp':>6s} {'H2Calm':>6s}")
    results = {}
    for name, keys in SUBSETS.items():
        for mode, lo in [("L/S", False), ("Lcap", "longbias")]:
            pos = ensemble_pos(memb, keys)
            longonly = False
            if lo == "longbias":
                pos = np.where(pos < 0, pos * 0.0, pos)  # long-only ensemble
                longonly = False  # already clipped
            ret, eq, p = bt_position(close, pos, long_only=False)
            m = quick_metrics(ret, eq, p)
            # halves
            r1, e1, p1 = bt_position(close[:mid], pos[:mid])
            r2, e2, p2 = bt_position(close[mid:], pos[mid:])
            m1 = quick_metrics(r1, e1, p1); m2 = quick_metrics(r2, e2, p2)
            tag = f"{name}-{mode}"
            results[tag] = (pos, m, m1, m2)
            print(f"{tag:18s} {m['total']*100:>8.0f}% {m['cagr']*100:>6.1f}% {m['sharpe']:>5.2f} "
                  f"{m['sortino']:>5.2f} {m['maxdd']*100:>6.1f}% {m['calmar']:>5.2f} "
                  f"{m['exposure']*100:>4.0f}% | {m1['sharpe']:>6.2f} {m2['sharpe']:>6.2f} {m2['calmar']:>6.2f}")
    bh = bt.buyhold_metrics(close)
    print(f"\nBUY&HOLD            {bh['total_return']*100:>8.0f}% {bh['cagr']*100:>6.1f}% "
          f"{bh['sharpe']:>5.2f}    -  {bh['maxdd']*100:>6.1f}% {bh['calmar']:>5.2f}")
    return df, memb, sigs, results, bh


if __name__ == "__main__":
    evaluate_all()
