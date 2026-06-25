"""Finer market-type taxonomy (v2): trend strength (Wilder ADX) x direction x volatility,
with hysteresis. Each cell is only worth keeping if it SEPARATES out-of-sample edge —
this module both classifies and reports per-cell edge so we can merge non-separating cells.

Cells:
  STRONG_UP    ADX>=adx_hi, +DI>-DI                 (ride hard)
  TREND_UP     adx_lo<=ADX<adx_hi, up               (trend)
  PULLBACK_UP  up-trend context but close<SMA20     (dip-buy)
  STRONG_DOWN  ADX>=adx_hi, -DI>+DI
  TREND_DOWN   adx_lo<=ADX<adx_hi, down
  BOUNCE_DOWN  down-trend context but close>SMA20
  CHOP_HIVOL   ADX<adx_lo and ATR% high             (toxic)
  RANGE        ADX<adx_lo and ATR% normal/low       (mean-revert / aside)
"""
import os
import numpy as np
import pandas as pd
import indicators as ind

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
CELLS = ["STRONG_UP", "TREND_UP", "PULLBACK_UP", "STRONG_DOWN", "TREND_DOWN",
         "BOUNCE_DOWN", "CHOP_HIVOL", "RANGE"]


def wilder_adx(high, low, close, n=14):
    up = high.diff(); dn = -low.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus_dm, index=high.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus_dm, index=high.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / n, adjust=False).mean()
    return adx, pdi, mdi


def load():
    raw = pd.read_csv(os.path.join(DATA, "btc_daily.csv"))
    df = ind.compute(raw[["date", "close", "volume", "high", "low", "open"]]
                     .rename(columns={"date": "Date"})).reset_index(drop=True)
    df["SMA50"] = df["close"].rolling(50).mean()
    df["SMA200"] = df["close"].rolling(200).mean()
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["ATRpct"] = tr.rolling(14).mean() / df["close"]
    df["ADX"], df["PDI"], df["MDI"] = wilder_adx(h, l, c, 14)
    return df


def classify(df, adx_lo=20.0, adx_hi=35.0, hysteresis=2):
    n = len(df)
    c = df["close"].to_numpy(); s20 = df["SMA20"].to_numpy(); s200 = df["SMA200"].to_numpy()
    adx = df["ADX"].to_numpy(); pdi = df["PDI"].to_numpy(); mdi = df["MDI"].to_numpy()
    atr = df["ATRpct"].to_numpy()
    atr_med = pd.Series(atr).rolling(365, min_periods=60).median().to_numpy()
    raw = np.array(["RANGE"] * n, dtype=object)
    for i in range(n):
        if s200[i] != s200[i] or adx[i] != adx[i]:
            raw[i] = "WARMUP"; continue
        up = pdi[i] >= mdi[i]; hivol = atr_med[i] == atr_med[i] and atr[i] > atr_med[i] * 1.2
        if adx[i] >= adx_hi:
            raw[i] = "STRONG_UP" if up else "STRONG_DOWN"
        elif adx[i] >= adx_lo:
            if up:
                raw[i] = "PULLBACK_UP" if c[i] < s20[i] else "TREND_UP"
            else:
                raw[i] = "BOUNCE_DOWN" if c[i] > s20[i] else "TREND_DOWN"
        else:
            raw[i] = "CHOP_HIVOL" if hivol else "RANGE"
    # hysteresis: switch to a new label only after `hysteresis` consecutive days of it
    out = raw.copy(); cur = None; cand = None; crun = 0
    for i in range(n):
        r = raw[i]
        if r == "WARMUP":
            cur = "WARMUP"; cand = None; crun = 0; out[i] = "WARMUP"; continue
        if r == cand:
            crun += 1
        else:
            cand = r; crun = 1
        if cur is None or cur == "WARMUP" or crun >= hysteresis:
            cur = cand
        out[i] = cur
    return out


def edge_table(df, reg):
    """Per-cell, per-strategy in-position out-of-sample Sharpe (2nd-half), to see which
    cells separate edge."""
    import signals as sg, backtest as bt
    sigs = sg.run_all(df, single_lookahead=False)
    close = df["close"].to_numpy(); px = np.zeros(len(df)); px[1:] = close[1:] / close[:-1] - 1
    rprev = np.roll(reg, 1)
    mid = len(df) // 2
    members = list(sg.EXCEL_COL.keys())
    print(f"{'cell':12s} {'days':>5s}  best engine (2nd-half in-pos Sharpe)")
    for cell in CELLS:
        mask = (rprev == cell)
        mask2 = mask.copy(); mask2[:mid] = False
        best = []
        for k in members:
            pos = bt.signals_to_position(sigs[k]); held = np.roll(pos, 1)
            r = (held * px)[mask2]
            if len(r) > 15 and r.std() > 0:
                best.append((k, r.mean() * 365 / (r.std(ddof=1) * np.sqrt(365))))
        best.sort(key=lambda x: -x[1])
        top = ", ".join(f"{k}({s:.2f})" for k, s in best[:3]) if best else "(thin)"
        print(f"{cell:12s} {int(mask.sum()):>5d}  {top}")


if __name__ == "__main__":
    df = load(); reg = classify(df)
    vc = pd.Series(reg).value_counts()
    print("=== regime_v2 distribution ===")
    for cell in CELLS + ["WARMUP"]:
        nseg = int(vc.get(cell, 0)); print(f"  {cell:12s} {nseg:5d} ({nseg/len(df)*100:4.1f}%)")
    print("\n=== edge separation (2nd-half) ===")
    edge_table(df, reg)
