"""Validate the Python signal port against the Excel cached signals, on Excel's own data."""
import os
import pandas as pd
import indicators as ind
import signals as sg

path = os.path.join(os.path.dirname(__file__), "..", "data", "excel_indicators.csv")
raw = pd.read_csv(path)
raw = raw.rename(columns={"Close": "close", "Volumn": "volume"})
df = raw[["Date", "close", "volume"]].copy()
df = ind.compute(df).reset_index(drop=True)

sigs = sg.run_all(df, single_lookahead=True)

print(f"{'strategy':10s} {'match%':>8s} {'#mismatch':>10s}  {'pyBuy/pySell':>14s}  {'xlBuy/xlSell':>14s}")
for key, excel_col in sg.EXCEL_COL.items():
    py = pd.Series(sigs[key]).astype(str).str.strip()
    xl = raw[excel_col].astype(str).str.strip().replace("nan", "")
    # align length
    n = min(len(py), len(xl))
    py = py.iloc[:n].reset_index(drop=True)
    xl = xl.iloc[:n].reset_index(drop=True)
    # only compare rows where excel has a real (non-blank) signal
    mask = (xl != "") & (xl != "None") & (xl != "nan") & (py != "")
    eq = (py[mask] == xl[mask])
    matchpct = eq.mean() * 100
    nmis = (~eq).sum()
    pyb = (py[mask] == "Buy").sum(); pys = (py[mask] == "Sell").sum()
    xlb = (xl[mask] == "Buy").sum(); xls = (xl[mask] == "Sell").sum()
    print(f"{key:10s} {matchpct:>7.2f}% {nmis:>10d}  {str(pyb)+'/'+str(pys):>14s}  {str(xlb)+'/'+str(xls):>14s}")

# show first few mismatches for the worst strategy
print("\n--- sample mismatches (DSAM, MACD) ---")
for key in ["DSAM", "MACD"]:
    excel_col = sg.EXCEL_COL[key]
    py = pd.Series(sigs[key]).astype(str).str.strip()
    xl = raw[excel_col].astype(str).str.strip().replace("nan", "")
    n = min(len(py), len(xl)); py = py.iloc[:n]; xl = xl.iloc[:n]
    mask = (xl != "") & (xl != "None") & (xl != "nan") & (py != "") & (py != xl)
    idx = list(mask[mask].index[:8])
    print(f"[{key}] first mismatches at rows:", idx)
    for j in idx:
        print(f"   row{j} date={raw['Date'].iloc[j]} py={py.iloc[j]!r} xl={xl.iloc[j]!r}")
