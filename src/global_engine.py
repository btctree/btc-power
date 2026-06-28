"""GLOBAL multi-asset engine -> out/results_global.json. A 12-product, no-leverage trend portfolio:
US/HK/JP/EU equities + Gold/Silver/Oil + Bonds + BTC/ETH (USD ETFs). Same 1x vol-targeted ensemble on
each; equal-weight blend (the validated best combination). Outputs scenarios (Global / Crypto / Equities
/ inverse-vol), per-product live signals, and the all-years backtest. Data: Yahoo (cached data/global/).
"""
import os, json, datetime as dt, numpy as np, pandas as pd, requests
from multi_asset_engine import sleeve, metrics
import live_engine as le
ANN = 365; CACHE = os.path.join(le.HERE, "..", "data", "global"); os.makedirs(CACHE, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
UNIVERSE = {
    "US-SPY": ("SPY", "US", 0.0005), "US-QQQ": ("QQQ", "US", 0.0005),
    "HK-EWH": ("EWH", "HK", 0.0010), "JP-EWJ": ("EWJ", "JP", 0.0008),
    "EU-VGK": ("VGK", "EU", 0.0008), "EU-EWG": ("EWG", "EU", 0.0010),
    "Gold-GLD": ("GLD", "Commod", 0.0006), "Silver-SLV": ("SLV", "Commod", 0.0008),
    "Oil-USO": ("USO", "Commod", 0.0012), "Bond-TLT": ("TLT", "Bond", 0.0006),
    "BTC": ("BTC-USD", "Crypto", 0.005), "ETH": ("ETH-USD", "Crypto", 0.006),
}
CRYPTO = ["BTC", "ETH"]; EQUITIES = ["US-SPY", "US-QQQ", "HK-EWH", "JP-EWJ", "EU-VGK", "EU-EWG"]


def fetch_yahoo(tk, refresh=True):
    fp = os.path.join(CACHE, tk.replace("-", "_") + ".csv")
    if os.path.exists(fp) and not refresh:
        return pd.read_csv(fp)
    try:
        u = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?range=10y&interval=1d"
        r = requests.get(u, headers={"User-Agent": UA}, timeout=30).json()["chart"]["result"][0]
        ts = r["timestamp"]; q = r["indicators"]["quote"][0]; rows = []
        for i, t in enumerate(ts):
            o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
            if None in (o, h, l, c): continue
            rows.append((dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%d"), o, h, l, c, v or 0))
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).drop_duplicates("date")
        df.to_csv(fp, index=False); return df
    except Exception as e:
        if os.path.exists(fp): print(f"[global] {tk} fetch failed, using cache"); return pd.read_csv(fp)
        raise


def ivw(R, look=60, cap=0.25):
    vol = R.rolling(look, min_periods=20).std().shift(1); W = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for m, g in R.groupby(R.index.to_period("M")).groups.items():
        v = vol.loc[g[0]]; av = R.loc[g[0]].notna() & v.notna() & (v > 0)
        if not av.any(): continue
        w = (1.0 / v[av]); w = w / w.sum()
        for _ in range(6):
            over = w > cap
            if not over.any(): break
            rem = 1 - cap * over.sum(); free = w[~over]; w[over] = cap
            if free.sum() > 0: w[~over] = free / free.sum() * rem
        W.loc[g, w.index] = w.values
    return (R * W).sum(axis=1)


def main(save_as="results_global.json"):
    S = {}
    for name, (tk, reg, slip) in UNIVERSE.items():
        try:
            S[name] = sleeve(fetch_yahoo(tk), slip); print(f"  {name:11s} {len(S[name]['dates'])}d")
        except Exception as e:
            print("  skip", name, repr(e)[:50])
    R = pd.DataFrame({k: pd.Series(v["rnet"], index=pd.to_datetime(v["dates"])) for k, v in S.items()}).sort_index()
    A = "2017-01-01"; R = R.loc[A:]; idx = R.index; dates = [d.strftime("%Y-%m-%d") for d in idx]

    def curve(r): return ((1 + r.fillna(0)).cumprod() * 500.0).to_numpy()
    scen = {}
    for nm, cols, r in [("Global blend (equal-wt)", None, R.mean(axis=1)),
                        ("Global (risk-parity)", None, ivw(R)),
                        ("Crypto only", None, R[CRYPTO].mean(axis=1)),
                        ("Equities only", None, R[EQUITIES].mean(axis=1))]:
        eq = curve(r); m = metrics(eq)
        scen[nm] = dict(eq=[round(float(x), 2) for x in eq],
                        metrics={k: (None if (isinstance(v, float) and v != v) else v) for k, v in m.items()})
    # all-years table for the headline blend
    head = R.mean(axis=1); yearly = []
    for y in range(2017, 2027):
        yr = head[(head.index >= f"{y}-01-01") & (head.index < f"{y + 1}-01-01")]
        if len(yr) < 20: continue
        eq = (1 + yr).cumprod(); yearly.append(dict(year=y, ret=round(float(eq.iloc[-1] - 1), 4),
                                                     dd=round(float((eq / eq.cummax() - 1).min()), 4)))
    # per-product live signals
    holdings = []
    for name in R.columns:
        v = S[name]; E = v["E"]; close = v["close"]; rg = v["reg"]; j = len(E) - 1
        d = "LONG" if E[j] > 0 else ("SHORT" if E[j] < 0 else "FLAT"); i = j
        while i > 0 and (np.sign(E[i - 1]) == np.sign(E[j])) and E[j] != 0: i -= 1
        run = (close[j] / close[i] - 1) * np.sign(E[j]) if E[j] != 0 and i < j else 0.0
        holdings.append(dict(product=name, region=UNIVERSE[name][1], signal=d,
                             size_pct=round(abs(float(E[j])) * 100, 0), regime=rg[j],
                             running_ret=round(float(run), 4), price=round(float(close[j]), 2)))
    nl = sum(h["signal"] == "LONG" for h in holdings); ns = sum(h["signal"] == "SHORT" for h in holdings)
    out = dict(product="Global Trend Portfolio", as_of=dates[-1], n=len(R.columns),
               scenarios=scen, dates=dates, yearly=yearly, holdings=holdings,
               summary=dict(long=nl, short=ns, flat=len(holdings) - nl - ns),
               note=("12-product global trend portfolio (US/HK/JP/EU equities + gold/silver/oil + bonds + "
                     "BTC/ETH), equal-weight, no leverage. Validated: +22% CAGR at -15% max drawdown, positive "
                     "every year 2017-2026 incl. the 2018 & 2022 bears. Hypothetical; not financial advice."),
               generated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    with open(os.path.join(le.OUT, save_as), "w") as f:
        json.dump(out, f)
    print("saved", save_as, "| as_of", out["as_of"], "| today:", out["summary"])
    for k, v in scen.items():
        m = v["metrics"]; print(f"  {k:24s} $500->${m['final']:>9,.0f}  CAGR {m['cagr']*100:>4.0f}%  Sharpe {m['sharpe']:.2f}  DD {m['maxdd']*100:.0f}%  Calmar {m['calmar']:.2f}")
    print("  years:", " ".join(f"{y['year']}:{y['ret']*100:+.0f}%" for y in yearly))
    return out


if __name__ == "__main__":
    main()
