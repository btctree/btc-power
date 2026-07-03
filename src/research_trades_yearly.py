"""Trade count + win ratio, overall and per year, for the LIVE Max B model @50bp."""
import os, numpy as np, pandas as pd
from live_engine import setup, ensemble_ctx, HERE
ANN = 365
df, reg0, memb = setup(); reg, emap, exp_raw = ensemble_ctx(df, memb)
dates = pd.to_datetime(df["Date"]); dstr = df["Date"].tolist(); n = len(df); i0 = 260
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()
def lmap(p, c): return dict(zip(pd.read_csv(p).iloc[:, 0].astype(str), pd.read_csv(p)[c])) if os.path.exists(p) else {}
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); fr = trk(funding); gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5
c_ = pd.Series(close)
wma200 = c_.rolling(1400).mean(); below_200w = (c_ < wma200).shift(1).fillna(False).to_numpy()
m111 = c_.rolling(111).mean(); m350x2 = 2 * c_.rolling(350).mean()
above = (m111 > m350x2).to_numpy(); pi = np.zeros(n, bool); lc = -10**9
for i in range(1, n):
    if above[i] and not above[i - 1]: lc = i
    if i - lc <= 365: pi[i] = True
pi = np.roll(pi, 1); pi[0] = False
eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); E = np.zeros(n)
for i in range(i0, n):
    sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
    if sig < 0 and below_200w[i]: g = 0.0
    if pi[i]: g *= 0.5
    if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; E[i] = held; continue
    e = sig * g * min(5.0, 1.5 / rv[i - 1])
    if eqv < peak * 0.70: e *= 0.5
    if abs(e - held) < 0.15 and not (e == 0 and held != 0): e = held
    adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
    if e != 0 and abs(e) * max(adv, 0) >= 0.99: eqv *= 0.01; held = 0.0; eq[i] = eqv; E[i] = 0; peak = max(peak, eqv); continue
    eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * 0.0055
    held = e; eq[i] = max(eqv, 1e-9); E[i] = e; peak = max(peak, eqv)
tr = []; i = i0
while i < n:
    s = 1 if E[i] > 0 else (-1 if E[i] < 0 else 0)
    if s == 0: i += 1; continue
    j = i
    while j + 1 < n and (1 if E[j + 1] > 0 else (-1 if E[j + 1] < 0 else 0)) == s: j += 1
    f0 = eq[i - 1] if i > 0 else 500.0
    tr.append(dict(year=dates[i].year, dir=s, ret=eq[j] / f0 - 1, open=(j == n - 1))); i = j + 1
T = pd.DataFrame(tr)
Tc = T[~T.open]                       # completed trades only for win ratio
print(f"{'year':>5} {'trades':>7} {'wins':>5} {'win%':>6} {'long w%':>8} {'short w%':>9}")
for y, g in Tc.groupby("year"):
    L = g[g.dir > 0]; S = g[g.dir < 0]
    print(f"{y:>5} {len(g):>7} {(g.ret>0).sum():>5} {(g.ret>0).mean()*100:>5.0f}% "
          f"{((L.ret>0).mean()*100 if len(L) else float('nan')):>7.0f}% {((S.ret>0).mean()*100 if len(S) else float('nan')):>8.0f}%")
L = Tc[Tc.dir > 0]; S = Tc[Tc.dir < 0]
print(f"{'ALL':>5} {len(Tc):>7} {(Tc.ret>0).sum():>5} {(Tc.ret>0).mean()*100:>5.0f}% "
      f"{(L.ret>0).mean()*100:>7.0f}% {(S.ret>0).mean()*100:>8.0f}%")
print(f"\ncompleted trades {len(Tc)} (+1 currently open) = {len(Tc)*2} in&out actions | longs {len(L)}, shorts {len(S)}")
print(f"avg win {Tc[Tc.ret>0].ret.mean()*100:+.1f}% | avg loss {Tc[Tc.ret<=0].ret.mean()*100:+.1f}% | payoff ratio {abs(Tc[Tc.ret>0].ret.mean()/Tc[Tc.ret<=0].ret.mean()):.2f}"
      if len(Tc[Tc.ret<=0]) else "")

# ---- holding days per trade + flat-gap days between trades, per year and overall ----
tr2 = []; gaps = []; i = i0; last_exit = None
while i < n:
    s = 1 if E[i] > 0 else (-1 if E[i] < 0 else 0)
    if s == 0: i += 1; continue
    j = i
    while j + 1 < n and (1 if E[j + 1] > 0 else (-1 if E[j + 1] < 0 else 0)) == s: j += 1
    if last_exit is not None and i - last_exit > 1:
        gaps.append(dict(year=dates[last_exit].year, days=i - last_exit - 1))
    tr2.append(dict(year=dates[i].year, hold=j - i + 1, open=(j == n - 1)))
    last_exit = j; i = j + 1
H = pd.DataFrame(tr2); G = pd.DataFrame(gaps)
print(f"{'year':>5} {'#tr':>4} {'avg hold':>9} {'max hold':>9} | {'#gaps':>6} {'avg gap':>8} {'max gap':>8}")
for y in range(2014, 2027):
    h = H[H.year == y]; g = G[G.year == y]
    if len(h) == 0: continue
    print(f"{y:>5} {len(h):>4} {h.hold.mean():>8.1f}d {h.hold.max():>8.0f}d | {len(g):>6} "
          f"{(g.days.mean() if len(g) else 0):>7.1f}d {(g.days.max() if len(g) else 0):>7.0f}d")
print(f"{'ALL':>5} {len(H):>4} {H.hold.mean():>8.1f}d {H.hold.max():>8.0f}d | {len(G):>6} {G.days.mean():>7.1f}d {G.days.max():>7.0f}d")
print(f"\ntime in market: {H.hold.sum()} of {n - i0} days ({H.hold.sum()/(n-i0)*100:.0f}%) | flat: {G.days.sum()} days ({G.days.sum()/(n-i0)*100:.0f}%)")
longest_gap = G.loc[G.days.idxmax()]
print(f"longest flat gap: {longest_gap.days:.0f} days, starting {longest_gap.year}")
longest_hold = H.loc[H.hold.idxmax()]
print(f"longest hold: {longest_hold.hold:.0f} days, entered {longest_hold.year}")

# ---- SAMPLING QUALITY: bootstrap the 109 completed trade returns (10,000 resamples) ----
rng = np.random.default_rng(42)
rets = Tc.ret.to_numpy()
finals = []
for _ in range(10000):
    smp = rng.choice(rets, size=len(rets), replace=True)
    finals.append(np.prod(1 + smp))
finals = np.array(finals)
p = np.percentile(finals, [5, 25, 50, 75, 95])
print(f"\nBOOTSTRAP (10k resamples of the {len(rets)} completed trades, compounded multiple of start):")
print(f"  5th pct {p[0]:>12,.0f}x | 25th {p[1]:>12,.0f}x | median {p[2]:>12,.0f}x | 75th {p[3]:>12,.0f}x | 95th {p[4]:>14,.0f}x")
print(f"  P(final multiple < 1, i.e. losing overall) = {(finals < 1).mean()*100:.2f}%")
print(f"  P(final < 100x) = {(finals < 100).mean()*100:.1f}%")
wr = (rets > 0).mean(); se = (wr * (1 - wr) / len(rets)) ** 0.5
print(f"  win-rate 95% CI: {wr*100:.0f}% +/- {1.96*se*100:.0f}pp")
top = np.sort(rets)[-10:]
print(f"  profit concentration: top-10 trades contribute {np.sum(np.log1p(top))/np.sum(np.log1p(rets[rets>-1]))*100:.0f}% of total log-return")
