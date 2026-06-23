"""Indicator definitions ported EXACTLY from working.xlsm 'Indicators' sheet.
Column letter map (Excel -> name):
 B Close, C Volume, D Single, E RSI, F SMA20, G SMA21, H EMA12, I EMA26,
 J EMA_fast, K EMA_slow, L MACD, M SignalLine, N BB_Upper, O BB_Lower,
 P MFI, Q OBV(vol-direction label), R ROC, S MACD_tailor, T Signalline_tailor
All series are pandas, indexed 0..n-1 (row i == Excel data row i+2).
NO look-ahead in any indicator (all use data up to current row).
"""
import numpy as np
import pandas as pd


def rsi_simple(close, n=14):
    # Excel: 100 - 100/(1 + avgGain_n / avgLoss_n), simple mean of last n diffs
    d = close.diff()
    gain = d.clip(lower=0)
    loss = (-d).clip(lower=0)
    ag = gain.rolling(n).mean()
    al = loss.rolling(n).mean()
    rs = ag / al
    out = 100 - 100 / (1 + rs)
    out[al == 0] = 100.0  # AVERAGE(loss)=0 -> IFERROR path -> very high; Excel gives ""/100
    return out


def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def ema_alpha(series, alpha):
    return series.ewm(alpha=alpha, adjust=False).mean()


def compute(df):
    """df needs columns: close, volume. Returns df with all indicator columns added."""
    c = df["close"].astype(float)
    v = df["volume"].astype(float)
    out = df.copy()
    out["RSI"] = rsi_simple(c, 14)                      # E
    out["SMA20"] = c.rolling(20).mean()                 # F
    out["SMA21"] = c.rolling(21).mean()                 # G
    out["EMA12"] = ema(c, 12)                           # H
    out["EMA26"] = ema(c, 26)                           # I
    out["EMA_fast"] = ema_alpha(c, 0.1538)              # J
    out["EMA_slow"] = ema_alpha(c, 0.0506)              # K
    out["MACD"] = out["EMA12"] - out["EMA26"]           # L
    out["SignalLine"] = ema(out["MACD"], 9)             # M
    sd = c.rolling(20).std(ddof=1)
    out["BB_Upper"] = out["SMA20"] + 2 * sd             # N
    out["BB_Lower"] = out["SMA20"] - 2 * sd             # O
    out["MFI"] = mfi_excel(c, v)                        # P
    out["OBV"] = vol_dir_label(v)                       # Q (mislabeled; = volume direction)
    out["ROC"] = roc(c, 13)                             # R
    out["MACD_tailor"] = c.rolling(14).mean() - c.rolling(20).mean()   # S
    out["Sig_tailor"] = out["MACD_tailor"].rolling(7).mean()           # T
    return out


def mfi_excel(close, volume):
    # Excel P at row t uses window B[t-14..t-1] vs B[t-15..t-2]: it EXCLUDES the
    # current row (lagged 1 day). So operate on close.shift(1)/volume.shift(1).
    c1 = close.shift(1)
    v1 = volume.shift(1)
    cp = c1.shift(1)
    up_mask = (c1 > cp).astype(float)
    dn_mask = (c1 < cp).astype(float)
    pv = c1 * v1
    up = (up_mask * pv).rolling(14).sum()
    dn = (dn_mask * pv).rolling(14).sum()
    out = 100 - (100 / (1 + up / dn))
    out[up == 0] = 100.0  # Excel: if up money flow sum==0 -> 100
    return out


def vol_dir_label(volume):
    # Excel Q: compare volume vs prior volume. |v/vp -1|<=0.1 -> HOLD; v>vp -> UP; else DOWN
    vp = volume.shift(1)
    ratio = (volume / vp - 1).abs()
    out = pd.Series(index=volume.index, dtype=object)
    out[:] = "DOWN"
    out[volume > vp] = "UP"
    out[ratio <= 0.1] = "HOLD"
    out[vp.isna()] = None
    return out


def roc(close, n=13):
    base = close.shift(n)
    return (close - base) / base * 100


# ---------------- verification against Excel cached values ----------------
def _verify():
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "data", "excel_indicators.csv")
    raw = pd.read_csv(path)
    raw = raw.rename(columns={"Close": "close", "Volumn": "volume"})
    df = raw[["Date", "close", "volume"]].copy()
    me = compute(df)
    checks = {
        "RSI": "RSI", "SMA20": "SMA20", "EMA12": "EMA12", "EMA26": "EMA26",
        "MACD": "MACD", "SignalLine": "SignalLine", "BB_Upper": "BB_Upper",
        "BB_Lower": "BB_Lower", "MFI": "MFI", "ROC": "ROC",
        "EMA_fast": "EMA_fast", "EMA_slow": "EMA_slow", "MACD_tailor": "MACD_tailor",
    }
    print(f"{'col':14s} {'maxAbsErr':>14s} {'meanAbsErr':>14s} {'~val':>12s}")
    for excel_col, my_col in checks.items():
        a = pd.to_numeric(raw[excel_col], errors="coerce")
        b = pd.to_numeric(me[my_col], errors="coerce")
        m = a.notna() & b.notna()
        # skip warmup first 60 rows
        m.iloc[:60] = False
        err = (a[m] - b[m]).abs()
        scale = a[m].abs().median()
        print(f"{excel_col:14s} {err.max():>14.4f} {err.mean():>14.6f} {scale:>12.2f}")
    # vol label match
    a = raw["OBV"].astype(str)
    b = me["OBV"].astype(str)
    m = (a != "nan") & (b != "None") & (b != "nan")
    m.iloc[:5] = False
    match = (a[m] == b[m]).mean()
    print(f"OBV(vol label) match rate: {match*100:.2f}%")


if __name__ == "__main__":
    _verify()
