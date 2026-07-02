"""Define a CRISIS / RISK-OFF market type and trade it with a dedicated book, so 2018 & 2022 become
profitable WITHOUT hurting other years. Detector = cross-asset BREADTH (what fraction of risk assets are
below their SMA200) — known yesterday, no look-ahead. When breadth says risk-off:
  - DEFENSIVE assets (USD/gold/silver/oil/commodities/bonds): trade their trends, but flat in CHOP_HIVOL
  - RISK assets (US/HK/JP/EU equities + BTC): take SHORTS only (capture the decline), no chop longs
Otherwise: normal equal-weight trend book across everything. Same engine, honest costs, no per-year tuning.
"""
import numpy as np, pandas as pd
import compare_m1m5 as cm, regime_system as rs, signals as sg, backtest as bt, live_engine as le
from global_engine import fetch_yahoo
ANN = 365
RISK = {"US-SPY": ("SPY", 0.0005), "US-QQQ": ("QQQ", 0.0005), "HK-EWH": ("EWH", 0.0010),
        "JP-EWJ": ("EWJ", 0.0008), "EU-VGK": ("VGK", 0.0008), "EU-EWG": ("EWG", 0.0010), "BTC": ("BTC-USD", 0.005)}
DEF = {"Gold-GLD": ("GLD", 0.0006), "Silver-SLV": ("SLV", 0.0008), "Oil-USO": ("USO", 0.0012),
       "Commod-DBC": ("DBC", 0.0010), "USD-UUP": ("UUP", 0.0006), "Bond-TLT": ("TLT", 0.0006)}

def sleeve(df, slip, short_only=False, flat_chop=False):
    df = cm.prep(df); n = len(df); close = df["close"].to_numpy(); sma200 = df["SMA200"].to_numpy()
    sigs = sg.run_all(df, single_lookahead=False); memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
    reg, emap, exp_raw = le.ensemble_ctx(df, memb)
    rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
    expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
    e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy().copy()
    for i in range(n):
        if e_in[i] < 0 and not (reg[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]): e_in[i] = 0.0
        if short_only and e_in[i] > 0: e_in[i] = 0.0
        if flat_chop and reg[i] == "CHOP_HIVOL": e_in[i] = 0.0
    e_in = np.clip(e_in, -1, 1); held = 0.0; rnet = np.zeros(n); fee, band = 0.0005, 0.12
    for i in range(1, n):
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): continue
        e = e_in[i - 1] * min(1.0, 1.5 / rv[i - 1])
        if abs(e - held) < band and not (e == 0 and held != 0): e = held
        rnet[i] = e * (close[i] / close[i - 1] - 1) - abs(e - held) * (fee + slip); held = e
    idx = pd.to_datetime(df["Date"])
    return pd.Series(rnet, index=idx), pd.Series(close < sma200, index=idx)

rn, rs_, dn, dc, below = {}, {}, {}, {}, {}
for k, (tk, slip) in RISK.items():
    rn[k], below[k] = sleeve(fetch_yahoo(tk), slip)                       # risk normal
    rs_[k], _ = sleeve(fetch_yahoo(tk), slip, short_only=True)            # risk short-only (crisis)
for k, (tk, slip) in DEF.items():
    dn[k], _ = sleeve(fetch_yahoo(tk), slip)                              # defensive normal
    dc[k], _ = sleeve(fetch_yahoo(tk), slip, flat_chop=True)              # defensive flat-in-chop (crisis)
IDX = sorted(set().union(*[s.index for s in rn.values()]))
IDX = pd.DatetimeIndex([d for d in IDX if d >= pd.Timestamp("2017-01-01")])
def M(d): return pd.DataFrame(d).reindex(IDX).fillna(0.0)
RN, RS, DN, DC = M(rn), M(rs_), M(dn), M(dc)
BREADTH = pd.DataFrame(below).reindex(IDX).ffill().mean(axis=1).shift(1).fillna(0)   # frac risk assets in downtrend

def yearly(r):
    return [(y, (1 + r[(r.index >= f"{y}-01-01") & (r.index < f"{y+1}-01-01")]).prod() - 1)
            for y in range(2017, 2027) if len(r[(r.index >= f"{y}-01-01") & (r.index < f"{y+1}-01-01")]) > 20]
def cagrdd(r):
    e = (1 + r).cumprod(); return e.iloc[-1] ** (1 / (len(r) / ANN)) - 1, (e / e.cummax() - 1).min(), e.iloc[-1]

# baseline: normal book always (equal weight all)
normal_book = pd.concat([RN, DN], axis=1).mean(axis=1)
crisis_book = pd.concat([DC, RS], axis=1).mean(axis=1)
SUSTAIN = BREADTH.rolling(40).mean()          # breadth must stay risk-off ~8 weeks (skip fast 2020 V)
# crisis-aware: SUSTAINED high breadth -> crisis book, else normal book
for THR in (0.45, 0.55, 0.65):
    crisis = SUSTAIN >= THR
    port = np.where(crisis, crisis_book.reindex(IDX).fillna(0), normal_book.reindex(IDX).fillna(0))
    port = pd.Series(port, index=IDX)
    c, dd, f = cagrdd(port); cb, ddb, fb = cagrdd(normal_book)
    yrs_crisis = sorted(set(BREADTH.index[crisis].year))
    print(f"\n=== sustained breadth(40d)>={THR:.0%}  ({int(crisis.sum())} crisis-days; years flagged: {yrs_crisis}) ===")
    print(f"{'year':>5} {'baseline':>9} {'crisis-aware':>13}")
    for (y, rb), (_, rp) in zip(yearly(normal_book), yearly(port)):
        star = "  <= bear" if y in (2018, 2022) else ""
        print(f"{y:>5} {rb*100:>+8.0f}% {rp*100:>+12.0f}%{star}")
    print(f"baseline    : CAGR {cb*100:.0f}%  DD {ddb*100:.0f}%  $500->${500*fb:,.0f}")
    print(f"crisis-aware: CAGR {c*100:.0f}%  DD {dd*100:.0f}%  $500->${500*f:,.0f}")
