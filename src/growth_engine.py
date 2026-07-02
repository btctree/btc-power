"""GROWTH A live engine -> out/results_live.json (the chosen PRODUCTION model, replaces Apex).
Growth A = conviction-filtered regime ensemble (|exp|>=0.4), EMA-5 smoothed + 0.15 deadband (turnover
control), cap 5x, vol-target 1.5, VOL+FUND gates, dd-kill 30%. NO short-selectivity, NO trend-aligned
cap (that's what distinguishes it from Apex). Verified @50bp: $500 -> $3,536,933 (2014+), maxDD -59%,
Sharpe 1.35, Calmar 1.75, win 38%. Honest: losing years exist (2018/2022/2025). Scenarios for the
Returns chart = the SAME Growth A logic at 1x / 0bp / 50bp / 100bp. Same JSON schema as the Apex build
(model_growth; model_apex/model_8b kept as aliases so cached dashboards keep working during cutover).
"""
import os, json, datetime as dt
import numpy as np, pandas as pd
from live_engine import setup, ensemble_ctx, metrics, OUT, HERE
ANN = 365
REG_BIAS = {"STRONG_UP": "UP", "TREND_UP": "UP", "PULLBACK_UP": "UP", "BOUNCE_DOWN": "UP",
            "STRONG_DOWN": "DOWN", "TREND_DOWN": "DOWN", "CHOP_HIVOL": "ASIDE", "RANGE": "ASIDE", "NEUTRAL": "ASIDE"}


def trail_rank(a, w=365):
    return pd.Series(a).rolling(w, min_periods=60).apply(lambda x: (x.iloc[-1] >= x).mean(), raw=False).to_numpy()


def main(save_as="results_live.json"):
    df, reg0, memb = setup()
    reg, emap, exp_raw = ensemble_ctx(df, memb)
    dates = df["Date"].tolist(); n = len(df); i0 = 260
    close = df["close"].to_numpy(); low = df["low"].to_numpy(); high = df["high"].to_numpy()
    sma200 = df["SMA200"].to_numpy()
    rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
    expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
    e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy()   # turnover control (no short filter)
    p = os.path.join(HERE, "..", "data", "funding.csv")
    fmap = dict(zip(*[pd.read_csv(p)[c] for c in ["date", "funding_rate"]])) if os.path.exists(p) else {}
    if not fmap:
        print("[growth] WARNING: data/funding.csv missing -> VOL+FUND gates DISABLED (results will differ).")
    elif max(fmap) < dates[-1]:
        print(f"[growth] note: funding.csv ends {max(fmap)} (latest bar {dates[-1]}) -> recent FUND gates inactive.")
    funding = np.array([fmap.get(d, np.nan) for d in dates])
    vr = trail_rank(rv); fr = trail_rank(funding)
    gl = np.ones(n); gs = np.ones(n)
    for i in range(n):
        if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
        if fr[i] == fr[i]:
            if fr[i] > 0.90: gl[i] *= 0.5
            if fr[i] < 0.10: gs[i] *= 0.5

    def sim(cap, slip, vt=1.5, dd_kill=0.30, band=0.15, fee=0.0005, maint=0.01):
        eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); E = np.zeros(n); liq = 0
        for i in range(i0, n):
            sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
            if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; E[i] = held; continue
            e = sig * g * min(cap, vt / rv[i - 1])
            if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
            if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
            adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
            if e != 0 and abs(e) * max(adv, 0) >= (1 - maint):
                eqv *= 0.01; liq += 1; held = 0.0; eq[i] = eqv; E[i] = 0.0; peak = max(peak, eqv); continue
            eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
            held = e; eq[i] = max(eqv, 1e-9); E[i] = e; peak = max(peak, eqv)
        return eq, E, liq

    specs = [("1x (spot, 50bp)", 1.0, 0.005, "Growth A signal at 1x — no leverage (realistic)"),
             ("Growth A @0bp", 5.0, 0.0, "Growth A perfect-fill (optimistic, untradeable)"),
             ("Growth A @50bp", 5.0, 0.005, "Growth A realistic (50bp slippage) — the headline"),
             ("Growth A @100bp", 5.0, 0.010, "Growth A stressed (100bp slippage)")]
    scen = {}; E_main = None; eq_main = None
    for name, cap, slip, desc in specs:
        eq, E, liq = sim(cap, slip)
        if name == "Growth A @50bp": E_main = E; eq_main = eq
        eqs = eq[i0:]; m = metrics(eqs)
        scen[name] = dict(eq=[round(float(x), 2) for x in eqs],
                          metrics={k: (None if (isinstance(v, float) and v != v) else round(float(v), 4)) for k, v in m.items()},
                          liq=int(liq), slip=slip, desc=desc)
    chart_dates = dates[i0:n]; chart_close = [round(float(x), 2) for x in close[i0:n]]

    # trades + paired entry/exit markers from the @50bp run; flag the current open trade
    trades = []; markers = []; i = i0
    while i < n:
        s = 1 if E_main[i] > 0 else (-1 if E_main[i] < 0 else 0)
        if s == 0: i += 1; continue
        j = i
        while j + 1 < n and (1 if E_main[j + 1] > 0 else (-1 if E_main[j + 1] < 0 else 0)) == s: j += 1
        entry = float(close[i]); exit_ = float(close[j]); ret = (exit_ / entry - 1.0) * s
        f0 = eq_main[i - 1] if i > 0 else 500.0
        model_ret = (eq_main[j] / f0 - 1.0) if f0 > 0 else 0.0
        is_open = (j == n - 1)
        nxt = (1 if (j + 1 < n and E_main[j + 1] > 0) else (-1 if (j + 1 < n and E_main[j + 1] < 0) else 0))
        reason = ("OPEN — current position" if is_open else
                  ("flipped to " + ("LONG" if nxt > 0 else "SHORT") if nxt != 0 else "went flat / regime change"))
        trades.append(dict(entry_dt=dates[i], exit_dt=dates[j], market=reg[i],
                           strategy=", ".join(emap.get(reg[i]) or []) or "—",
                           direction="LONG" if s > 0 else "SHORT", entry=round(entry, 2),
                           exit=round(exit_, 2), ret=round(ret, 4), apex_ret=round(float(model_ret), 4),
                           reason=reason, idx=i - i0, exit_idx=j - i0, open=is_open, exit_date=dates[j]))
        markers.append({"i": i - i0, "d": s, "t": "in"})
        if not is_open: markers.append({"i": j - i0, "d": s, "t": "out"})
        i = j + 1
    recent = trades[-20:][::-1]

    # today's Growth A signal
    i = n - 1; price = float(close[i]); rgi = reg[i]; engines = emap.get(rgi) or []
    sig = e_in[i]; g = gl[i] if sig > 0 else (gs[i] if sig < 0 else 1.0)
    mult = min(5.0, 1.5 / rv[i]) if (rv[i] == rv[i] and rv[i] > 0) else 0.0
    e = sig * g * mult; sg2 = 1 if e > 0 else (-1 if e < 0 else 0)
    dirn = "LONG" if sg2 > 0 else ("SHORT" if sg2 < 0 else "FLAT"); expm = abs(e)
    liqm = (1.0 / expm) if expm > 0 else 0.0
    growth = dict(direction=dirn, regime=rgi, engines=engines, exposure_mult=round(expm, 2),
                  action=(f"{dirn} {expm:.1f}x equity" if sg2 else "FLAT — stand aside"),
                  confidence=round(abs(e_in[i]), 2), conviction_ok=bool(abs(e_in[i]) > 0),
                  margin_pct=round(expm / 5 * 100, 0), vol_scale=round(min(1.0, 1.5 / rv[i]), 2) if rv[i] > 0 else 1.0,
                  cutloss=(round(price * (0.85 if sg2 > 0 else 1.15), 2) if sg2 else None),
                  liquidation=(round((price * (1 - liqm) if sg2 > 0 else price * (1 + liqm)), 2) if (sg2 and expm > 0) else None),
                  note=(f"Growth A: 5x-capped vol-targeted ensemble — the production model. Effective {expm:.1f}x — "
                        f"needs a ~{liqm*100:.0f}% adverse gap to liquidate; 0 liquidations in backtest (tail risk remains). "
                        f"Honest: maxDD -59%; losing years happen (2018/2022/2025 in backtest)."))
    core = dict(direction=dirn, regime=rgi, engines=engines,
                action=(f"{dirn} (spot 1x)" if sg2 else "FLAT — stand aside"),
                size_pct=round(min(1.0, abs(e_in[i])) * 100, 0), margin="SPOT 1x — no leverage, cannot be liquidated",
                cutloss=(round(price * (0.85 if sg2 > 0 else 1.15), 2) if sg2 else None),
                confidence=round(abs(e_in[i]), 2), take_profit="ride the trend; exit when the ensemble flips / regime changes")
    natbias = REG_BIAS.get(rgi, "ASIDE"); posbias = "UP" if sg2 > 0 else ("DOWN" if sg2 < 0 else "ASIDE")
    conflict = bool(sg2) and natbias in ("UP", "DOWN") and natbias != posbias
    clp = round(price * (0.85 if sg2 > 0 else 1.15), 2) if sg2 else None
    if not sg2:
        head = f"{rgi}: no qualifying setup — stand aside."
    elif conflict:
        head = (f"Holding {dirn} into a {rgi} market (trailing signal). Manage with the cut-loss "
                f"${clp:,.0f}; Growth A exits when the ensemble flips.")
    else:
        head = f"{rgi}: ensemble leans {dirn} (engines {', '.join(engines) or '—'})."
    fc = dict(regime=rgi, engines=engines, direction=dirn,
              bias=("POTENTIAL UP" if sg2 > 0 else ("POTENTIAL DOWN" if sg2 < 0 else "STAND ASIDE")),
              headline=head)
    s20 = float(df["SMA20"].iloc[i]); s50 = float(df["SMA50"].iloc[i]); s200 = float(sma200[i])
    bbu = float(df["BB_Upper"].iloc[i]); bbl = float(df["BB_Lower"].iloc[i])
    out = dict(as_of=dates[i], price=round(price, 2), rsi=round(float(df["RSI"].iloc[i]), 1),
               in_position=(dirn != "FLAT"), model_name="Growth A",
               live=core, model_growth=growth, model_apex=growth, model_8b=growth, forecast=fc, regime_bias=REG_BIAS,
               no_trade_status=dict(market=rgi, bias=fc["bias"], next_action=fc["headline"]),
               levels=dict(price=round(price, 2), sma20=round(s20, 2), sma50=round(s50, 2), sma200=round(s200, 2),
                           bb_upper=round(bbu, 2), bb_lower=round(bbl, 2)),
               scenarios=scen, dates=chart_dates, close=chart_close, recent_trades=recent, trade_markers=markers,
               generated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    with open(os.path.join(OUT, save_as), "w") as f:
        json.dump(out, f)
    print("saved", save_as, "|", out["as_of"], "$%.0f" % out["price"], "| Growth A:", growth["action"])
    for k, v in scen.items():
        print(f"  {k:16s} ${v['metrics']['final']:>15,.0f}  DD {v['metrics']['maxdd']*100:>4.0f}%  liq {v['liq']}")
    print(f"  recent trades: {len(recent)} | open trade flagged: {recent[0]['open'] if recent else None} | markers: {len(markers)}")
    return out


if __name__ == "__main__":
    main()
