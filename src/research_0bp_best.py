"""Best model under ZERO slippage/fees, judged on your constraints: strong return + Calmar + Sharpe,
200+ trades, NO big drawdown, NO liquidation, ALL years profitable. Scans BTC-only + global universe,
equal-weight blend and BTC-concentrated, across leverage. Honest: 0 cost as requested (borrow on
leverage still applies, it's not slippage); daily liquidation check (lev x daily loss <= -100%).
"""
import numpy as np, pandas as pd
import compare_m1m5 as cm, regime_system as rs, signals as sg, backtest as bt, live_engine as le
from global_engine import fetch_yahoo, UNIVERSE
ANN = 365
U = {k: v for k, v in UNIVERSE.items() if k != "ETH"}

def sleeve0(df):
    df = cm.prep(df); n = len(df); close = df["close"].to_numpy(); sma200 = df["SMA200"].to_numpy()
    sigs = sg.run_all(df, single_lookahead=False); memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
    reg, emap, exp_raw = le.ensemble_ctx(df, memb)
    rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
    expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
    e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy().copy()
    for i in range(n):
        if e_in[i] < 0 and not (reg[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]): e_in[i] = 0.0
    e_in = np.clip(e_in, -1, 1); held = 0.0; rnet = np.zeros(n); E = np.zeros(n); band = 0.12; tr = 0
    for i in range(1, n):
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): E[i] = held; continue
        e = e_in[i - 1] * min(1.0, 1.5 / rv[i - 1])
        if abs(e - held) < band and not (e == 0 and held != 0): e = held
        if np.sign(e) != np.sign(held): tr += 1
        rnet[i] = e * (close[i] / close[i - 1] - 1)                 # NO cost (0 slippage/fee)
        held = e; E[i] = e
    return pd.Series(rnet, index=pd.to_datetime(df["Date"])), tr

S, TR = {}, {}
for k, (tk, reg, slip) in U.items():
    S[k], TR[k] = sleeve0(fetch_yahoo(tk))
R = pd.DataFrame(S).sort_index().loc["2017-01-01":].fillna(0.0); yrs = len(R) / ANN
tot_trades = sum(TR.values())

def metr(r, L, borrow=0.06):
    d = L * r - (L - 1) * borrow / ANN
    liq = int((d <= -1.0).sum())                                    # leverage wipeout day
    e = 1.0; arr = []
    for x in d:
        e = max(e * (1 + x), 1e-12); arr.append(e)
    s = pd.Series(arr, index=r.index); c = s.iloc[-1] ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1
    dd = (s / s.cummax() - 1).min(); sh = d.mean() * ANN / (d.std(ddof=1) * np.sqrt(ANN)) if d.std() > 0 else float("nan")
    posyr = sum(1 for y in range(2017, 2027)
                if len(d[(d.index >= f"{y}-01-01") & (d.index < f"{y+1}-01-01")]) > 20
                and (1 + d[(d.index >= f"{y}-01-01") & (d.index < f"{y+1}-01-01")]).prod() > 1)
    ny = sum(1 for y in range(2017, 2027) if len(d[(d.index >= f"{y}-01-01") & (d.index < f"{y+1}-01-01")]) > 20)
    return dict(cagr=c, dd=dd, sharpe=sh, calmar=c / abs(dd) if dd < 0 else 0, final=500 * s.iloc[-1], liq=liq, pos=posyr, ny=ny)

blend = R.mean(axis=1); btc = R["BTC"]
print(f"total trades (all products, 0bp): {tot_trades}\n")
print(f"{'config':22s} {'lev':>4} {'CAGR':>6} {'maxDD':>6} {'Calmar':>6} {'Sharpe':>6} {'posYr':>6} {'liq':>4} {'$500->':>11}")
rows = []
for name, r in [("All-weather blend", blend), ("BTC only", btc)]:
    for L in [1.0, 1.5, 2.0, 3.0]:
        m = metr(r, L); rows.append((name, L, m))
        flag = ""
        if m["dd"] > -0.25 and m["liq"] == 0 and m["pos"] == m["ny"]: flag = "  <- no big DD, 0 liq, all yrs +"
        print(f"{name:22s} {L:>3.1f}x {m['cagr']*100:>+5.0f}% {m['dd']*100:>5.0f}% {m['calmar']:>6.2f} {m['sharpe']:>6.2f} {m['pos']:>3}/{m['ny']:<2} {m['liq']:>4} ${m['final']:>10,.0f}{flag}")
# pick best Calmar among all-years-profit + no-liq + DD<25%
ok = [(n, L, m) for n, L, m in rows if m["dd"] > -0.25 and m["liq"] == 0 and m["pos"] == m["ny"]]
if ok:
    bc = max(ok, key=lambda x: x[2]["calmar"]); bs = max(ok, key=lambda x: x[2]["sharpe"]); br = max(ok, key=lambda x: x[2]["cagr"])
    print(f"\nBest CALMAR (no big DD/0 liq/all yrs+): {bc[0]} {bc[1]}x -> Calmar {bc[2]['calmar']:.2f}, CAGR {bc[2]['cagr']*100:.0f}%, DD {bc[2]['dd']*100:.0f}%, Sharpe {bc[2]['sharpe']:.2f}")
    print(f"Best SHARPE: {bs[0]} {bs[1]}x -> Sharpe {bs[2]['sharpe']:.2f}")
    print(f"Highest RETURN within constraints: {br[0]} {br[1]}x -> CAGR {br[2]['cagr']*100:.0f}%, DD {br[2]['dd']*100:.0f}%, $500->${br[2]['final']:,.0f}")
