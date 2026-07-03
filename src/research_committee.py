"""THE 7-BRAIN COMMITTEE: treat the 7 models as voters; act only on agreement.
Variants: AVG (blend of all exposures — netting lowers turnover), MAJ5 (>=5/7 same sign -> average of
agreeing exposures, else flat), UNAN (7/7 same sign). All at 50bp with the same cost/liquidation engine.
Honest note: the 7 share the same underlying 9-engine signal -> they are correlated voters, not
independent brains; disagreement happens at transitions/chop (where losses live) — that's the test.
"""
import os, numpy as np, pandas as pd
from live_engine import setup, ensemble_ctx, HERE
from global_engine import fetch_yahoo
ANN = 365
df, reg0, memb = setup(); reg, emap, exp_raw = ensemble_ctx(df, memb)
dates = pd.to_datetime(df["Date"]); dstr = df["Date"].tolist(); n = len(df); i0 = 260
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy(); sma200 = df["SMA200"].to_numpy()
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
esm5 = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()
esm10 = pd.Series(expf).ewm(span=10, adjust=False).mean().to_numpy()
apex_sig = esm5.copy()
for i in range(n):
    if apex_sig[i] < 0 and not (reg[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]): apex_sig[i] = 0.0
up = close > sma200; sgA = np.sign(apex_sig)
cap_ta = np.where(((sgA > 0) & up) | ((sgA < 0) & ~up), 3.25, 3.0)
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
m111 = c_.rolling(111).mean(); m350x2 = 2 * c_.rolling(350).mean()
above = (m111 > m350x2).to_numpy(); pi_alarm = np.zeros(n, bool); lc = -10**9
for i in range(1, n):
    if above[i] and not above[i - 1]: lc = i
    if i - lc <= 365: pi_alarm[i] = True
pi_alarm = np.roll(pi_alarm, 1); pi_alarm[0] = False

def target_expo(sig, cap, vt, legacy=None, dgate=0.0):
    """Each brain's DESIRED exposure path (pre-cost), with the floor+Pi stack applied."""
    caparr = cap if hasattr(cap, "__len__") else None
    E = np.zeros(n)
    for i in range(i0, n):
        s = sig[i - 1]; g = gl[i - 1] if s > 0 else (gs[i - 1] if s < 0 else 1.0)
        if dgate and dollar_strong[i - 1]: g *= dgate
        if s < 0 and below_200w[i]: g = 0.0
        if pi_alarm[i]: g *= 0.5
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): E[i] = E[i - 1]; continue
        mult = legacy * min(1.0, 0.60 / rv[i - 1]) if legacy else min(caparr[i - 1] if caparr is not None else cap, vt / rv[i - 1])
        E[i] = s * g * mult
    return E

BRAINS = [("SteadyA", target_expo(esm5, 2, 1.5, dgate=0.5)), ("MaxB", target_expo(esm5, 5, 1.5)),
          ("Raw8B", target_expo(expf, 5, 0.6, legacy=5)), ("Bal3x", target_expo(esm5, 3, 1.5)),
          ("AggrB", target_expo(esm5, 5, 2.0)), ("SmoothC", target_expo(esm10, 5, 1.5)),
          ("Apex", target_expo(apex_sig, cap_ta, 1.5))]
EM = np.stack([e for _, e in BRAINS])           # 7 x n desired exposures
SG = np.sign(EM)
agree_long = (SG > 0).sum(0); agree_short = (SG < 0).sum(0)
print("directional agreement stats (days): 7/7 long:", int((agree_long == 7).sum()),
      "| >=5 long:", int((agree_long >= 5).sum()), "| >=5 short:", int((agree_short >= 5).sum()),
      "| split/flat rest of", n - i0)

def run_expo(E_t, band=0.15, slip=0.005, dd_kill=0.30, fee=0.0005, maint=0.01):
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        e = E_t[i]
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
        if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint): eqv *= 0.01; held = 0.0; eq[i] = eqv; peak = max(peak, eqv); continue
        eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(eqv, 1e-9); peak = max(peak, eqv)
    return eq

# committees
E_avg = EM.mean(0)
maj = np.where(agree_long >= 5, 1, np.where(agree_short >= 5, -1, 0))
E_maj = np.zeros(n)
for i in range(n):
    if maj[i] > 0: E_maj[i] = EM[:, i][SG[:, i] > 0].mean()
    elif maj[i] < 0: E_maj[i] = EM[:, i][SG[:, i] < 0].mean()
unan = np.where(agree_long == 7, 1, np.where(agree_short == 7, -1, 0))
E_un = np.zeros(n)
for i in range(n):
    if unan[i] != 0: E_un[i] = EM[:, i].mean()

def rep(eq, nm):
    s = pd.Series(eq[i0:], index=dates[i0:])
    dd = (s / s.cummax() - 1).min()
    e2 = s[s.index >= "2021-01-01"]; c2 = (e2.iloc[-1] / e2.iloc[0]) ** (ANN / len(e2)) - 1
    ys = {}
    for y in range(2014, 2027):
        seg = s[(s.index >= f"{y}-01-01") & (s.index < f"{y+1}-01-01")]
        if len(seg) > 20: ys[y] = seg.iloc[-1] / seg.iloc[0] - 1
    bad = " ".join(f"{y}:{ys[y]*100:+.0f}%" for y in (2014, 2018, 2022, 2024, 2025) if y in ys)
    print(f"{nm:22s} ${s.iloc[-1]:>12,.0f}  21+ {c2*100:+.0f}%/yr  DD {dd*100:.0f}%  | hard yrs: {bad}")
    return s.iloc[-1]

print(f"\n{'committee variant':22s} {'FINAL @50bp':>13}")
rep(run_expo(E_avg), "AVG (blend all 7)")
rep(run_expo(E_maj), "MAJORITY >=5/7")
rep(run_expo(E_un), "UNANIMOUS 7/7")
print("\nreference: SteadyA $1.10M | MaxB $11.59M | AggrB+stack $13.45M (individual, same costs)")
