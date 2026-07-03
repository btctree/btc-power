"""EARLY BEAR-YEAR DETECTION, the user's spec: flag the losing year AT ITS START (not during profit
years). Community tools tested:
  T1 Pi Cycle Top: 111DMA crosses above 2x350DMA = cycle-top alarm (fired 2013, Dec-2017 3 days before
     top, Apr-2021). Rule: for 365 days after a cross -> exposure x mult (the traditional bear window).
  T2 Halving calendar: the classic losing years 2014/2018/2022 are ALL halving+2 years. Rule: de-risk
     in halving+2 calendar years. HONESTY: n=3 events, and 2025 (a loss year) was halving+1 while 2026
     (halving+2) is profitable -> the cycle drifted this time. Fragile by construction.
Applied on the two best bases (cap2+dollar-gate+200WMA-floor, GrowthA+floor). No look-ahead: crosses
and calendars known in real time. 50bp.
"""
import os, numpy as np, pandas as pd
from live_engine import setup, ensemble_ctx, HERE
from global_engine import fetch_yahoo
ANN = 365
df, reg0, memb = setup(); reg, emap, exp_raw = ensemble_ctx(df, memb)
dates = pd.to_datetime(df["Date"]); dstr = df["Date"].tolist(); n = len(df); i0 = 260
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
esm = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()
def lmap(p, c): return dict(zip(pd.read_csv(p).iloc[:, 0].astype(str), pd.read_csv(p)[c])) if os.path.exists(p) else {}
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); fr = trk(funding); gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5
u = fetch_yahoo("UUP", refresh=False)
uup = pd.Series(u["close"].values, index=pd.to_datetime(u["date"])).reindex(dates).ffill()
dollar_strong = (uup > uup.rolling(200).mean()).shift(1).fillna(False).to_numpy()
c_ = pd.Series(close, index=dates)
wma200 = c_.rolling(1400).mean(); below_200w = (c_ < wma200).shift(1).fillna(False).to_numpy()
# Pi Cycle Top: 111DMA crossing above 2x350DMA
m111 = c_.rolling(111).mean(); m350x2 = 2 * c_.rolling(350).mean()
above = (m111 > m350x2).to_numpy()
pi_alarm = np.zeros(n, bool); last_cross = -10**9
for i in range(1, n):
    if above[i] and not above[i - 1]: last_cross = i
    if i - last_cross <= 365: pi_alarm[i] = True
pi_alarm = np.roll(pi_alarm, 1); pi_alarm[0] = False          # act next day
cross_dates = [dstr[i] for i in range(1, n) if above[i] and not above[i - 1]]
print("Pi Cycle Top crosses:", cross_dates)
# halving+2 calendar
yr = dates.dt.year.to_numpy()
halv2 = np.isin(yr, [2014, 2018, 2022, 2026])

def sim(cap, vt, band=0.15, slip=0.005, dd_kill=0.30, fee=0.0005, maint=0.01, dgate=0.0,
        floor=True, pimult=None, calmult=None):
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        sig = esm[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if dgate and dollar_strong[i - 1]: g *= dgate
        if floor and sig < 0 and below_200w[i]: g = 0.0
        if pimult is not None and pi_alarm[i]: g *= pimult
        if calmult is not None and halv2[i]: g *= calmult
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        e = sig * g * min(cap, vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint): eqv *= 0.01; held = 0.0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv)
    return eq

def rep(eq):
    s = pd.Series(eq[i0:], index=dates[i0:])
    e2 = s[s.index >= "2021-01-01"]
    c2 = (e2.iloc[-1] / e2.iloc[0]) ** (ANN / len(e2)) - 1
    dd = (s / s.cummax() - 1).min()
    yrs = {}
    for y in (2018, 2022, 2025, 2017, 2019, 2020, 2023, 2024, 2026):
        seg = s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]
        if len(seg) > 20: yrs[y] = seg.iloc[-1] / seg.iloc[0] - 1
    return s.iloc[-1], c2, dd, yrs

for base_nm, kw in [("cap2+gate+floor", dict(cap=2, vt=1.5, dgate=0.5)), ("GrowthA+floor", dict(cap=5, vt=1.5))]:
    print(f"\n=== base: {base_nm} ===")
    print(f"{'variant':22s} {'FULL $':>12} {'21+':>6} {'DD':>5} | {'2018':>6} {'2022':>6} {'2025':>6} | {'2017':>6} {'2019':>6} {'2020':>6}")
    for vn, extra in [("(base)", {}), ("PiCycle x0.5/12m", dict(pimult=0.5)), ("PiCycle x0.25/12m", dict(pimult=0.25)),
                      ("halving+2 x0.5", dict(calmult=0.5))]:
        f, c2, dd, ys = rep(sim(**kw, **extra))
        print(f"{vn:22s} ${f:>11,.0f} {c2*100:>+5.0f}% {dd*100:>4.0f}% | {ys.get(2018,0)*100:>+5.0f}% {ys.get(2022,0)*100:>+5.0f}% {ys.get(2025,0)*100:>+5.0f}% | {ys.get(2017,0)*100:>+5.0f}% {ys.get(2019,0)*100:>+5.0f}% {ys.get(2020,0)*100:>+5.0f}%")

# full yearly + straightness for the PiCycle winners
def rep2(eq):
    s = pd.Series(eq[i0:], index=dates[i0:])
    e1 = s[s.index < "2021-01-01"]; e2 = s[s.index >= "2021-01-01"]
    c1 = (e1.iloc[-1] / e1.iloc[0]) ** (ANN / len(e1)) - 1; c2 = (e2.iloc[-1] / e2.iloc[0]) ** (ANN / len(e2)) - 1
    ys = {}
    for y in range(2014, 2027):
        seg = s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]
        if len(seg) > 20: ys[y] = seg.iloc[-1] / seg.iloc[0] - 1
    return s.iloc[-1], c1, c2, (c2 / c1 if c1 > 0 else np.nan), ys
print("\nFULL YEARLY (PiCycle x0.5 variants):")
for nm, kw in [("cap2+gate+floor+Pi.5", dict(cap=2, vt=1.5, dgate=0.5, pimult=0.5)),
               ("GrowthA+floor+Pi.5", dict(cap=5, vt=1.5, pimult=0.5))]:
    f, c1, c2, ratio, ys = rep2(sim(**kw))
    print(f"{nm}: ${f:,.0f} | early {c1*100:+.0f}%/yr late {c2*100:+.0f}%/yr ratio {ratio:.2f}")
    print("   " + " ".join(f"{y}:{r*100:+.0f}%" for y, r in ys.items()))

# ===== FULL PERFORMANCE BY YEAR, 0bp AND 50bp, both final candidates =====
def yearly_full(eq):
    s = pd.Series(eq[i0:], index=dates[i0:]); out = {}
    for y in range(2014, 2027):
        seg = s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]
        if len(seg) > 20:
            out[y] = (seg.iloc[-1] / seg.iloc[0] - 1, (seg / seg.cummax() - 1).min())
    r = s.pct_change().dropna(); yrs_ = len(s) / ANN
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs_) - 1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dd = (s / s.cummax() - 1).min()
    return out, s.iloc[-1], cagr, sh, dd

CANDS = [("A Steady-Million (cap2 stack)", dict(cap=2, vt=1.5, dgate=0.5, pimult=0.5)),
         ("B Max (cap5 stack)", dict(cap=5, vt=1.5, pimult=0.5))]
for nm, kw in CANDS:
    y0, f0_, c0, s0, d0 = yearly_full(sim(slip=0.0, **kw))
    y5, f5_, c5, s5, d5 = yearly_full(sim(slip=0.005, **kw))
    print(f"\n===== {nm} =====")
    print(f"{'year':>5} | {'0bp ret':>8} {'0bp DD':>7} | {'50bp ret':>8} {'50bp DD':>7}")
    for y in range(2014, 2027):
        if y not in y5: continue
        a, b = y0[y]; c, d = y5[y]
        print(f"{y:>5} | {a*100:>+7.0f}% {b*100:>6.0f}% | {c*100:>+7.0f}% {d*100:>6.0f}%")
    print(f"FINAL | 0bp ${f0_:,.0f} (CAGR {c0*100:+.0f}%, Sharpe {s0:.2f}, maxDD {d0*100:.0f}%)")
    print(f"      | 50bp ${f5_:,.0f} (CAGR {c5*100:+.0f}%, Sharpe {s5:.2f}, maxDD {d5*100:.0f}%)")
