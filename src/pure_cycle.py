"""PURE MATH-CYCLE strategy: ignore ALL normal trading logic (no RSI/MACD/ensemble/regime).
Use ONLY the halving cycle + power law to go long/short. Backtest $500 from 2014, 1x and leveraged,
honest intraday liquidation. Reports in-sample (cycle rules fit to history) vs causal (honest) and
buy&hold. WARNING: cycle phases & power law are calibrated on only ~3-4 BTC cycles -> in-sample = optimistic.
"""
import numpy as np, pandas as pd
import compare_m1m5 as cm

ANN = 365
df = cm.prep(cm.build_combined())
c = df["close"]; close = c.to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
dates = pd.to_datetime(df["Date"]); n = len(df); i0 = 260
logp = np.log(close)

# ---- the math cycle ----
genesis = pd.Timestamp("2009-01-03")
days = ((dates - genesis).dt.days).to_numpy().astype(float); days[days < 1] = 1
logd = np.log(days)
halvings = [pd.Timestamp(x) for x in ["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20"]]
dsh = np.array([min([(d - h).days for h in halvings if h <= d] or [9999]) for d in dates], float)
phase = dsh / 1458.0                      # 0..1 through the ~4yr cycle

# power law: full-fit (in-sample) and causal (honest, expanding)
A = np.column_stack([np.ones(n), logd]); bfull, *_ = np.linalg.lstsq(A, logp, rcond=None)
resid_full = logp - (bfull[0] + bfull[1] * logd)
resid_caus = np.full(n, np.nan); b = None
for i in range(60, n):
    if b is None or i % 5 == 0:
        b, *_ = np.linalg.lstsq(np.column_stack([np.ones(i + 1), logd[:i + 1]]), logp[:i + 1], rcond=None)
    resid_caus[i] = logp[i] - (b[0] + b[1] * logd[i])
print(f"power-law exponent n={bfull[1]:.2f} | BTC now: resid_full {resid_full[-1]:+.2f}, resid_causal {resid_caus[-1]:+.2f}")

# ---- cycle position rules (calendar only) ----
# bull: halving->top (phase<0.42) and accumulation pre-halving (phase>0.62); bear: top->bottom (0.42-0.62)
def cyc_pos(longshort=True):
    p = np.zeros(n)
    for i in range(n):
        ph = phase[i] % 1.0
        if ph < 0.42 or ph > 0.62: p[i] = 1.0
        else: p[i] = -1.0 if longshort else 0.0
    return p
# power-law mean-reversion position (buy below fair value, sell above), scaled
def pl_pos(resid, ls=True):
    z = pd.Series(resid); zz = ((z - z.rolling(365, min_periods=120).mean()) / z.rolling(365, min_periods=120).std()).to_numpy()
    p = np.clip(-zz / 1.5, -1, 1) if ls else np.clip(-zz / 1.5, 0, 1)
    return np.nan_to_num(p)

def sim(pos, lev, slip=0.0, fee=0.0005, maint=0.01):
    equity = peak = 500.0; held = 0.0; liq = 0; eq = np.full(n, 500.0)
    for i in range(i0, n):
        e = pos[i - 1] * lev
        adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
        if e != 0 and abs(e) * max(adv, 0) >= (1 - maint):
            equity *= 0.01; liq += 1; held = 0.0; eq[i] = equity; peak = max(peak, equity); continue
        equity *= (1 + e * (close[i] / close[i - 1] - 1)); equity -= equity * abs(e - held) * (fee + slip)
        held = e; eq[i] = max(equity, 1e-9); peak = max(peak, equity)
    s = pd.Series(eq[i0:], index=dates.iloc[i0:].values); r = s.pct_change().dropna(); yrs = len(s) / ANN
    cagr = (s.iloc[-1] / 500) ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1
    dd = (s / s.cummax() - 1).min()
    return s.iloc[-1], cagr, dd, liq

# buy & hold
bh = 500 * close[-1] / close[i0]
print(f"\nstart {dates.iloc[i0].date()}  ->  now {dates.iloc[-1].date()}   (BTC ${close[i0]:,.0f} -> ${close[-1]:,.0f})")
print(f"BUY & HOLD $500 -> ${bh:,.0f}  (DD ~ -83%)\n")

STRATS = [
    ("Cycle long/short (in-sample)", cyc_pos(True)),
    ("Cycle long-only (in-sample)", cyc_pos(False)),
    ("PowerLaw MR (in-sample fit)", pl_pos(resid_full, True)),
    ("PowerLaw MR (CAUSAL/honest)", pl_pos(resid_caus, True)),
]
for slip in (0.0, 0.005):
    print(f"================  slippage {int(slip*10000)}bp  ================")
    print(f"{'strategy':32s} {'lev':>4s} {'$500 ->':>16s} {'CAGR':>6s} {'maxDD':>7s} {'liq':>4s}")
    for nm, pos in STRATS:
        for lev in (1, 2, 3, 5):
            f, cagr, dd, liq = sim(pos, lev, slip)
            mark = "  <-- NO-LIQ" if liq == 0 and lev > 1 else ("  LIQUIDATED" if liq > 0 else "")
            print(f"{nm:32s} {lev:>3d}x ${f:>15,.0f} {cagr*100:>5.0f}% {dd*100:>6.0f}% {liq:>4d}{mark}")
        print()
