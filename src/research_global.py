"""GLOBAL cross-asset diversification research. Same 1x vol-targeted trend ensemble applied to
US/HK/JP/EU equities + crypto + gold + bonds (USD-denominated ETFs, so one currency, FX baked in).
Blends: equal-weight and inverse-vol (risk-parity) over the assets available each day. Reports
per-asset stats, the cross-asset correlation matrix, blend backtests by sub-period + drawdowns, and
a search for the best combination. No leverage. Data: Yahoo Finance v8 (cached to data/global/).
Honest notes: ensemble rules are crypto-derived and applied UNCHANGED to equities (out-of-sample for
the method); equity fills ~5-10bp, crypto 50bp+ (tiered); weekends = equity returns 0 (markets closed).
"""
import os, json, datetime as dt, numpy as np, pandas as pd, requests
from multi_asset_engine import sleeve, metrics
import live_engine as le
ANN = 365; CACHE = os.path.join(le.HERE, "..", "data", "global"); os.makedirs(CACHE, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
# name -> (yahoo ticker, region, round-trip slippage)
UNIVERSE = {
    "US-SPY": ("SPY", "US", 0.0005), "US-QQQ": ("QQQ", "US", 0.0005),
    "HK-EWH": ("EWH", "HK", 0.0010), "JP-EWJ": ("EWJ", "JP", 0.0008),
    "EU-VGK": ("VGK", "EU", 0.0008), "EU-EWG": ("EWG", "EU", 0.0010),
    "Gold-GLD": ("GLD", "Commod", 0.0006), "Silver-SLV": ("SLV", "Commod", 0.0008),
    "Oil-USO": ("USO", "Commod", 0.0012), "Bond-TLT": ("TLT", "Bond", 0.0006),
    "BTC": ("BTC-USD", "Crypto", 0.005), "ETH": ("ETH-USD", "Crypto", 0.006),
}

def fetch_yahoo(tk):
    fp = os.path.join(CACHE, tk.replace("-", "_") + ".csv")
    if os.path.exists(fp):
        return pd.read_csv(fp)
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?range=10y&interval=1d"
    r = requests.get(u, headers={"User-Agent": UA}, timeout=30).json()["chart"]["result"][0]
    ts = r["timestamp"]; q = r["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c): continue
        rows.append((dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%d"), o, h, l, c, v or 0))
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).drop_duplicates("date")
    df.to_csv(fp, index=False); return df

# --- per-asset sleeves ---
S = {}; Sfull = {}
for name, (tk, reg, slip) in UNIVERSE.items():
    try:
        sl = sleeve(fetch_yahoo(tk), slip); Sfull[name] = sl
        S[name] = pd.Series(sl["rnet"], index=pd.to_datetime(sl["dates"]))
        print(f"  {name:10s} {len(sl['dates'])}d")
    except Exception as e:
        print("  skip", name, repr(e)[:60])
R = pd.DataFrame(S).sort_index()                      # daily net strategy returns, union index
idx = R.index
buyhold = {}
for name, (tk, reg, slip) in UNIVERSE.items():
    df = fetch_yahoo(tk); buyhold[name] = pd.Series(df["close"].values, index=pd.to_datetime(df["date"]))

def stats(r, a, b):
    r = r.loc[a:b].dropna()
    if len(r) < 60: return (float('nan'),) * 4
    eq = (1 + r).cumprod(); yrs = len(r) / 252  # equities ~252 trading days/yr; mixed -> use calendar below
    yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
    cg = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    dd = (eq / eq.cummax() - 1).min(); sh = r.mean() / r.std(ddof=1) * np.sqrt(252) if r.std() > 0 else float('nan')
    return cg, dd, sh, eq.iloc[-1]

FULL_A, FULL_B = "2017-01-01", idx[-1].strftime("%Y-%m-%d")
P1 = ("2017-01-01", "2021-01-01"); P2 = ("2021-01-01", FULL_B)

print("\n=== PER-ASSET (trend sleeve, 1x) ===")
print(f"{'asset':10s} {'region':7s} | {'full CAGR':>9s} {'DD':>5s} {'Shrp':>5s} | {'21-26 CAGR':>10s} {'Shrp':>5s}")
for name in R.columns:
    reg = UNIVERSE[name][1]; c, d, s, _ = stats(R[name], FULL_A, FULL_B); _, _, s2, _ = stats(R[name], *P2); c2 = stats(R[name], *P2)[0]
    print(f"{name:10s} {reg:7s} | {c*100:>+8.0f}% {d*100:>4.0f}% {s:>5.2f} | {c2*100:>+9.0f}% {s2:>5.2f}")

# --- blends over assets available each day ---
def eqw(R): return R.mean(axis=1)                     # equal weight, available assets
def ivw(R, look=60, cap=0.25):                        # inverse-vol (risk parity), monthly, capped
    vol = R.rolling(look, min_periods=20).std().shift(1)
    W = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for m, g in R.groupby(R.index.to_period("M")).groups.items():
        v = vol.loc[g[0]]; avail = R.loc[g[0]].notna() & v.notna() & (v > 0)
        if not avail.any(): continue
        w = (1.0 / v[avail]); w = w / w.sum()
        for _ in range(6):                            # cap any weight at `cap`, renormalize the rest
            over = w > cap
            if not over.any(): break
            rem = 1 - cap * over.sum(); free = w[~over]
            w[over] = cap
            if free.sum() > 0: w[~over] = free / free.sum() * rem
        W.loc[g, w.index] = w.values
    return (R * W).sum(axis=1)

eqA = ["US-SPY", "US-QQQ", "HK-EWH", "JP-EWJ", "EU-VGK", "EU-EWG"]            # equities only
glob = list(R.columns)                                                        # everything
combos = {
    "Equities only (EW)": eqw(R[eqA]),
    "Equities + Crypto (EW)": eqw(R[eqA + ["BTC", "ETH"]]),
    "GLOBAL all (EW)": eqw(R[glob]),
    "GLOBAL all (inverse-vol)": ivw(R[glob]),
    "Equities+Crypto+Gold (inv-vol)": ivw(R[eqA + ["BTC", "ETH", "Gold-GLD"]]),
    "Crypto only (EW)": eqw(R[["BTC", "ETH"]]),
}
print("\n=== BLENDS ===")
print(f"{'combination':32s} | {'full CAGR':>9s} {'DD':>5s} {'Shrp':>5s} {'Calmar':>6s} | {'17-20 Shrp':>10s} | {'21-26 CAGR':>10s} {'DD':>5s} {'Shrp':>5s}")
for name, r in combos.items():
    cf, df_, sf, _ = stats(r, FULL_A, FULL_B); _, _, s1, _ = stats(r, *P1); c2, d2, s2, _ = stats(r, *P2)
    cal = cf / abs(df_) if df_ < 0 else 0
    print(f"{name:32s} | {cf*100:>+8.0f}% {df_*100:>4.0f}% {sf:>5.2f} {cal:>6.2f} | {s1:>10.2f} | {c2*100:>+9.0f}% {d2*100:>4.0f}% {s2:>5.2f}")
print("\nBenchmarks (buy & hold, full):")
for b in ["US-SPY", "BTC", "Gold-GLD"]:
    rr = buyhold[b].reindex(idx).ffill().pct_change(); c, d, s, _ = stats(rr, FULL_A, FULL_B)
    print(f"  {b:10s} CAGR {c*100:>+5.0f}%  DD {d*100:>4.0f}%  Sharpe {s:.2f}")
print("\n=== cross-asset SLEEVE-return correlation (full) ===")
print(R.loc[FULL_A:].corr().round(2).to_string())

print("\n=== CURRENT SIGNALS (what to do today, per product) ===")
print(f"{'product':10s} {'region':7s} | {'signal':6s} {'size':>5s} {'regime':14s} {'running%':>8s}")
for name in R.columns:
    sl = Sfull[name]; E = sl["E"]; close = sl["close"]; rg = sl["reg"]; j = len(E) - 1
    d = "LONG" if E[j] > 0 else ("SHORT" if E[j] < 0 else "FLAT")
    i = j
    while i > 0 and (np.sign(E[i - 1]) == np.sign(E[j])) and E[j] != 0: i -= 1
    run = (close[j] / close[i] - 1) * np.sign(E[j]) if E[j] != 0 and i < j else 0.0
    print(f"{name:10s} {UNIVERSE[name][1]:7s} | {d:6s} {abs(E[j])*100:>4.0f}% {rg[j]:14s} {run*100:>+7.1f}%")

print("\n=== FULL BACKTEST — best blend (GLOBAL all, equal-weight): yearly return & maxDD ===")
best = eqw(R[glob])
for y in range(2017, 2027):
    yr = best[(best.index >= f"{y}-01-01") & (best.index < f"{y+1}-01-01")]
    if len(yr) < 20: continue
    eq = (1 + yr).cumprod(); ret = eq.iloc[-1] - 1; dd = (eq / eq.cummax() - 1).min()
    print(f"  {y}:  return {ret*100:>+6.1f}%   maxDD {dd*100:>5.1f}%")
eqc = (1 + best.loc[FULL_A:]).cumprod()
print(f"  WHOLE: $500 -> ${eqc.iloc[-1]*500:,.0f}   maxDD {(eqc/eqc.cummax()-1).min()*100:.1f}%")
# save snapshot for a future dashboard
snap = {"as_of": idx[-1].strftime("%Y-%m-%d"), "signals": [
    {"product": n, "region": UNIVERSE[n][1],
     "signal": ("LONG" if Sfull[n]["E"][-1] > 0 else ("SHORT" if Sfull[n]["E"][-1] < 0 else "FLAT")),
     "size_pct": round(abs(Sfull[n]["E"][-1]) * 100, 0), "regime": Sfull[n]["reg"][-1]} for n in R.columns]}
json.dump(snap, open(os.path.join(le.OUT, "global_signals.json"), "w"), indent=1)
print("\nsaved out/global_signals.json")
