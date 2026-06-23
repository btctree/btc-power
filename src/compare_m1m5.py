"""Apples-to-apples: run OUR trend-ride strategy on the SAME long history the
M1-vs-M5 system used (CoinGecko daily pre-2017-08 + Binance after), so the only
difference vs M1vM5 is the strategy, not the data window.

Pre-2017 has no intraday OHLC (CoinGecko close-only) — same limitation M1vM5 had —
so stops there are close-based. 2017-08+ uses real Binance high/low.
"""
import os
import numpy as np
import pandas as pd
import indicators as ind
import signals as sg
import backtest as bt
import regime_system as rs
import fast_search as fsearch

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")


def build_combined():
    cg = pd.read_csv(os.path.join(DATA, "excel_indicators.csv"))[["Date", "Close", "Volumn"]]
    cg = cg.rename(columns={"Date": "date", "Close": "close", "Volumn": "volume"})
    cg["date"] = pd.to_datetime(cg["date"]).dt.strftime("%Y-%m-%d")
    cg = cg[cg["date"] < "2017-08-17"].copy()
    cg["open"] = cg["close"]; cg["high"] = cg["close"]; cg["low"] = cg["close"]
    cg["volume"] = cg["volume"].fillna(0.0)
    bn = pd.read_csv(os.path.join(DATA, "btc_daily.csv"))      # Binance, real OHLC
    comb = pd.concat([cg[["date", "open", "high", "low", "close", "volume"]], bn], ignore_index=True)
    comb = comb.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    return comb


def prep(comb):
    df = ind.compute(comb[["date", "close", "volume", "high", "low", "open"]]
                     .rename(columns={"date": "Date"})).reset_index(drop=True)
    df["SMA50"] = df["close"].rolling(50).mean()
    df["SMA200"] = df["close"].rolling(200).mean()
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean(); df["ATRpct"] = df["ATR"] / df["close"]
    df["bbw"] = (df["BB_Upper"] - df["BB_Lower"]) / df["SMA20"]
    df["slope50"] = df["SMA50"].pct_change(10)
    return df


def run_from(df, start_date, label):
    reg = rs.classify(df)
    sigs = sg.run_all(df, single_lookahead=False)
    memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
    fsearch._C = dict(close=df["close"].to_numpy(), high=df["high"].to_numpy(),
                      low=df["low"].to_numpy(), reg=reg, memb=memb,
                      fundarr=np.zeros(len(df)), dates=df["Date"].tolist())
    ref = {(r, 1): (1.0, 1, 0.10) for r in fsearch.LONG_REGIMES}
    ref[("CHOP_HIGHVOL", -1)] = (0.5, 1, 0.07); ref[("BEAR_TREND", -1)] = (0.5, 1, 0.07)
    i0 = next(i for i, d in enumerate(df["Date"]) if d >= start_date)
    eq, liq = fsearch.fast_sim(ref, max(i0, 260), len(df), start=500.0)
    m = fsearch.metrics(eq)
    yrs = len(eq) / 365
    print(f"{label:34s} ${m['final']:>11,.0f}  ({m['final']/500:>7.0f}x)  CAGR {m['cagr']*100:>5.1f}%  "
          f"Sharpe {m['sharpe']:.2f}  maxDD {m['maxdd']*100:.0f}%  liq {liq}  [{df['Date'].iloc[max(i0,260)]}→, {yrs:.1f}y]")
    return m


def main():
    comb = build_combined()
    df = prep(comb)
    print(f"combined history: {df['Date'].iloc[0]} → {df['Date'].iloc[-1]}  ({len(df)} days)")
    print("OUR trend-ride strategy, SPOT 1x, on the SAME data window M1vM5 used:\n")
    run_from(df, "2014-01-01", "OURS from 2014 (M1vM5 window)")
    run_from(df, "2017-08-17", "OURS from 2017-08 (Binance only)")
    print("\nM1-vs-M5 reference (their reported numbers):")
    print(f"{'M1vM5 from 2014 (gross, no fees)':34s} ${223000:>11,.0f}  ({447:>7}x)   <- their headline")
    print(f"{'M1vM5 from 2017-08 (in-window)':34s} ${500*75.8:>11,.0f}  ({76:>7}x)   gross")
    print("\n$80M target reference: needs 231%/yr — neither system is within ~300x of it.")


if __name__ == "__main__":
    main()
