"""Make BOTH bear years green. 2022 already +5% (oil/energy/short-crypto). 2018 ~flat because trend-
following gets whipsawed in the choppy grind-down (BTC sleeve -8%). Fix tested here: go FLAT in
CHOP_HIVOL regimes (don't fight the chop) + keep the bear-winner assets (USD/energy/commod) in the pool.
Same engine, no look-ahead, no per-year tuning — the chop-flat rule applies in ALL years, not just 2018.
"""
import numpy as np, pandas as pd
import compare_m1m5 as cm, regime_system as rs, signals as sg, backtest as bt, live_engine as le
from global_engine import fetch_yahoo, UNIVERSE
ANN = 365
ALL = {k: v for k, v in UNIVERSE.items() if k != "ETH"}
ALL.update({"USD-UUP": ("UUP", "FX", 0.0006), "Energy-XLE": ("XLE", "Sector", 0.0006),
            "Commod-DBC": ("DBC", "Commod", 0.0010)})

def sleeve(df, slip, flat_chop=False):
    df = cm.prep(df); n = len(df); close = df["close"].to_numpy(); sma200 = df["SMA200"].to_numpy()
    sigs = sg.run_all(df, single_lookahead=False); memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
    reg, emap, exp_raw = le.ensemble_ctx(df, memb)
    rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
    expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
    e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy().copy()
    for i in range(n):
        if e_in[i] < 0 and not (reg[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]): e_in[i] = 0.0
        if flat_chop and reg[i] == "CHOP_HIVOL": e_in[i] = 0.0          # <-- the fix: don't trade the chop
    e_in = np.clip(e_in, -1, 1); held = 0.0; rnet = np.zeros(n); fee, band = 0.0005, 0.12
    for i in range(1, n):
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): continue
        e = e_in[i - 1] * min(1.0, 1.5 / rv[i - 1])
        if abs(e - held) < band and not (e == 0 and held != 0): e = held
        rnet[i] = e * (close[i] / close[i - 1] - 1) - abs(e - held) * (fee + slip); held = e
    return pd.Series(rnet, index=pd.to_datetime(df["Date"]))

def build(flat_chop):
    S = {k: sleeve(fetch_yahoo(tk), slip, flat_chop) for k, (tk, reg, slip) in ALL.items()}
    return pd.DataFrame(S).sort_index().loc["2017-01-01":].fillna(0.0)

def yret(r, y):
    seg = r[(r.index >= f"{y}-01-01") & (r.index < f"{y+1}-01-01")]; return (1 + seg).prod() - 1 if len(seg) > 20 else np.nan
def cagrdd(r):
    e = (1 + r).cumprod(); return e.iloc[-1] ** (1 / (len(r) / ANN)) - 1, (e / e.cummax() - 1).min(), e.iloc[-1]

R0 = build(False).mean(axis=1); R1 = build(True).mean(axis=1)
c0, d0, f0 = cagrdd(R0); c1, d1, f1 = cagrdd(R1)
print(f"{'year':>5} {'trade-chop':>11} {'FLAT-in-chop':>13}")
for y in range(2017, 2027):
    a, b = yret(R0, y), yret(R1, y)
    if np.isnan(a): continue
    star = "  <= bear yr" if y in (2018, 2022) else ""
    print(f"{y:>5} {a*100:>+10.0f}% {b*100:>+12.0f}%{star}")
print(f"\ntrade-chop : CAGR {c0*100:.0f}%  maxDD {d0*100:.0f}%  $500->${500*f0:,.0f}")
print(f"FLAT-chop  : CAGR {c1*100:.0f}%  maxDD {d1*100:.0f}%  $500->${500*f1:,.0f}")
