"""Consolidate the 107 monthly 1-minute kline files into one compact store, and
re-derive the daily bars from the 1-min data so daily-close == intraday-close.

Handles the timestamp-unit change (ms in older files, microseconds in 2025+).
1-min files have NO volume; daily volume is merged from the existing API daily csv.
Outputs:
  data/intraday_1m.npz   day(int32 ordinal), o,h,l,c (float32), sorted by time
  data/btc_daily.csv     OHLC re-derived from 1m + volume merged from API daily
  data/funding.csv       normalized funding_time(ms)->date, rate
"""
import os, glob, csv
import numpy as np
import pandas as pd
import datetime as dt

HERE = os.path.dirname(__file__)
KDIR = os.path.join(HERE, "..", "data", "intraday", "klines")
FUND = os.path.join(HERE, "..", "data", "intraday", "funding", "BTCUSDT-funding.csv")
DATADIR = os.path.join(HERE, "..", "data")


def norm_ts_ms(arr):
    """Normalize a timestamp array to milliseconds. >=1e15 -> microseconds."""
    arr = arr.astype("int64")
    # ms ~1.5e12 (13 digits), us ~1.7e15 (16 digits)
    us_mask = arr >= 1_000_000_000_000_000  # 1e15
    arr = arr.copy()
    arr[us_mask] = arr[us_mask] // 1000
    return arr


def main():
    files = sorted(glob.glob(os.path.join(KDIR, "BTCUSDT-1m-*.csv")))
    print(f"reading {len(files)} monthly files...")
    days = []
    o = []; h = []; l = []; c = []
    tms_all = []
    for fn in files:
        df = pd.read_csv(fn)
        ts = norm_ts_ms(df["open_time"].to_numpy())
        tms_all.append(ts)
        o.append(df["open"].to_numpy(dtype="float32"))
        h.append(df["high"].to_numpy(dtype="float32"))
        l.append(df["low"].to_numpy(dtype="float32"))
        c.append(df["close"].to_numpy(dtype="float32"))
    tms = np.concatenate(tms_all)
    O = np.concatenate(o); H = np.concatenate(h); L = np.concatenate(l); C = np.concatenate(c)
    # sort by time, dedupe
    order = np.argsort(tms, kind="stable")
    tms, O, H, L, C = tms[order], O[order], H[order], L[order], C[order]
    uniq, idx = np.unique(tms, return_index=True)
    tms, O, H, L, C = tms[idx], O[idx], H[idx], L[idx], C[idx]
    # day ordinal (UTC)
    day_ord = (tms // 86_400_000).astype("int32")   # days since epoch
    minute = ((tms % 86_400_000) // 60_000).astype("int16")
    print(f"total 1-min bars: {len(tms):,}  span {ms_to_date(tms[0])} .. {ms_to_date(tms[-1])}")

    np.savez_compressed(os.path.join(DATADIR, "intraday_1m.npz"),
                        day=day_ord, minute=minute, o=O, h=H, l=L, c=C)
    print("saved intraday_1m.npz")

    # ---- daily bars from 1m ----
    dfm = pd.DataFrame({"day": day_ord, "o": O, "h": H, "l": L, "c": C})
    g = dfm.groupby("day")
    daily = pd.DataFrame({
        "open": g["o"].first(), "high": g["h"].max(),
        "low": g["l"].min(), "close": g["c"].last(),
    }).reset_index()
    daily["date"] = daily["day"].apply(lambda d: (dt.date(1970, 1, 1) + dt.timedelta(days=int(d))).isoformat())
    # merge volume from existing API daily
    api = pd.read_csv(os.path.join(DATADIR, "btc_daily.csv"))
    vol = api[["date", "volume"]]
    daily = daily.merge(vol, on="date", how="left")
    daily["volume"] = daily["volume"].fillna(0.0)
    daily = daily[["date", "open", "high", "low", "close", "volume"]]
    # sanity vs API close
    cmp = daily.merge(api[["date", "close"]].rename(columns={"close": "api_close"}), on="date", how="inner")
    err = (cmp["close"] - cmp["api_close"]).abs() / cmp["api_close"]
    print(f"daily close vs API: rows={len(cmp)}  median rel-err={err.median()*100:.4f}%  max={err.max()*100:.3f}%")
    daily.to_csv(os.path.join(DATADIR, "btc_daily.csv"), index=False)
    print(f"saved btc_daily.csv  {daily['date'].iloc[0]} .. {daily['date'].iloc[-1]}  ({len(daily)} days)")

    # ---- funding ----
    fdf = pd.read_csv(FUND)
    fdf["ms"] = norm_ts_ms(fdf["funding_time"].to_numpy())
    fdf["date"] = (fdf["ms"] // 86_400_000).apply(
        lambda d: (dt.date(1970, 1, 1) + dt.timedelta(days=int(d))).isoformat())
    # daily funding cost = sum of the (typically 3) 8h rates that day
    fday = fdf.groupby("date")["funding_rate"].sum().reset_index()
    fday.to_csv(os.path.join(DATADIR, "funding.csv"), index=False)
    print(f"saved funding.csv  {fday['date'].iloc[0]} .. {fday['date'].iloc[-1]}  "
          f"(avg daily {fday['funding_rate'].mean()*100:.4f}%)")


def ms_to_date(ms):
    return (dt.date(1970, 1, 1) + dt.timedelta(days=int(ms // 86_400_000))).isoformat()


if __name__ == "__main__":
    main()
