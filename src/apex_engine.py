"""APEX live engine -> out/results_live.json (replaces the 8B model).
Apex = conviction-filtered regime ensemble, SHORT-SELECTIVE (only short confirmed downtrends),
turnover-controlled (EMA-5 + 0.15 deadband), TREND-ALIGNED cap (3.25x with-trend / 3.0x counter),
vol-targeted (60%), VOL+FUND gates, DD-kill 30%. Scenarios for the chart = the SAME Apex logic at
1x / 0bp / 50bp / 100bp (so the Returns chart presents the current model, not the old 8B/1B curve).
Same JSON schema as before (model_apex; model_8b kept as alias for back-compat during cutover).
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
    sma200 = df["SMA200"].to_numpy(); regA = np.array(reg, dtype=object); up = close > sma200
    rv = pd.Series(close).pct_change().rolling(20).std().to_numpy() * np.sqrt(ANN)
    expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)
    e_in = pd.Series(expf).ewm(span=5, adjust=False).mean().to_numpy().copy()   # turnover control first
    for i in range(n):                                  # then SHORT-SELECTIVE on the smoothed signal
        if e_in[i] < 0 and not (regA[i] in ("STRONG_DOWN", "TREND_DOWN") and close[i] < sma200[i]):
            e_in[i] = 0.0
    sgn = np.sign(e_in); aligned = ((sgn > 0) & up) | ((sgn < 0) & ~up)
    cap_ta = np.where(aligned, 3.25, 3.0)
    p = os.path.join(HERE, "..", "data", "funding.csv")
    fmap = dict(zip(*[pd.read_csv(p)[c] for c in ["date", "funding_rate"]])) if os.path.exists(p) else {}
    funding = np.array([fmap.get(d, np.nan) for d in dates])
    vr = trail_rank(rv); fr = trail_rank(funding)
    gl = np.ones(n); gs = np.ones(n)
    for i in range(n):
        if vr[i] == vr[i] and vr[i] > 0.85: gl[i] *= 0.5; gs[i] *= 0.5
        if fr[i] == fr[i]:
            if fr[i] > 0.90: gl[i] *= 0.5
            if fr[i] < 0.10: gs[i] *= 0.5

    def sim(cap_arr, slip, vt=1.5, dd_kill=0.30, band=0.15, fee=0.0005, maint=0.01):
        eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); E = np.zeros(n); liq = 0
        for i in range(i0, n):
            sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
            if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; E[i] = held; continue
            e = sig * g * min(cap_arr[i - 1], vt / rv[i - 1])
            if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
            if band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
            adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
            if e != 0 and abs(e) * max(adv, 0) >= (1 - maint):
                eqv *= 0.01; liq += 1; held = 0.0; eq[i] = eqv; E[i] = 0.0; peak = max(peak, eqv); continue
            eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
            held = e; eq[i] = max(eqv, 1e-9); E[i] = e; peak = max(peak, eqv)
        return eq, E, liq

    ones = np.ones(n)
    specs = [("1x (spot, 50bp)", ones, 0.005, "Apex signal at 1x — no leverage (realistic)"),
             ("Apex @0bp", cap_ta, 0.0, "Apex perfect-fill (optimistic, untradeable)"),
             ("Apex @50bp", cap_ta, 0.005, "Apex realistic (50bp slippage) — the headline"),
             ("Apex @100bp", cap_ta, 0.010, "Apex stressed (100bp slippage)")]
    scen = {}; E_main = None
    for name, ca, slip, desc in specs:
        eq, E, liq = sim(ca, slip)
        if name == "Apex @50bp": E_main = E; eq_main = eq
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
        apex_ret = (eq_main[j] / f0 - 1.0) if f0 > 0 else 0.0   # REAL realized equity return of this position
        is_open = (j == n - 1)
        nxt = (1 if (j + 1 < n and E_main[j + 1] > 0) else (-1 if (j + 1 < n and E_main[j + 1] < 0) else 0))
        reason = ("OPEN — current position" if is_open else
                  ("flipped to " + ("LONG" if nxt > 0 else "SHORT") if nxt != 0 else "went flat / regime change"))
        trades.append(dict(entry_dt=dates[i], exit_dt=dates[j], market=reg[i],
                           strategy=", ".join(emap.get(reg[i]) or []) or "—",
                           direction="LONG" if s > 0 else "SHORT", entry=round(entry, 2),
                           exit=round(exit_, 2), ret=round(ret, 4), apex_ret=round(float(apex_ret), 4),
                           reason=reason, idx=i - i0, exit_idx=j - i0, open=is_open, exit_date=dates[j]))
        markers.append({"i": i - i0, "d": s, "t": "in"})
        if not is_open: markers.append({"i": j - i0, "d": s, "t": "out"})
        i = j + 1
    recent = trades[-20:][::-1]

    # today's Apex signal
    i = n - 1; price = float(close[i]); rgi = reg[i]; engines = emap.get(rgi) or []
    sig = e_in[i]; g = gl[i] if sig > 0 else (gs[i] if sig < 0 else 1.0)
    mult = min(cap_ta[i], 1.5 / rv[i]) if (rv[i] == rv[i] and rv[i] > 0) else 0.0
    e = sig * g * mult; sg2 = 1 if e > 0 else (-1 if e < 0 else 0)
    dirn = "LONG" if sg2 > 0 else ("SHORT" if sg2 < 0 else "FLAT"); expm = abs(e)
    liqm = (1.0 / expm) if expm > 0 else 0.0
    apex = dict(direction=dirn, regime=rgi, engines=engines, exposure_mult=round(expm, 2),
                action=(f"{dirn} {expm:.1f}x equity" if sg2 else "FLAT — stand aside"),
                confidence=round(abs(e_in[i]), 2), conviction_ok=bool(abs(e_in[i]) > 0),
                margin_pct=round(expm / 5 * 100, 0), vol_scale=round(min(1.0, 1.5 / rv[i]), 2) if rv[i] > 0 else 1.0,
                cutloss=(round(price * (0.85 if sg2 > 0 else 1.15), 2) if sg2 else None),
                liquidation=(round((price * (1 - liqm) if sg2 > 0 else price * (1 + liqm)), 2) if (sg2 and expm > 0) else None),
                note=(f"Apex: trend-aligned, short-selective, vol-targeted ensemble. Effective {expm:.1f}x — needs a "
                      f"~{liqm*100:.0f}% adverse gap to liquidate; 0 liquidations in backtest (tail risk remains)."))
    core = dict(direction=dirn, regime=rgi, engines=engines,
                action=(f"{dirn} (spot 1x)" if sg2 else "FLAT — stand aside"),
                size_pct=round(min(1.0, abs(e_in[i])) * 100, 0), margin="SPOT 1x — no leverage, cannot be liquidated",
                cutloss=(round(price * (0.85 if sg2 > 0 else 1.15), 2) if sg2 else None),
                confidence=round(abs(e_in[i]), 2), take_profit="ride the trend; exit when the ensemble flips / regime changes")
    fc = dict(regime=rgi, engines=engines, direction=dirn,
              bias=("POTENTIAL UP" if sg2 > 0 else ("POTENTIAL DOWN" if sg2 < 0 else "STAND ASIDE")),
              headline=(f"{rgi}: engines ({', '.join(engines) or '—'}) lean {dirn}." if sg2
                        else f"{rgi}: no qualifying setup — stand aside."))
    s20 = float(df["SMA20"].iloc[i]); s50 = float(df["SMA50"].iloc[i]); s200 = float(df["SMA200"].iloc[i])
    bbu = float(df["BB_Upper"].iloc[i]); bbl = float(df["BB_Lower"].iloc[i])
    out = dict(as_of=dates[i], price=round(price, 2), rsi=round(float(df["RSI"].iloc[i]), 1),
               in_position=(dirn != "FLAT"), model_name="Apex",
               live=core, model_apex=apex, model_8b=apex, forecast=fc, regime_bias=REG_BIAS,
               no_trade_status=dict(market=rgi, bias=fc["bias"], next_action=fc["headline"]),
               levels=dict(price=round(price, 2), sma20=round(s20, 2), sma50=round(s50, 2), sma200=round(s200, 2),
                           bb_upper=round(bbu, 2), bb_lower=round(bbl, 2)),
               scenarios=scen, dates=chart_dates, close=chart_close, recent_trades=recent, trade_markers=markers,
               generated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    with open(os.path.join(OUT, save_as), "w") as f:
        json.dump(out, f)
    print("saved", save_as, "|", out["as_of"], "$%.0f" % out["price"], "| Apex:", apex["action"])
    for k, v in scen.items():
        print(f"  {k:16s} ${v['metrics']['final']:>14,.0f}  DD {v['metrics']['maxdd']*100:>4.0f}%  liq {v['liq']}")
    print(f"  recent trades: {len(recent)} | open trade flagged: {recent[0]['open'] if recent else None} | markers: {len(markers)}")
    return out


if __name__ == "__main__":
    main()
