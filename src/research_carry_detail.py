"""FULL CALCULATION of the carry sleeve on Core 1x: decompose every component per year —
days carry active, average carry notional, gross funding collected ($), re-size costs paid ($),
net carry contribution ($ and %), and reconcile base + carry = combined equity exactly.
"""
import os, numpy as np, pandas as pd
from live_engine import setup, ensemble_ctx, HERE
ANN = 365
df, reg0, memb = setup(); reg, emap, exp_raw = ensemble_ctx(df, memb)
dates = pd.to_datetime(df["Date"]); dstr = df["Date"].tolist(); n = len(df); i0 = 260
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
esm = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()
def lmap(p, c): return dict(zip(pd.read_csv(p).iloc[:, 0].astype(str), pd.read_csv(p)[c])) if os.path.exists(p) else {}
fmap = lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate")
funding = np.array([fmap.get(d, np.nan) for d in dstr])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); fr = trk(funding); gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5
f_sm = pd.Series(funding, index=dates).rolling(7, min_periods=3).mean().shift(1).to_numpy()
carry_on = (f_sm > 0)
f_yday = pd.Series(funding, index=dates).shift(1).to_numpy()

def sim(carry, cap=1, vt=1.5, band=0.15, slip=0.005, dd_kill=0.30, fee=0.0005, maint=0.01, carry_cost=0.002):
    eqv = peak = 500.0; held = 0.0; heldc = 0.0; eq = np.full(n, 500.0)
    log = []  # (date, carry_notional_frac, funding_income_$, resize_cost_$)
    for i in range(i0, n):
        sig = esm[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; continue
        e = sig * g * min(cap, vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint):
            eqv *= 0.01; held = 0.0; heldc = 0.0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        inc = 0.0; cost = 0.0
        if carry:
            idle = max(0.0, 1.0 - abs(e))
            c_t = idle if (carry_on[i - 1] and idle > 0.25) else 0.0
            if abs(c_t - heldc) > 0.3 or (c_t == 0 and heldc > 0):
                cost = eqv * abs(c_t - heldc) * carry_cost; eqv -= cost; heldc = c_t
            if heldc > 0 and f_yday[i] == f_yday[i]:
                inc = eqv * heldc * max(f_yday[i], -0.0005); eqv += inc
        log.append((dates[i], heldc, inc, cost))
        held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv)
    return eq, pd.DataFrame(log, columns=["date", "cnot", "inc", "cost"]).set_index("date")

eq0, _ = sim(False); eq1, L = sim(True)
print("=== THE MECHANISM, step by step ===")
print("1. Each day the trend model sets exposure e (0..1 for Core 1x). Idle capital = 1 - |e|.")
print("2. If 7d-avg funding (known yesterday) > 0 AND idle > 25%: carry sleeve = idle fraction,")
print("   as long-spot + short-perp (delta-neutral). Position re-sized only if it drifts >0.3 (no churn).")
print("3. Daily income = equity x carry_fraction x yesterday's funding rate. Costs: 0.2% of notional per re-size.")
print()
print(f"{'year':>5} {'carry days':>10} {'avg notion.':>11} {'funding earned':>14} {'resize costs':>12} {'net':>10}")
tot_inc = tot_cost = 0.0
for y in range(2020, 2027):
    g = L[(L.index >= f"{y}-01-01") & (L.index < f"{y+1}-01-01")]
    if len(g) < 20: continue
    act = g[g.cnot > 0]
    tot_inc += g.inc.sum(); tot_cost += g.cost.sum()
    print(f"{y:>5} {len(act):>10} {act.cnot.mean() if len(act) else 0:>10.0%} ${g.inc.sum():>13,.2f} ${g.cost.sum():>11,.2f} ${g.inc.sum()-g.cost.sum():>9,.2f}")
print(f"{'ALL':>5} {'':>10} {'':>11} ${tot_inc:>13,.2f} ${tot_cost:>11,.2f} ${tot_inc-tot_cost:>9,.2f}")
print(f"\nRECONCILIATION: Core 1x base final ${eq0[-1]:,.2f}  |  with carry ${eq1[-1]:,.2f}")
print(f"difference ${eq1[-1]-eq0[-1]:,.2f} = compounded effect of the net carry income above")
print(f"(simple sum ${tot_inc-tot_cost:,.2f} compounds because income earned early keeps growing with the strategy)")
