"""Full per-cell sizing/margin optimization with TRAIN/TEST validation.

Every (regime, direction) cell gets its OWN margin% and leverage (and longs/shorts
their own trailing stop). We randomly search thousands of combinations, fit on the
TRAIN half, and measure on the held-out TEST half — so we can see whether per-cell
tuning is real edge or overfitting.

Fast daily-fidelity engine (uses daily high/low — the true 1-min intraday extremes —
to detect trailing-stop hits). The winning config is then re-checked on the full
1-minute engine (trend_ride_sim) for fidelity.
"""
import os, json, random
import numpy as np
import regime_switch_sim as rss

HERE = os.path.dirname(__file__)
MAP = rss.MAP
TREND_GROUP = rss.TREND_GROUP
BEAR_GROUP = rss.BEAR_GROUP
# active (regime, dir) cells that can trade
LONG_REGIMES = ["BULL_TREND", "BULL_PULLBACK", "CHOP_HIGHVOL", "BEAR_TREND", "BEAR_BOUNCE"]
SHORT_REGIMES = ["CHOP_HIGHVOL", "BEAR_TREND", "BULL_PULLBACK", "BEAR_BOUNCE"]
CELLS = [(r, 1) for r in LONG_REGIMES] + [(r, -1) for r in SHORT_REGIMES]

_C = None


def load():
    global _C
    if _C is None:
        df, reg, memb, intr, fund = rss.load()
        _C = dict(close=df["close"].to_numpy(), high=df["high"].to_numpy(),
                  low=df["low"].to_numpy(), reg=reg, memb=memb,
                  fund={}, dates=df["Date"].tolist())
        # daily funding map -> array
        import pandas as pd
        p = os.path.join(HERE, "..", "data", "funding.csv")
        fmap = dict(zip(*[pd.read_csv(p)[c] for c in ["date", "funding_rate"]])) if os.path.exists(p) else {}
        _C["fundarr"] = np.array([fmap.get(d, 0.00011 * 3) for d in _C["dates"]])
    return _C


def fast_sim(size_map, lo, hi, cutloss_long=0.10, cutloss_short=0.07,
             fee=0.0005, use_funding=False, slip=0.0, start=500.0):
    """size_map: {(regime,dir): (margin_frac, leverage)}. lo:hi = day index window."""
    C = load(); close = C["close"]; high = C["high"]; low = C["low"]
    reg = C["reg"]; memb = C["memb"]; fundarr = C["fundarr"]
    equity = start; pos = None
    eq = []; liqs = 0
    for i in range(lo, hi):
        rg = reg[i]
        if pos is not None:
            d = pos["dir"]; cl = pos["cl"]; exited = False
            # test trailing stop against today's extreme (pre-update, conservative)
            if d == 1:
                if low[i] <= pos["stop"]:
                    fill = pos["stop"] * (1 - slip); exited = True
                elif pos["liq"] and low[i] <= pos["liq"]:
                    equity -= pos["margin"] + pos["notional"] * fee; liqs += 1; pos = None; eq.append(max(equity, 0)); continue
                else:
                    if high[i] > pos["hi"]:
                        pos["hi"] = high[i]; pos["stop"] = max(pos["stop"], pos["hi"] * (1 - cl))
            else:
                if high[i] >= pos["stop"]:
                    fill = pos["stop"] * (1 + slip); exited = True
                elif pos["liq"] and high[i] >= pos["liq"]:
                    equity -= pos["margin"] + pos["notional"] * fee; liqs += 1; pos = None; eq.append(max(equity, 0)); continue
                else:
                    if low[i] < pos["lo"]:
                        pos["lo"] = low[i]; pos["stop"] = min(pos["stop"], pos["lo"] * (1 + cl))
            if exited:
                equity += pos["notional"] * (fill / pos["entry"] - 1) * d - pos["notional"] * fee
                pos = None
            else:
                if use_funding:
                    equity -= pos["notional"] * fundarr[i]
                suited = _suited(pos, rg); m = memb[pos["strat"]][i]
                sig_exit = (m * d < 0) if pos["kind"] == "trend" else (m * d <= 0)
                if (not suited) or sig_exit:
                    equity += pos["notional"] * (close[i] / pos["entry"] - 1) * d - pos["notional"] * fee
                    pos = None
        if pos is None and equity > 1:
            strat, kind, cs = MAP.get(rg, (None, "flat", 0))
            if strat and cs >= 0.5:
                m = memb[strat][i]
                d = 1 if m > 0 else (-1 if m < 0 else 0)
                cell = size_map.get((rg, d))
                if d != 0 and cell is not None and cell[0] > 0:
                    szf, lev = cell[0], cell[1]
                    cl = cell[2] if len(cell) > 2 else (cutloss_long if d == 1 else cutloss_short)
                    margin = equity * szf; notional = margin * lev
                    equity -= notional * fee
                    entry = close[i]
                    if d == 1:
                        stop = entry * (1 - cl); liq = entry * (1 - 1 / lev + 0.005) if lev > 1 else None
                        if liq:
                            stop = max(stop, liq * 1.003)
                    else:
                        stop = entry * (1 + cl); liq = entry * (1 + 1 / lev - 0.005) if lev > 1 else None
                        if liq:
                            stop = min(stop, liq * 0.997)
                    pos = dict(entry=entry, dir=d, strat=strat, kind=kind, regime=rg,
                               margin=margin, notional=notional, hi=entry, lo=entry, stop=stop, liq=liq, cl=cl)
        eq.append(max(equity, 0))
        if equity <= 0:
            eq += [0] * (hi - i - 1); break
    return np.array(eq), liqs


def _suited(pos, rg):
    if pos["kind"] == "trend" and pos["regime"] in TREND_GROUP:
        return rg in TREND_GROUP
    if pos["regime"] in BEAR_GROUP:
        return rg in BEAR_GROUP
    return rg == pos["regime"]


def metrics(eq, start=500.0):
    if len(eq) < 2 or eq[-1] <= 0:
        return dict(final=eq[-1] if len(eq) else 0, cagr=-1, sharpe=-9, maxdd=-1, calmar=-9)
    r = np.diff(eq) / eq[:-1]; r = r[np.isfinite(r)]
    yrs = len(eq) / 365
    cagr = (eq[-1] / start) ** (1 / yrs) - 1
    sh = r.mean() * 365 / (r.std(ddof=1) * np.sqrt(365)) if r.std() > 0 else -9
    peak = np.maximum.accumulate(eq); dd = (eq / peak - 1).min()
    return dict(final=eq[-1], cagr=cagr, sharpe=sh, maxdd=dd, calmar=cagr / abs(dd) if dd < 0 else -9)


def main(N=6000):
    """WIDENED search: per-cell size x leverage x STOP-LOSS, with a 3-WAY split.
    TRAIN+VALIDATION are used to fit & SELECT; TEST is touched only to report the
    final unbiased out-of-sample number (no leakage)."""
    C = load(); n = len(C["close"])
    t1 = 260 + int((n - 260) * 0.45)   # end of train
    t2 = 260 + int((n - 260) * 0.72)   # end of validation
    print(f"split: TRAIN 260:{t1}  VAL {t1}:{t2}  TEST {t2}:{n}  (days {n})")
    random.seed(11)
    sizes = [0.0, 0.25, 0.5, 0.75, 1.0]; levs = [1, 2, 3]; cls = [0.05, 0.07, 0.10, 0.15, 0.20]
    results = []
    for _ in range(N):
        sm = {cell: (random.choice(sizes), random.choice(levs), random.choice(cls)) for cell in CELLS}
        etr, ltr = fast_sim(sm, 260, t1)
        if ltr > 0:
            continue
        mtr = metrics(etr)
        if mtr["sharpe"] < 0.3:        # prune obvious losers before spending val/test evals
            continue
        eva, lva = fast_sim(sm, t1, t2)
        ete, lte = fast_sim(sm, t2, n)
        if lva > 0:
            continue
        results.append((sm, mtr, metrics(eva), metrics(ete), ltr + lva + lte))
    print(f"evaluated {len(results)} no-liquidation, non-losing configs (of {N})")
    if not results:
        return None

    ref = {(r, 1): (1.0, 1, 0.10) for r in LONG_REGIMES}
    ref[("CHOP_HIGHVOL", -1)] = (0.5, 1, 0.07); ref[("BEAR_TREND", -1)] = (0.5, 1, 0.07)
    rtr = metrics(fast_sim(ref, 260, t1)[0]); rva = metrics(fast_sim(ref, t1, t2)[0]); rte = metrics(fast_sim(ref, t2, n)[0])
    print(f"\nREFERENCE (principled): train {rtr['sharpe']:.2f} | val {rva['sharpe']:.2f} | TEST {rte['sharpe']:.2f}")

    def line(tag, sm, mtr, mva, mte):
        print(f"[{tag:34s}] train {mtr['sharpe']:.2f} | val {mva['sharpe']:.2f} | TEST {mte['sharpe']:.2f}"
              f"  (test CAGR {mte['cagr']*100:.0f}% DD {mte['maxdd']*100:.0f}%)")

    # SELECTION uses train+val only (no test leakage):
    sel = sorted(results, key=lambda x: -min(x[1]["sharpe"], x[2]["sharpe"]))[0]
    print("\n--- selection by TRAIN+VAL robustness (test reported but NOT used to select) ---")
    line("SELECTED (robust on train+val)", *sel[:4])
    # for contrast: the in-sample-max (train only) and the oracle (test) :
    bt = sorted(results, key=lambda x: -x[1]["sharpe"])[0]
    line("in-sample-max (train only)", *bt[:4])
    orc = sorted(results, key=lambda x: -x[3]["sharpe"])[0]
    line("oracle best-on-TEST (unusable)", *orc[:4])
    # generalization stats
    top = sorted(results, key=lambda x: -np.minimum(x[1]["sharpe"], x[2]["sharpe"]))[:50]
    print(f"\nTop-50 by train+val robustness: median val {np.median([t[2]['sharpe'] for t in top]):.2f} "
          f"-> median TEST {np.median([t[3]['sharpe'] for t in top]):.2f}")
    tb = sorted(results, key=lambda x: -x[1]["sharpe"])[:50]
    print(f"Top-50 by TRAIN only:           median train {np.median([t[1]['sharpe'] for t in tb]):.2f} "
          f"-> median TEST {np.median([t[3]['sharpe'] for t in tb]):.2f}")

    sm = sel[0]; full = metrics(fast_sim(sm, 260, n)[0])
    print(f"\nSELECTED config full-period: ${full['final']:,.0f}  CAGR {full['cagr']*100:.0f}%  "
          f"Sharpe {full['sharpe']:.2f}  DD {full['maxdd']*100:.0f}%  Calmar {full['calmar']:.2f}")
    print("Per-cell (size% x lev, stop):")
    for (rg, d), v in sorted(sm.items(), key=lambda x: (x[0][1], x[0][0])):
        if v[0] > 0:
            print(f"  {'LONG ' if d == 1 else 'SHORT'} {rg:14s}: {int(v[0]*100)}% x {v[1]}x, {int(v[2]*100)}% stop  (expo {v[0]*v[1]*100:.0f}%)")
    json.dump({"selected": {f"{k[0]}|{k[1]}": list(v) for k, v in sm.items()},
               "test_sharpe": sel[3]["sharpe"], "ref_test_sharpe": rte["sharpe"]},
              open(os.path.join(HERE, "..", "out", "opt_widened.json"), "w"))
    return sm


if __name__ == "__main__":
    main()
