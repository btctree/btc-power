"""How fragile are the results given only ~63-116 trades / 12yr? Block-bootstrap the daily returns
+ trade-level win-rate CI + profit concentration (top-10 trades). Answers: is the sample too small?
"""
import os
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le
ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
sma200 = df["SMA200"].to_numpy(); n = len(df); i0 = 260; dstr = df["Date"].tolist(); dates = pd.to_datetime(df["Date"])
rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
regA = np.array(reg, dtype=object); up = close > sma200
HERE = os.path.dirname(os.path.abspath(__file__))
def lmap(p, col):
    f = pd.read_csv(p); return dict(zip(f.iloc[:, 0].astype(str), f[col]))
funding = np.array([lmap(os.path.join(HERE, "..", "data", "funding.csv"), "funding_rate").get(d, np.nan) for d in dstr])
def trk(a, w=365): return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()
vr = trk(rv); fr = trk(funding)
gl = np.ones(n); gs = np.ones(n)
for i in range(n):
    if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
    if fr[i] == fr[i]:
        if fr[i] > 0.90: gl[i] *= 0.5
        if fr[i] < 0.10: gs[i] *= 0.5
def build(conv, short_gate, long_confirm, smooth=5):
    ef = np.where(np.abs(exp_raw) >= conv, exp_raw, 0.0)
    e = pd.Series(ef).ewm(span=smooth, adjust=False).mean().to_numpy().copy()
    for i in range(n):
        if e[i] < 0 and short_gate and not (regA[i] in ("STRONG_DOWN","TREND_DOWN") and close[i] < sma200[i]): e[i] = 0.0
        if e[i] > 0 and long_confirm and not (close[i] > sma200[i]): e[i] = 0.0
    return e
def sim(e_in, vt=1.5, slip=0.005, dd_kill=0.30, band=0.15, fee=0.0005, maint=0.01):
    sgn = np.sign(e_in); aligned = ((sgn > 0) & up) | ((sgn < 0) & ~up); cap = np.where(aligned, 5.0, 3.0)
    eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); E = np.zeros(n); rets = []
    for i in range(i0, n):
        sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
        if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; E[i] = held; rets.append(0.0); continue
        ee = sig * g * min(cap[i - 1], vt / rv[i - 1])
        if dd_kill > 0 and eqv < peak * (1 - dd_kill): ee *= 0.5
        if band > 0 and abs(ee - held) < band and not (ee == 0 and held != 0): ee = held
        prev = eqv
        adv = (-(low[i] / close[i - 1] - 1)) if ee > 0 else ((high[i] / close[i - 1] - 1) if ee < 0 else 0.0)
        if ee != 0 and abs(ee) * max(adv, 0) >= (1 - maint):
            eqv *= 0.01; held = 0.0; eq[i] = eqv; E[i] = 0.0; peak = max(peak, eqv); rets.append(eqv/prev-1); continue
        eqv *= (1 + ee * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(ee - held) * (fee + slip)
        held = ee; eq[i] = max(eqv, 1e-9); E[i] = ee; peak = max(peak, eqv); rets.append(eqv/prev-1)
    return eq, E, np.array(rets)
def trades(eq, E):
    i = i0; tr = []
    while i < n:
        s = 1 if E[i] > 0 else (-1 if E[i] < 0 else 0)
        if s == 0: i += 1; continue
        j = i
        while j + 1 < n and (1 if E[j+1]>0 else (-1 if E[j+1]<0 else 0)) == s: j += 1
        f0 = eq[i-1] if i > 0 else 500.0; tr.append(eq[j]/f0 - 1); i = j + 1
    return np.array(tr)

def block_boot(rets, L=21, N=3000):
    m = len(rets); finals = []; sharpes = []; dds = []
    nb = m // L + 1
    for _ in range(N):
        starts = np.random.randint(0, m - L, size=nb)
        path = np.concatenate([rets[s:s+L] for s in starts])[:m]
        eq = 500.0 * np.cumprod(1 + path)
        finals.append(eq[-1]);
        r = path; sharpes.append(r.mean()*ANN/(r.std(ddof=1)*np.sqrt(ANN)) if r.std()>0 else 0)
        dds.append((eq/np.maximum.accumulate(eq)-1).min())
    return np.array(finals), np.array(sharpes), np.array(dds)

for nm, conv, sg, lc in [("WIN-opt (conv0.55+short-dn)", 0.55, True, False),
                          ("PROFIT-opt (pure-aligned)", 0.55, True, True)]:
    e_in = build(conv, sg, lc); eq, E, rets = sim(e_in); tr = trades(eq, E)
    actual = eq[-1]; nt = len(tr); wr = (tr > 0).mean()
    wr_se = np.sqrt(wr*(1-wr)/nt)
    # profit concentration via log-returns of trades
    lg = np.log1p(np.clip(tr, -0.99, None)); order = np.argsort(-lg); top10 = lg[order[:10]].sum(); tot = lg.sum()
    fin, sh, dd = block_boot(rets)
    print(f"\n=== {nm} ===  actual ${actual:,.0f} | {nt} trades")
    print(f"  WIN RATE {wr*100:.0f}% +/- {wr_se*100:.0f}%  -> 95% CI [{(wr-1.96*wr_se)*100:.0f}%, {(wr+1.96*wr_se)*100:.0f}%]")
    print(f"  top-10 trades = {top10/tot*100:.0f}% of total log-profit  (profit is concentrated in a few trades)")
    print(f"  bootstrap final $:  5th ${np.percentile(fin,5):,.0f} | median ${np.percentile(fin,50):,.0f} | 95th ${np.percentile(fin,95):,.0f}")
    print(f"  bootstrap Sharpe :  5th {np.percentile(sh,5):.2f} | median {np.percentile(sh,50):.2f} | 95th {np.percentile(sh,95):.2f}  | P(Sharpe>0)={np.mean(sh>0)*100:.0f}%")
    print(f"  bootstrap maxDD  :  5th {np.percentile(dd,5)*100:.0f}% | median {np.percentile(dd,50)*100:.0f}% | 95th {np.percentile(dd,95)*100:.0f}%")
