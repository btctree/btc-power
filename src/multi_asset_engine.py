"""MULTI-ASSET engine -> out/results_multi.json. A diversified majors trend-basket (validated in
research_validate.py: ~2x BTC's risk-adjusted return at HALF the drawdown, robust across eras).
Each coin runs through the SAME 1x vol-targeted ensemble; the portfolio blends them two ways:
  - "Basket top-8"   : monthly pick the 8 most-liquid majors by TRAILING dollar volume (no hindsight)
  - "Basket equal-wt": equal weight across the whole majors universe
Plus "BTC 1x" as the conservative sub-option. No leverage. Tiered per-asset slippage.
Output schema feeds a multi-asset dashboard (scenarios chart + per-asset holdings table).
"""
import os, json, datetime as dt, numpy as np, pandas as pd, requests
import compare_m1m5 as cm, regime_system as rs, signals as sg, backtest as bt, live_engine as le
ANN = 365; BASE = "https://data-api.binance.vision"; OUT = le.OUT
CACHE = os.path.join(le.HERE, "..", "data", "alt"); os.makedirs(CACHE, exist_ok=True)
UNIVERSE = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "BNB": "BNBUSDT", "XRP": "XRPUSDT", "ADA": "ADAUSDT",
            "DOGE": "DOGEUSDT", "SOL": "SOLUSDT", "LTC": "LTCUSDT", "LINK": "LINKUSDT", "BCH": "BCHUSDT",
            "TRX": "TRXUSDT", "ETC": "ETCUSDT", "EOS": "EOSUSDT", "XLM": "XLMUSDT"}
TIER1 = {"BTC", "ETH"}; TIER2 = {"BNB", "XRP", "ADA", "DOGE", "SOL", "LTC"}
def slip_for(k): return 0.005 if k in TIER1 else (0.008 if k in TIER2 else 0.012)


def fetch_klines(sym, refresh_last=True):
    fp = os.path.join(CACHE, sym + ".csv")
    if os.path.exists(fp) and not refresh_last:
        return pd.read_csv(fp)
    out = []; ms = int(pd.Timestamp("2017-01-01").timestamp() * 1000)
    try:
        while True:
            a = requests.get(BASE + "/api/v3/klines", params={"symbol": sym, "interval": "1d", "startTime": ms, "limit": 1000}, timeout=25).json()
            if not a: break
            out += a; ms = a[-1][0] + 86400000
            if len(a) < 1000: break
        rows = [(dt.datetime.fromtimestamp(x[0] / 1000, dt.timezone.utc).strftime("%Y-%m-%d"),
                 float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])) for x in out]
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).drop_duplicates("date")
        df.to_csv(fp, index=False); return df
    except Exception as e:
        if os.path.exists(fp):
            print(f"[multi] {sym} fetch failed ({repr(e)[:40]}); using cache"); return pd.read_csv(fp)
        raise


def sleeve(comb, slip):
    """One asset through the ensemble -> dict(dates, rnet daily, e path, close, reg, regimes)."""
    df = cm.prep(comb); n = len(df); close = df["close"].to_numpy(); sma200 = df["SMA200"].to_numpy()
    sigs = sg.run_all(df, single_lookahead=False); memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
    reg, emap, exp_raw = le.ensemble_ctx(df, memb)
    rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
    expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
    e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy().copy()
    for i in range(n):
        if e_in[i] < 0 and not (reg[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]): e_in[i] = 0.0
    e_in = np.clip(e_in, -1, 1); held = 0.0; rnet = np.zeros(n); E = np.zeros(n); fee, band = 0.0005, 0.12
    for i in range(1, n):
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): E[i] = held; continue
        e = e_in[i - 1] * min(1.0, 1.5 / rv[i - 1])
        if abs(e - held) < band and not (e == 0 and held != 0): e = held
        rnet[i] = e * (close[i] / close[i - 1] - 1) - abs(e - held) * (fee + slip); held = e; E[i] = e
    return dict(dates=df["Date"].tolist(), rnet=rnet, E=E, close=close,
                dvol=(df["close"] * df["volume"]).to_numpy(), reg=reg)


def metrics(eq):
    eq = np.asarray(eq, float); s = pd.Series(eq); r = s.pct_change().dropna(); yrs = len(eq) / ANN
    final = float(eq[-1]); cagr = (final / eq[0]) ** (1 / yrs) - 1 if final > 0 else -1
    dd = float((s / s.cummax() - 1).min()); sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    return dict(final=round(final, 2), cagr=round(float(cagr), 4), sharpe=round(float(sh), 4),
                maxdd=round(dd, 4), calmar=round(float(cagr / abs(dd)) if dd < 0 else 0, 4))


def main(save_as="results_multi.json"):
    S = {}
    for k, s in UNIVERSE.items():
        try:
            S[k] = sleeve(fetch_klines(s), slip_for(k)); print(f"  {k:4s} {len(S[k]['dates'])}d")
        except Exception as e:
            print("  skip", k, repr(e)[:50])
    R = pd.DataFrame({k: pd.Series(v["rnet"], index=pd.to_datetime(v["dates"])) for k, v in S.items()}).sort_index()
    V = pd.DataFrame({k: pd.Series(v["dvol"], index=pd.to_datetime(v["dates"])) for k, v in S.items()}).sort_index()
    idx = R.index; dates = [d.strftime("%Y-%m-%d") for d in idx]
    # top-N (monthly, trailing-90d liquidity, no peeking)
    N = 8; liq = V.rolling(90, min_periods=30).median().shift(1)
    W = pd.DataFrame(0.0, index=idx, columns=R.columns)
    for m, g in R.groupby(idx.to_period("M")).groups.items():
        row = liq.loc[g[0]].dropna(); sel = row[row > 0].nlargest(N).index
        if len(sel): W.loc[g, sel] = 1.0 / len(sel)
    r_top = (R * W).sum(axis=1)
    r_eq = R.mean(axis=1)
    r_btc = R["BTC"]
    def curve(r): return (1 + r.fillna(0)).cumprod() * 500.0
    i0 = 260  # warm-up parity with single-asset engine
    scen = {}
    for name, r, desc in [("Basket top-8", r_top, "8 most-liquid majors, monthly (no hindsight)"),
                          ("Basket equal-wt", r_eq, "equal weight across the majors universe"),
                          ("BTC 1x", r_btc, "BTC-only conservative sub-option")]:
        eq = curve(r).to_numpy()[i0:]
        m = metrics(eq)
        scen[name] = dict(eq=[round(float(x), 2) for x in eq],
                          metrics={kk: (None if (isinstance(vv, float) and vv != vv) else vv) for kk, vv in m.items()},
                          desc=desc)
    chart_dates = dates[i0:]; btc_close = [round(float(x), 2) for x in R.index.map(lambda d: 0).to_numpy()]  # placeholder
    btc_close = [round(float(x), 2) for x in pd.Series(S["BTC"]["close"], index=pd.to_datetime(S["BTC"]["dates"])).reindex(idx).ffill().to_numpy()[i0:]]

    # current holdings: today's top-8 basket + each selected asset's live position
    today = idx[-1]; selW = W.loc[today]; sel = list(selW[selW > 0].index)
    def holding(k):
        v = S[k]; E = v["E"]; close = v["close"]; n = len(E); j = n - 1
        d = 1 if E[j] > 0 else (-1 if E[j] < 0 else 0)
        # running return of the current spell
        i = j
        while i > 0 and (1 if E[i-1] > 0 else (-1 if E[i-1] < 0 else 0)) == d and d != 0: i -= 1
        run = (close[j] / close[i] - 1) * d if d != 0 and i < j else 0.0
        return dict(sym=k, direction=("LONG" if d > 0 else ("SHORT" if d < 0 else "FLAT")),
                    size_pct=round(abs(float(E[j])) * 100, 0), regime=v["reg"][j],
                    running_ret=round(float(run), 4), price=round(float(close[j]), 4))
    holdings_top8 = [holding(k) for k in sel]
    holdings_all = [holding(k) for k in R.columns]
    nlong = sum(1 for h in holdings_top8 if h["direction"] == "LONG")
    nshort = sum(1 for h in holdings_top8 if h["direction"] == "SHORT")

    out = dict(product="Multi-Asset Trend Basket", as_of=dates[-1],
               btc_price=round(float(S["BTC"]["close"][-1]), 2),
               universe=list(R.columns), n_top=N,
               scenarios=scen, dates=chart_dates, btc_close=btc_close,
               holdings_top8=holdings_top8, holdings_all=holdings_all,
               basket_today=dict(selected=sel, long=nlong, short=nshort, flat=len(sel) - nlong - nshort),
               note=("Diversified majors trend-basket (1x, no leverage). Validated: ~2x BTC's risk-adjusted "
                     "return at ~half the drawdown, robust across eras. Weak in pure alt-bear years "
                     "(2018/2022) when alts fall harder than BTC. Hypothetical; not financial advice."),
               generated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    with open(os.path.join(OUT, save_as), "w") as f:
        json.dump(out, f)
    print("saved", save_as, "| as_of", out["as_of"], "| basket today:", out["basket_today"])
    for k, v in scen.items():
        mm = v["metrics"]
        print(f"  {k:16s} $500->${mm['final']:>12,.0f}  CAGR {mm['cagr']*100:>4.0f}%  Sharpe {mm['sharpe']:.2f}  DD {mm['maxdd']*100:.0f}%  Calmar {mm['calmar']:.2f}")
    return out


if __name__ == "__main__":
    main()
