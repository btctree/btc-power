"""ACTUARY round 2 — engineer NEW derived datasets from price+time and test them:
 1) BTC POWER LAW: log(price) ~ a + n*log(days since genesis) -> deviation = mean-reversion signal
    (the 'multi square root / power of a past time' idea, done rigorously & causally).
 2) Halving-cycle phase (the 4-year cycle).
 3) Literal sqrt/power transforms of lagged prices.
All causal (expanding fits, prior-day values). Report predictive IC at 5/20/60/120d + backtests.
"""
import os
import numpy as np, pandas as pd
import stable_combo as sc
import live_engine as le

ANN = 365
df, reg0, memb = sc.prep()
reg, emap, exp_raw = le.ensemble_ctx(df, memb)
expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
c = df["close"]; close = c.to_numpy(); n = len(df); i0 = 260
dates = pd.to_datetime(df["Date"]); rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
logp = np.log(close)

# ---- 1) POWER LAW (causal expanding fit, refit every 5d) ----
genesis = pd.Timestamp("2009-01-03")
days = ((dates - genesis).dt.days).to_numpy().astype(float); days[days < 1] = 1
logd = np.log(days)
pl_resid = np.full(n, np.nan); pl_n = np.full(n, np.nan)
b = None
for i in range(i0, n):
    if b is None or (i - i0) % 5 == 0:
        A = np.column_stack([np.ones(i + 1), logd[:i + 1]])
        b, *_ = np.linalg.lstsq(A, logp[:i + 1], rcond=None)
    pl_resid[i] = logp[i] - (b[0] + b[1] * logd[i]); pl_n[i] = b[1]
pl_resid_z = ((pd.Series(pl_resid) - pd.Series(pl_resid).rolling(365, min_periods=120).mean())
              / pd.Series(pl_resid).rolling(365, min_periods=120).std()).to_numpy()
print(f"Power-law exponent n (latest causal fit): {pl_n[-1]:.2f}  (Santostasi-style ~5-6)")
print(f"Current deviation from power-law trend: resid {pl_resid[-1]:+.2f} (log), z {pl_resid_z[-1]:+.2f}  ({'ABOVE' if pl_resid[-1]>0 else 'BELOW'} fair value)")

# ---- 2) halving-cycle phase ----
halvings = [pd.Timestamp(x) for x in ["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20"]]
dsh = np.array([min([(d - h).days for h in halvings if h <= d] or [9999]) for d in dates], float)
phase = np.clip(dsh / 1458.0, 0, 1.2)           # 0..~1 through the 4yr cycle
cyc_sin = np.sin(2 * np.pi * phase); cyc_cos = np.cos(2 * np.pi * phase)

# ---- 3) literal sqrt/power-of-lagged-price transforms ----
def lagpow(lag, p):
    out = np.full(n, np.nan)
    out[lag:] = close[lag:] / (np.power(close[:-lag], p) + 1e-9)
    return out
sqrt_ratios = {f"price/lag{lag}^{p}": lagpow(lag, p) for lag, p in [(365, 0.5), (730, 0.5), (200, 0.75)]}

# ---- predictive IC ----
def ic(arr, hd):
    fwd = (c.shift(-hd) / c - 1).to_numpy()
    m = np.zeros(n, bool); m[i0:n - hd] = True
    m &= np.isfinite(arr) & np.isfinite(fwd)
    return np.corrcoef(arr[m], fwd[m])[0, 1] if m.sum() > 200 else np.nan

print("\nNEW-FEATURE predictive IC vs forward return (negative on pl_resid => mean-reversion):")
feats = {"pl_resid": pl_resid, "pl_resid_z": pl_resid_z, "cyc_sin": cyc_sin, "cyc_cos": cyc_cos,
         "cycle_phase": phase, **sqrt_ratios}
print(f"{'feature':16s} {'fwd5':>7s} {'fwd20':>7s} {'fwd60':>7s} {'fwd120':>7s}")
for nm, a in feats.items():
    print(f"{nm:16s} {ic(a,5):>7.3f} {ic(a,20):>7.3f} {ic(a,60):>7.3f} {ic(a,120):>7.3f}")

# ---- backtests ----
def sim(pos, lev, slip=0.005, vt=0.60):
    pos = np.clip(pos, -1, 1)
    eq = np.full(n, 500.0); equity = peak = 500.0; held = 0.0
    for i in range(i0, n):
        p = pos[i - 1]
        if not (np.isfinite(p) and np.isfinite(rv[i - 1]) and rv[i - 1] > 0):
            eq[i] = equity; continue
        tgt = p * lev * min(1.0, vt / rv[i - 1])
        if equity < peak * 0.70: tgt *= 0.5
        e = tgt; ret = close[i] / close[i - 1] - 1
        equity *= (1 + e * ret); equity -= equity * abs(e - held) * (0.0005 + slip)
        held = e; eq[i] = max(equity, 1e-6); peak = max(peak, equity)
    s = pd.Series(eq[i0:], index=dates.iloc[i0:].values); r = s.pct_change().dropna(); yrs = len(s) / ANN
    cagr = (s.iloc[-1] / 500) ** (1 / yrs) - 1 if s.iloc[-1] > 0 else -1
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dd = (s / s.cummax() - 1).min()
    return s.iloc[-1], sh, (cagr / abs(dd) if dd < 0 else float("nan")), dd

pl_signal = np.clip(-pl_resid_z / 2.0, -1, 1)                       # long below trend, short above
combo = np.clip(expf * (1 + np.nan_to_num(-pl_resid_z) * 0.5), -1, 1)  # ensemble tilted by power-law
print("\nBACKTEST @50bp ($500 start, vol-targeted):")
print(f"{'model':28s} {'final$':>14s} {'Shrp':>5s} {'Calm':>5s} {'maxDD':>6s}")
for nm, pos, lev in [("Power-law MR alone 1x", pl_signal, 1), ("Power-law MR alone 2x", pl_signal, 2),
                     ("Ensemble B 1x", expf, 1), ("Ensemble B 2x", expf, 2),
                     ("Ensemble x PowerLaw 1x", combo, 1), ("Ensemble x PowerLaw 2x", combo, 2)]:
    f, sh, cal, dd = sim(pos, lev)
    print(f"{nm:28s} ${f:>13,.0f} {sh:>5.2f} {cal:>5.2f} {dd*100:>5.0f}%")

# ===== corrected-sign + TRAIN/TEST robustness (overfitting check; n=3-4 cycles is the risk) =====
def sim_rng(pos, lev, a, b, slip=0.005, vt=0.60):
    pos = np.clip(pos, -1, 1); equity = peak = 500.0; held = 0.0; eqs = []
    for i in range(a, b):
        p = pos[i - 1]
        if not (np.isfinite(p) and np.isfinite(rv[i - 1]) and rv[i - 1] > 0): eqs.append(equity); continue
        tgt = p * lev * min(1.0, vt / rv[i - 1])
        if equity < peak * 0.70: tgt *= 0.5
        e = tgt; equity *= (1 + e * (close[i] / close[i - 1] - 1)); equity -= equity * abs(e - held) * (0.0005 + slip)
        held = e; equity = max(equity, 1e-6); peak = max(peak, equity); eqs.append(equity)
    s = pd.Series(eqs); r = s.pct_change().dropna()
    sh = r.mean() * ANN / (r.std(ddof=1) * np.sqrt(ANN)) if r.std() > 0 else float("nan")
    dd = (s / s.cummax() - 1).min(); return s.iloc[-1] / s.iloc[0], sh, dd
mid = (i0 + n) // 2
plz = np.nan_to_num(pl_resid_z)
sigs = {"PL momentum (long ABOVE trend)": np.clip(plz / 2, -1, 1),
        "cyc_cos (cycle)": np.clip(cyc_cos, -1, 1),
        "Ensemble x PL+ (correct sign)": np.clip(expf * (1 + plz * 0.5), -1, 1),
        "Ensemble alone (ref)": expf}
print("\nCORRECTED-SIGN + TRAIN/TEST (1x):")
print(f"{'signal':32s} {'train Sh/DD':>16s} {'test Sh/DD':>16s}")
for nm, pos in sigs.items():
    ftr, shtr, ddtr = sim_rng(pos, 1, i0, mid); fte, shte, ddte = sim_rng(pos, 1, mid, n)
    print(f"{nm:32s} {shtr:>7.2f}/{ddtr*100:>5.0f}% {shte:>7.2f}/{ddte*100:>5.0f}%")
