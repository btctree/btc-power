"""Validate the multi-asset basket HONESTLY before productizing:
 1) broader universe (14 coins incl. faded 2017-era names) -> not 4-coin luck,
 2) NON-PEEKING selection: each month pick top-N by TRAILING-90d dollar volume (known at the time),
    so illiquid/dying coins drop out without hindsight (survivorship-safe; you still eat losses held),
 3) tiered per-asset slippage (alts cost more),
 4) walk-forward: report 2017-20 (design era) vs 2021-26 (out-of-sample-ish) + yearly.
Cached to data/alt/ for repeatability. 1x, no leverage.
"""
import os, numpy as np, pandas as pd, datetime as dt, requests
import compare_m1m5 as cm, regime_system as rs, signals as sg, backtest as bt, live_engine as le
ANN = 365; BASE = "https://data-api.binance.vision"; CACHE = os.path.join(le.HERE, "..", "data", "alt")
os.makedirs(CACHE, exist_ok=True)
UNIVERSE = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "BNB": "BNBUSDT", "XRP": "XRPUSDT", "ADA": "ADAUSDT",
            "DOGE": "DOGEUSDT", "SOL": "SOLUSDT", "LTC": "LTCUSDT", "LINK": "LINKUSDT", "BCH": "BCHUSDT",
            "TRX": "TRXUSDT", "ETC": "ETCUSDT", "EOS": "EOSUSDT", "XLM": "XLMUSDT"}
TIER1 = {"BTC", "ETH"}; TIER2 = {"BNB", "XRP", "ADA", "DOGE", "SOL", "LTC"}
def slip_for(k): return 0.005 if k in TIER1 else (0.008 if k in TIER2 else 0.012)

def fetch_klines(sym):
    fp = os.path.join(CACHE, sym + ".csv")
    if os.path.exists(fp): return pd.read_csv(fp)
    out = []; ms = int(pd.Timestamp("2017-01-01").timestamp() * 1000)
    while True:
        a = requests.get(BASE + "/api/v3/klines", params={"symbol": sym, "interval": "1d", "startTime": ms, "limit": 1000}, timeout=25).json()
        if not a: break
        out += a; ms = a[-1][0] + 86400000
        if len(a) < 1000: break
    rows = [(dt.datetime.fromtimestamp(x[0] / 1000, dt.timezone.utc).strftime("%Y-%m-%d"),
             float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])) for x in out]
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).drop_duplicates("date")
    df.to_csv(fp, index=False); return df

def sleeve(comb, slip):
    df = cm.prep(comb); n = len(df); close = df["close"].to_numpy(); sma200 = df["SMA200"].to_numpy()
    sigs = sg.run_all(df, single_lookahead=False); memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
    reg, emap, exp_raw = le.ensemble_ctx(df, memb)
    rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
    expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
    e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy().copy()
    for i in range(n):
        if e_in[i] < 0 and not (reg[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]): e_in[i] = 0.0
    e_in = np.clip(e_in, -1, 1); held = 0.0; rnet = np.zeros(n); fee, band = 0.0005, 0.12
    for i in range(1, n):
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): continue
        e = e_in[i - 1] * min(1.0, 1.5 / rv[i - 1])
        if abs(e - held) < band and not (e == 0 and held != 0): e = held
        rnet[i] = e * (close[i] / close[i - 1] - 1) - abs(e - held) * (fee + slip); held = e
    dvol = (df["close"] * df["volume"]).to_numpy()
    return df["Date"].tolist(), rnet, dvol

Rd, Vd = {}, {}
for k, s in UNIVERSE.items():
    try:
        d, r, v = sleeve(fetch_klines(s), slip_for(k)); Rd[k] = pd.Series(r, index=pd.to_datetime(d)); Vd[k] = pd.Series(v, index=pd.to_datetime(d))
    except Exception as e:
        print("skip", k, repr(e)[:60])
R = pd.DataFrame(Rd).sort_index(); V = pd.DataFrame(Vd).sort_index()
print(f"universe: {list(R.columns)}  ({R.shape[0]} days)")

def topn_weights(N):
    liq = V.rolling(90, min_periods=30).median().shift(1)          # trailing liquidity, known yesterday
    W = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for m, idx in R.groupby(R.index.to_period("M")).groups.items():
        d0 = idx[0]; row = liq.loc[d0].dropna()
        sel = row[row > 0].nlargest(N).index
        if len(sel): W.loc[idx, sel] = 1.0 / len(sel)
    return W

def stats(r, a, b):
    r = r.loc[a:b].dropna()
    if len(r) < 50: return (float('nan'),) * 3
    eq = (1 + r).cumprod(); yrs = len(r) / ANN
    cg = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    dd = (eq / eq.cummax() - 1).min(); sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float('nan')
    return cg, dd, sh

A17, B20, A21, AEND = "2017-09-01", "2021-01-01", "2021-01-01", R.index[-1]
syss = [("BTC only", R["BTC"]), ("equal-weight ALL", R.mean(axis=1)),
        ("top-6 by liquidity", (R * topn_weights(6)).sum(axis=1)),
        ("top-4 by liquidity", (R * topn_weights(4)).sum(axis=1)),
        ("top-8 by liquidity", (R * topn_weights(8)).sum(axis=1))]
hdr = f"{'system':22s} | {'17-20 CAGR':>10s} {'DD':>5s} {'Shrp':>5s} | {'21-26 CAGR':>10s} {'DD':>5s} {'Shrp':>5s}"
print(hdr); print("-" * len(hdr))
for name, r in syss:
    c1, d1, s1 = stats(r, A17, B20); c2, d2, s2 = stats(r, A21, AEND)
    print(f"{name:22s} | {c1*100:>+9.0f}% {d1*100:>4.0f}% {s1:>5.2f} | {c2*100:>+9.0f}% {d2*100:>4.0f}% {s2:>5.2f}")
print("-" * len(hdr))
# yearly Sharpe of the top-6 vs BTC (walk-forward read)
t6 = (R * topn_weights(6)).sum(axis=1)
print("\nyear-by-year Sharpe (top-6 / BTC-only):")
for y in range(2018, 2026):
    a, b = f"{y}-01-01", f"{y+1}-01-01"
    _, _, s6 = stats(t6, a, b); _, _, sb = stats(R["BTC"], a, b)
    print(f"  {y}:  top6 {s6:>5.2f}   BTC {sb:>5.2f}")
