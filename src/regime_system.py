"""Detailed market-type segmentation + which strategy wins in each regime.
Foundation for the single-strategy-at-a-time regime-switching engine.

Regimes (daily features: SMA50/200, ATR, BB width, RSI, slope):
  BULL_TREND     close>SMA50>SMA200, SMA50 rising, decent vol
  BULL_PULLBACK  uptrend (close>SMA200) but short-term dip (close<SMA20)
  RANGE_LOWVOL   flat SMA50, narrow bands, RSI 40-60
  CHOP_HIGHVOL   wide range / high ATR but no net trend (toxic)
  BEAR_TREND     close<SMA50<SMA200, SMA50 falling
  BEAR_BOUNCE    downtrend but short-term pop (close>SMA20)
"""
import os
import numpy as np
import pandas as pd
import indicators as ind
import signals as sg
import backtest as bt

HERE = os.path.dirname(__file__)
DATADIR = os.path.join(HERE, "..", "data")
MEMBERS = ["OBV", "DSAM", "MACD", "RSI", "EMA", "BB", "MFI", "OBV_ROC", "MACD_SIG"]
REGIMES = ["BULL_TREND", "BULL_PULLBACK", "RANGE_LOWVOL", "CHOP_HIGHVOL", "BEAR_TREND", "BEAR_BOUNCE"]


def load():
    raw = pd.read_csv(os.path.join(DATADIR, "btc_daily.csv"))
    df = ind.compute(raw[["date", "close", "volume", "high", "low", "open"]]
                     .rename(columns={"date": "Date"})).reset_index(drop=True)
    df["SMA50"] = df["close"].rolling(50).mean()
    df["SMA200"] = df["close"].rolling(200).mean()
    # ATR(14)
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()
    df["ATRpct"] = df["ATR"] / df["close"]
    df["bbw"] = (df["BB_Upper"] - df["BB_Lower"]) / df["SMA20"]
    df["slope50"] = df["SMA50"].pct_change(10)
    return df


def classify(df):
    n = len(df)
    reg = np.array(["NEUTRAL"] * n, dtype=object)
    c = df["close"].to_numpy(); s20 = df["SMA20"].to_numpy(); s50 = df["SMA50"].to_numpy()
    s200 = df["SMA200"].to_numpy(); slope = df["slope50"].to_numpy()
    atrp = df["ATRpct"].to_numpy(); rsi = df["RSI"].to_numpy()
    bbw = df["bbw"].to_numpy()
    atr_med = pd.Series(atrp).rolling(365, min_periods=60).median().to_numpy()
    bbw_med = pd.Series(bbw).rolling(365, min_periods=60).median().to_numpy()
    for i in range(n):
        if s200[i] != s200[i] or s50[i] != s50[i]:
            continue
        up = c[i] > s200[i]
        strong_up = c[i] > s50[i] > s200[i] and slope[i] > 0.01
        strong_dn = c[i] < s50[i] < s200[i] and slope[i] < -0.01
        highvol = atr_med[i] == atr_med[i] and atrp[i] > atr_med[i] * 1.25
        if strong_up:
            reg[i] = "BULL_PULLBACK" if c[i] < s20[i] else "BULL_TREND"
        elif strong_dn:
            reg[i] = "BEAR_BOUNCE" if c[i] > s20[i] else "BEAR_TREND"
        elif highvol:
            reg[i] = "CHOP_HIGHVOL"
        elif 38 <= rsi[i] <= 62 and (bbw_med[i] != bbw_med[i] or bbw[i] < bbw_med[i]):
            reg[i] = "RANGE_LOWVOL"
        else:
            reg[i] = "BULL_PULLBACK" if up else "BEAR_BOUNCE"
    return reg


def regime_strategy_table(df, reg):
    """For each strategy, annualized Sharpe & mean daily return of being in-position,
    conditioned on the regime of the PRIOR day (the day the position was decided)."""
    sigs = sg.run_all(df, single_lookahead=False)
    close = df["close"].to_numpy()
    pxret = np.zeros(len(df)); pxret[1:] = close[1:] / close[:-1] - 1
    reg_prev = np.roll(reg, 1)
    out = {}
    for k in MEMBERS:
        pos = bt.signals_to_position(sigs[k])
        held = np.roll(pos, 1)            # position decided yesterday earns today
        sret = held * pxret
        row = {}
        for rg in REGIMES:
            mask = reg_prev == rg
            r = sret[mask]
            if len(r) > 20 and r.std() > 0:
                sharpe = r.mean() * 365 / (r.std(ddof=1) * np.sqrt(365))
                row[rg] = (sharpe, r.mean() * 365, mask.sum(), (held[mask] != 0).mean())
            else:
                row[rg] = (float("nan"), float("nan"), int(mask.sum()), float("nan"))
        out[k] = row
    return out, sigs


def main():
    df = load()
    reg = classify(df)
    # regime distribution
    vc = pd.Series(reg).value_counts()
    print("=== MARKET-TYPE SEGMENTATION (daily, 2017-2026) ===")
    for rg in REGIMES + ["NEUTRAL"]:
        n = int(vc.get(rg, 0))
        print(f"  {rg:14s} {n:5d} days ({n/len(df)*100:4.1f}%)")
    tab, sigs = regime_strategy_table(df, reg)
    print("\n=== STRATEGY Sharpe BY REGIME (in-position, annualized) — best per regime in [] ===")
    print(f"{'strategy':10s}" + "".join(f"{rg[:11]:>13s}" for rg in REGIMES))
    for k in MEMBERS:
        line = f"{k:10s}"
        for rg in REGIMES:
            sh = tab[k][rg][0]
            line += f"{sh:>13.2f}" if sh == sh else f"{'-':>13s}"
        print(line)
    print("\n=== BEST STRATEGY per regime (by in-position Sharpe) ===")
    best = {}
    for rg in REGIMES:
        ranked = sorted(((k, tab[k][rg][0]) for k in MEMBERS if tab[k][rg][0] == tab[k][rg][0]),
                        key=lambda x: -x[1])
        best[rg] = ranked[:3]
        top = ", ".join(f"{k}({s:.2f})" for k, s in ranked[:3])
        print(f"  {rg:14s} -> {top}")
    return df, reg, tab, best


if __name__ == "__main__":
    main()
