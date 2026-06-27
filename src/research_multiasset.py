"""Different approach for more return: a BASKET of trend-followers (BTC/ETH/SOL/BNB), each run
through the SAME 1x vol-targeted ensemble, equal-weight blended (daily rebalance). Each sleeve is
positive-expectancy (unlike mean-reversion), and coins lead different bull runs, so the blend should
lift recent Sharpe and smooth drawdowns WITHOUT leverage. Honest: same rules for every asset, no
per-asset tuning; reported split by sub-period + cross-asset correlation. 1x, 50bp.
"""
import numpy as np, pandas as pd, bisect, datetime as dt, requests
import compare_m1m5 as cm, regime_system as rs, signals as sg, backtest as bt, live_engine as le
ANN = 365; BASE = "https://data-api.binance.vision"

def fetch_klines(sym, start="2017-01-01"):
    out = []; ms = int(pd.Timestamp(start).timestamp() * 1000)
    while True:
        a = requests.get(BASE + "/api/v3/klines", params={"symbol": sym, "interval": "1d",
                         "startTime": ms, "limit": 1000}, timeout=25).json()
        if not a: break
        out += a; ms = a[-1][0] + 86400000
        if len(a) < 1000: break
    rows = [(dt.datetime.utcfromtimestamp(x[0] / 1000).strftime("%Y-%m-%d"),
             float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])) for x in out]
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).drop_duplicates("date")

def sleeve(comb, slip=0.005):
    """Run one asset through the ensemble -> (dates, net daily strategy returns at 1x)."""
    df = cm.prep(comb); n = len(df); close = df["close"].to_numpy(); sma200 = df["SMA200"].to_numpy()
    sigs = sg.run_all(df, single_lookahead=False); memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
    reg, emap, exp_raw = le.ensemble_ctx(df, memb)
    rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
    expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
    e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy().copy()
    for i in range(n):
        if e_in[i] < 0 and not (reg[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]):
            e_in[i] = 0.0
    e_in = np.clip(e_in, -1, 1)
    held = 0.0; rnet = np.zeros(n); fee, band = 0.0005, 0.12
    for i in range(1, n):
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): rnet[i] = 0.0; continue
        e = e_in[i - 1] * min(1.0, 1.5 / rv[i - 1])
        if abs(e - held) < band and not (e == 0 and held != 0): e = held
        ret = close[i] / close[i - 1] - 1
        rnet[i] = e * ret - abs(e - held) * (fee + slip); held = e
    return df["Date"].tolist(), rnet

SYMS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "BNB": "BNBUSDT"}
ser = {}
for k, s in SYMS.items():
    d, r = sleeve(fetch_klines(s)); ser[k] = pd.Series(r, index=pd.to_datetime(d)); print(f"fetched {k}: {len(d)} days {d[0]}..{d[-1]}")
R = pd.DataFrame(ser).sort_index()                       # daily net strategy returns per asset

def stats(r, a, b):
    r = r.loc[a:b].dropna(); eq = (1 + r).cumprod(); yrs = len(r) / ANN
    cg = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    dd = (eq / eq.cummax() - 1).min(); sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    return cg, dd, sh, eq.iloc[-1]

A21, AEND = "2021-01-01", R.index[-1]; A17, B20 = "2017-09-01", "2021-01-01"
blendR = R.mean(axis=1)                                   # equal-weight, daily rebalance, only-available assets
print(f"\n{'system':18s} | {'17-20 CAGR':>10s} {'DD':>5s} {'Shrp':>5s} | {'21-26 CAGR':>10s} {'DD':>5s} {'Shrp':>5s} {'x500':>9s}")
print("-" * 86)
for name, r in [("BTC only", R["BTC"]), ("ETH only", R["ETH"]), ("SOL only", R["SOL"]),
                ("BNB only", R["BNB"]), ("EQUAL-WEIGHT BLEND", blendR)]:
    c1, d1, s1, _ = stats(r, A17, B20); c2, d2, s2, m2 = stats(r, A21, AEND)
    x500 = (1 + r.dropna()).prod() * 500
    print(f"{name:18s} | {c1*100:>+9.0f}% {d1*100:>4.0f}% {s1:>5.2f} | {c2*100:>+9.0f}% {d2*100:>4.0f}% {s2:>5.2f} ${x500:>8,.0f}")
c1, d1, s1, _ = stats(R[["BTC", "ETH", "SOL"]].mean(axis=1), A17, B20)
c2, d2, s2, _ = stats(R[["BTC", "ETH", "SOL"]].mean(axis=1), A21, AEND)
print(f"{'BLEND ex-BNB':18s} | {c1*100:>+9.0f}% {d1*100:>4.0f}% {s1:>5.2f} | {c2*100:>+9.0f}% {d2*100:>4.0f}% {s2:>5.2f}")
print("-" * 86)
print("recent cross-asset corr (strategy returns):")
print(R.loc[A21:].corr().round(2).to_string())

# STRESS: thin-alt slippage (alts less liquid than BTC) -> 120bp on alts, 50bp on BTC
print("\nSTRESS — 120bp slippage on alts (50bp BTC):")
serS = {"BTC": ser["BTC"]}
for k, s in [("ETH", "ETHUSDT"), ("SOL", "SOLUSDT"), ("BNB", "BNBUSDT")]:
    d, r = sleeve(fetch_klines(s), slip=0.012); serS[k] = pd.Series(r, index=pd.to_datetime(d))
RS = pd.DataFrame(serS).sort_index()
for name, r in [("BLEND (stressed)", RS.mean(axis=1)), ("BLEND ex-BNB (stressed)", RS[["BTC", "ETH", "SOL"]].mean(axis=1))]:
    c1, d1, s1, _ = stats(r, A17, B20); c2, d2, s2, _ = stats(r, A21, AEND)
    print(f"{name:24s} | 17-20 {c1*100:>+5.0f}% {d1*100:>4.0f}% {s1:.2f} | 21-26 {c2*100:>+5.0f}% {d2*100:>4.0f}% {s2:.2f}")
