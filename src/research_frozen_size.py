"""FROZEN-AT-ENTRY sizing (the user's real practice): when a signal fires, enter with that size and
HOLD IT — no mid-trade re-sizing — until the signal exits/flips. Compare vs the live re-sizing model
(Max B stack) at 50bp and 0bp: final, DD, yearly, and the entry size of the current open trade.
Costs only on entry/exit (lower turnover). Liquidation checked daily on the frozen exposure.
"""
import os, numpy as np, pandas as pd
from live_engine import setup, ensemble_ctx, HERE
ANN = 365
df, reg0, memb = setup(); reg, emap, exp_raw = ensemble_ctx(df, memb)
dates = df["Date"].tolist(); n = len(df); i0 = 260
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()
def lmap(p, c): return dict(zip(pd.read_csv(p).iloc[:, 0].astype(str), pd.read_csv(p)[c])) if os.path.exists(p) else {}
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dates])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); fr = trk(funding); gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5
c_ = pd.Series(close)
below = (c_ < c_.rolling(1400).mean()).shift(1).fillna(False).to_numpy()
m111 = c_.rolling(111).mean(); m350 = 2 * c_.rolling(350).mean()
ab = (m111 > m350).to_numpy(); pi = np.zeros(n, bool); lc = -10**9
for i in range(1, n):
    if ab[i] and not ab[i - 1]: lc = i
    if i - lc <= 365: pi[i] = True
pi = np.roll(pi, 1); pi[0] = False

def sim(mode, slip, cap=5.0, vt=1.5, dd_kill=0.30, band=0.15, fee=0.0005, maint=0.01):
    """mode='resize' (live logic) or 'frozen' (enter with signal size, hold until exit/flip)."""
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); E = np.zeros(n); liq = 0
    for i in range(i0, n):
        sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if sig < 0 and below[i]: g = 0.0
        if pi[i]: g *= 0.5
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; E[i] = held; continue
        t = sig * g * min(cap, vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): t *= 0.5
        if mode == "resize":
            e = t
            if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        else:  # frozen: only act on entry / exit / flip
            if held == 0:
                e = t if abs(t) >= band else 0.0                     # enter at signal size
            elif np.sign(t) == np.sign(held):
                e = held                                             # HOLD the entry size
            else:
                e = t if abs(t) >= band else 0.0                     # exit to flat or flip
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint):
            eqv *= 0.01; liq += 1; held = 0.0; eq[i] = eqv; E[i] = 0.0; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); E[i] = e; peak = max(peak, eqv)
    return eq, E, liq

def rep(eq):
    s = pd.Series(eq[i0:], index=pd.to_datetime(dates[i0:]))
    dd = (s / s.cummax() - 1).min()
    ys = {}
    for y in range(2014, 2027):
        seg = s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]
        if len(seg) > 20: ys[y] = seg.iloc[-1] / seg.iloc[0] - 1
    return float(s.iloc[-1]), dd, ys

print(f"{'model':>16} {'slip':>5} {'FINAL':>14} {'maxDD':>6} {'liq':>4}")
res = {}
for mode in ("resize", "frozen"):
    for slip, tag in ((0.005, "50bp"), (0.0, "0bp")):
        eq, E, liq = sim(mode, slip); f, dd, ys = rep(eq); res[(mode, tag)] = (f, dd, ys, E)
        print(f"{mode:>16} {tag:>5} ${f:>13,.0f} {dd*100:>5.0f}% {liq:>4}")
print("\nyearly @50bp:")
print(f"{'year':>5} {'resize':>9} {'frozen':>9}")
ys_r = res[('resize','50bp')][2]; ys_f = res[('frozen','50bp')][2]
for y in range(2014, 2027):
    if y in ys_r: print(f"{y:>5} {ys_r[y]*100:>+8.0f}% {ys_f[y]*100:>+8.0f}%")
# current open trade entry size under frozen logic
E = res[('frozen','50bp')][3]
i = n - 1; s0 = np.sign(E[i]); k = i
while k > 0 and np.sign(E[k-1]) == s0 and s0 != 0: k -= 1
print(f"\nFROZEN current signal: {'LONG' if s0>0 else 'SHORT'} {abs(E[i]):.2f}x (entered {dates[k]} at ${close[k]:,.0f}, "
      f"margin {abs(E[i])/5*100:.0f}%) — held unchanged since entry: {bool(abs(E[i])==abs(E[k]))}")
# ---- middle ground: wider deadband = fewer resize actions, how much performance kept? ----
print("\nRESIZE-MODEL with wider deadbands (fewer actions):")
print(f"{'band':>6} {'FINAL @50bp':>14} {'maxDD':>6} {'trades/yr':>9} {'resizes/yr':>10} {'total actions/yr':>16}")
yrs_span = (n - i0) / ANN
for band in (0.15, 0.30, 0.50):
    eq, E, liq = sim("resize", 0.005, band=band)
    f, dd, ys = rep(eq)
    flips = 0; resz = 0
    for i in range(i0 + 1, n):
        if np.sign(E[i]) != np.sign(E[i-1]): flips += 1
        elif E[i] != E[i-1] and E[i] != 0: resz += 1
    print(f"{band:>6.2f} ${f:>13,.0f} {dd*100:>5.0f}% {flips/yrs_span:>9.1f} {resz/yrs_span:>10.1f} {(flips+resz)/yrs_span:>16.1f}")
