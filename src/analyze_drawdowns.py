"""Attribute the Core-1x ensemble's losses in the 3 user-flagged windows.
Reproduces the exact Core-1x config (lev=1, vol_target=0.60, dd_kill=0.30, slip=0.003) but
records the DAILY position/return so we can see WHY each window lost: wrong direction,
whipsaw, chop, or costs. Honest: real data, no look-ahead.
"""
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le

ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)   # conviction filter (Core/8B)
dates = pd.to_datetime(df["Date"])
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
n = len(df); i0 = 260

# ---- instrumented Core-1x sim (mirror of sc.simulate, lev=1) ----
lev, fee, slip, vol_target, dd_kill = 1.0, 0.0005, 0.003, 0.60, 0.30
equity = peak = 500.0; held = 0.0
rows = []
for i in range(i0, n):
    tgt = expf[i - 1] * lev
    if vol_target > 0 and rv[i - 1] == rv[i - 1] and rv[i - 1] > 0:
        tgt *= min(1.0, vol_target / rv[i - 1])
    if dd_kill > 0 and equity < peak * (1 - dd_kill):
        tgt *= 0.5
    e = tgt
    ret = close[i] / close[i - 1] - 1
    pnl = e * ret
    turn = abs(e - held); cost = turn * (fee + slip)
    equity *= (1 + pnl); equity -= equity * cost
    held = e; peak = max(peak, equity)
    rows.append(dict(date=dates.iloc[i], reg=reg[i - 1], e=e, btc_ret=ret,
                     pnl=pnl, cost=cost, equity=equity, price=close[i]))
S = pd.DataFrame(rows).set_index("date")

print(f"FULL: $500 -> ${S.equity.iloc[-1]:,.0f} | days {len(S)} | in-market {np.mean(S.e!=0)*100:.0f}%")
ddseries = S.equity / S.equity.cummax() - 1
print(f"maxDD {ddseries.min()*100:.0f}% on {ddseries.idxmin().date()}")

# ---- auto-detect worst peak->trough episodes ----
print("\n=== worst drawdown episodes (Core 1x) ===")
eq = S.equity.values; idx = S.index
peakv = -1; peaki = 0; episodes = []
run_peak = eq[0]; run_peak_i = 0
trough = eq[0]; trough_i = 0
i = 1
# simple: scan, record drops > 25% from a running peak until recovery
cur_peak = eq[0]; cur_peak_i = 0; cur_tr = eq[0]; cur_tr_i = 0
for k in range(1, len(eq)):
    if eq[k] > cur_peak:
        if cur_peak > cur_tr * 1.0 and (cur_tr / cur_peak - 1) < -0.20:
            episodes.append((idx[cur_peak_i], idx[cur_tr_i], cur_peak, cur_tr, cur_tr / cur_peak - 1))
        cur_peak = eq[k]; cur_peak_i = k; cur_tr = eq[k]; cur_tr_i = k
    elif eq[k] < cur_tr:
        cur_tr = eq[k]; cur_tr_i = k
if (cur_tr / cur_peak - 1) < -0.20:
    episodes.append((idx[cur_peak_i], idx[cur_tr_i], cur_peak, cur_tr, cur_tr / cur_peak - 1))
episodes.sort(key=lambda x: x[4])
for p, t, pv, tv, d in episodes[:8]:
    print(f"  {str(p.date())} -> {str(t.date())}  ${pv:,.0f}->${tv:,.0f}  {d*100:+.0f}%")

# ---- analyse the 3 user windows ----
WINDOWS = [
    ("W1  late-2017 -> 2018 crash", "2017-12-01", "2018-04-30"),
    ("W2  2021-11 top -> 2022", "2021-11-01", "2022-07-31"),
    ("W3  2025 second half", "2025-07-01", "2025-12-31"),
]
for name, a, b in WINDOWS:
    w = S.loc[a:b]
    if not len(w):
        print(f"\n## {name}: no data"); continue
    btc = w.price.iloc[-1] / w.price.iloc[0] - 1
    streq = w.equity.iloc[-1] / w.equity.iloc[0] - 1
    dd = (w.equity / w.equity.cummax() - 1).min()
    longd = np.mean(w.e > 0) * 100; shortd = np.mean(w.e < 0) * 100; flatd = np.mean(w.e == 0) * 100
    gross = w.pnl.sum(); costs = w.cost.sum()
    # pnl by regime
    byreg = w.groupby("reg").pnl.sum().sort_values()
    # pnl split long vs short days
    long_pnl = w.loc[w.e > 0, "pnl"].sum(); short_pnl = w.loc[w.e < 0, "pnl"].sum()
    print(f"\n## {name}  [{a} -> {b}]  ({len(w)} days)")
    print(f"   BTC buy&hold {btc*100:+.0f}%   |   Core-1x {streq*100:+.0f}%   |   window maxDD {dd*100:.0f}%")
    print(f"   positioning: LONG {longd:.0f}% / SHORT {shortd:.0f}% / FLAT {flatd:.0f}% of days")
    print(f"   gross pnl(sum) {gross*100:+.1f}%  costs(sum) {costs*100:.1f}%  | long-day pnl {long_pnl*100:+.1f}%  short-day pnl {short_pnl*100:+.1f}%")
    print("   pnl by regime:")
    for r, v in byreg.items():
        dd_share = w[w.reg == r]
        print(f"      {r:12s} {v*100:+6.1f}%   ({len(dd_share)} days, dir L{np.mean(dd_share.e>0)*100:.0f}/S{np.mean(dd_share.e<0)*100:.0f}/F{np.mean(dd_share.e==0)*100:.0f})")
