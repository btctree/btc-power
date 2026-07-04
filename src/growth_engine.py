"""MAX B live engine -> out/results_live.json (the PRODUCTION model, chosen 2026-07-02; replaces the
plain Growth A). Max B = Growth A base (conviction ensemble |exp|>=0.4, EMA-5 + 0.15 deadband, cap 5x,
vol-target 1.5, VOL+FUND gates, dd-kill 30%) PLUS the protection stack:
  - 200-WEEK-MA FLOOR: no shorts while price < 200WMA (BTC bottoms at the 200WMA every cycle)
  - PI CYCLE de-risk: for 365 days after the 111DMA crosses above 2x350DMA (cycle-top alarm; fired
    2017-12-17 and 2021-04-12, zero false positives), exposure x0.5.
Verified @50bp: $500 -> $11,593,525 (2014+), maxDD -56%. @0bp $772M. Honest: 2024 ~0%, 2025 -38%
losing years remain; Pi Cycle rests on 2 historical events (failure mode inert). Scenarios = the SAME
Max B logic at 1x / 0bp / 50bp / 100bp. JSON keys unchanged (model_growth + apex/8b aliases).
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
    # --- Max B protection stack (BTC closes only; both arrays pre-shifted 1 day = no look-ahead) ---
    c_ = pd.Series(close)
    wma200 = c_.rolling(1400).mean()                               # 200-week MA
    below_200w = (c_ < wma200).shift(1).fillna(False).to_numpy()   # floor: no shorts below it
    m111 = c_.rolling(111).mean(); m350x2 = 2 * c_.rolling(350).mean()
    above = (m111 > m350x2).to_numpy()
    pi_alarm = np.zeros(n, bool); _lc = -10**9
    for i in range(1, n):
        if above[i] and not above[i - 1]: _lc = i
        if i - _lc <= 365: pi_alarm[i] = True
    pi_alarm = np.roll(pi_alarm, 1); pi_alarm[0] = False           # act next day
    pi_crosses = [dates[i] for i in range(1, n) if above[i] and not above[i - 1]]
    print("[maxb] Pi Cycle crosses:", pi_crosses, "| alarm active today:", bool(pi_alarm[n - 1]),
          "| price vs 200WMA:", "BELOW" if below_200w[n - 1] else "above")

    def sim(cap, slip, vt=1.5, dd_kill=0.30, band=0.15, fee=0.0005, maint=0.01, quant=False):
        """quant=True -> real-world margin: exposure snapped to whole levels 0/1x/2x/3x/4x/5x."""
        eqv = peak = 500.0; held = 0.0; eq = np.full(n, 500.0); E = np.zeros(n); liq = 0
        for i in range(i0, n):
            sig = e_in[i - 1]; g = gl[i - 1] if sig > 0 else (gs[i - 1] if sig < 0 else 1.0)
            if sig < 0 and below_200w[i]: g = 0.0                  # 200WMA floor: no shorts below
            if pi_alarm[i]: g *= 0.5                               # Pi Cycle bear-window de-risk
            if not (rv[i - 1] == rv[i - 1] and rv[i - 1] > 0): eq[i] = eqv; E[i] = held; continue
            e = sig * g * min(cap, vt / rv[i - 1])
            if dd_kill > 0 and eqv < peak * (1 - dd_kill): e *= 0.5
            if quant:
                # whole margin levels 0/1/2/3/4/5x with hysteresis: keep the HELD level until the
                # continuous target drifts >=0.75 of a step (or direction flips) — real-world re-leveling
                if held != 0 and np.sign(e) == np.sign(held) and abs(e - held) < 0.75:
                    e = held
                else:
                    e = np.sign(e) * min(5.0, np.floor(abs(e) + 0.5))
            elif band > 0 and abs(e - held) < band and not (e == 0 and held != 0): e = held
            adv = (-(low[i] / close[i - 1] - 1)) if e > 0 else ((high[i] / close[i - 1] - 1) if e < 0 else 0.0)
            if e != 0 and abs(e) * max(adv, 0) >= (1 - maint):
                eqv *= 0.01; liq += 1; held = 0.0; eq[i] = eqv; E[i] = 0.0; peak = max(peak, eqv); continue
            eqv *= (1 + e * (close[i] / close[i - 1] - 1)); eqv -= eqv * abs(e - held) * (fee + slip)
            held = e; eq[i] = max(eqv, 1e-9); E[i] = e; peak = max(peak, eqv)
        return eq, E, liq

    # NOTE on real-world margin: exchanges quantize the LEVERAGE SETTING (1x..5x), not the position
    # size — with a 5x margin setting any notional up to 5x equity is achievable (e.g. 1.9x = 38% of
    # funds posted as margin). So the continuous-size model is tradeable as-is. The strict
    # integer-EXPOSURE variant (quant=True) was measured: $644k @50bp / -71% DD (vs $3.54M / -59%)
    # because whole-step re-leveling multiplies turnover cost — documented, not used.
    specs = [("1x (spot, 50bp)", 1.0, 0.005, False, "Max B signal at 1x — no leverage (spot fractions allowed)"),
             ("Max B @0bp", 5.0, 0.0, False, "Max B perfect-fill (optimistic, untradeable)"),
             ("Max B @50bp", 5.0, 0.005, False, "Max B realistic (50bp slippage) — the headline"),
             ("Max B @100bp", 5.0, 0.010, False, "Max B stressed (100bp slippage)")]
    scen = {}; E_main = None; eq_main = None
    for name, cap, slip, quant, desc in specs:
        eq, E, liq = sim(cap, slip, quant=quant)
        if name == "Max B @50bp": E_main = E; eq_main = eq
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
                           entry_x=round(float(abs(E_main[i])), 2), max_x=round(float(np.max(np.abs(E_main[i:j + 1]))), 2),
                           exit=round(exit_, 2), ret=round(ret, 4), apex_ret=round(float(model_ret), 4),
                           reason=reason, idx=i - i0, exit_idx=j - i0, open=is_open, exit_date=dates[j]))
        markers.append({"i": i - i0, "d": s, "t": "in"})
        if not is_open: markers.append({"i": j - i0, "d": s, "t": "out"})
        i = j + 1
    recent = trades[-20:][::-1]

    # today Max B signal = the position ACTUALLY HELD by the @50bp path (stable until exit/flip/resize;
    # cut-loss & liquidation anchored to the ENTRY price, not today's).
    i = n - 1; price = float(close[i]); rgi = reg[i]; engines = emap.get(rgi) or []
    held = float(E_main[i]); sg2 = 1 if held > 0 else (-1 if held < 0 else 0)
    dirn = "LONG" if sg2 > 0 else ("SHORT" if sg2 < 0 else "FLAT"); expm = abs(held)
    k = i
    while k > 0 and np.sign(E_main[k - 1]) == sg2 and sg2 != 0: k -= 1
    entry_price = float(close[k]) if sg2 else None; entry_date = dates[k] if sg2 else None
    entry_x = round(float(abs(E_main[k])), 2) if sg2 else None      # size at ENTRY (equity multiple)
    liqm = (1.0 / expm) if expm > 1 else None                      # <=1x notional cannot be liquidated
    cutl = (round(entry_price * (0.85 if sg2 > 0 else 1.15), 2) if sg2 else None)
    liqp = (round(entry_price * (1 - liqm) if sg2 > 0 else entry_price * (1 + liqm), 2) if (sg2 and liqm) else None)
    # latest action = what changed on the most recent close (ENTER / ADD / REDUCE / EXIT / FLIP / HOLD)
    prev = float(E_main[i - 1]) if i > 0 else 0.0
    pv, cv = abs(prev), expm
    if np.sign(prev) == sg2 and abs(held - prev) < 1e-9:
        act_type, instr = "HOLD", (f"HOLD — keep {dirn} {cv:.1f}x (margin {cv/5*100:.0f}%); no action needed" if sg2 else "FLAT — no position, no action")
    elif prev == 0 and sg2 != 0:
        act_type, instr = "ENTER", f"ENTER — BUY BTC worth {cv:.1f}x your equity (margin {cv/5*100:.0f}% at 5x setting)" if sg2 > 0 else f"ENTER — SHORT BTC worth {cv:.1f}x your equity (margin {cv/5*100:.0f}%)"
    elif sg2 == 0 and prev != 0:
        act_type, instr = "EXIT", "EXIT — CLOSE the entire position; hold cash"
    elif np.sign(prev) != sg2:
        act_type, instr = "FLIP", f"FLIP — CLOSE the old position and open {dirn} {cv:.1f}x your equity (margin {cv/5*100:.0f}%)"
    elif cv > pv:
        act_type, instr = "ADD", f"ADD — {'BUY' if sg2 > 0 else 'SHORT'} +{cv-pv:.1f}x more notional ({pv:.1f}x -> {cv:.1f}x; margin {pv/5*100:.0f}% -> {cv/5*100:.0f}%)"
    else:
        act_type, instr = "REDUCE", f"REDUCE — close {pv-cv:.1f}x of notional ({pv:.1f}x -> {cv:.1f}x; margin {pv/5*100:.0f}% -> {cv/5*100:.0f}%)"
    latest_action = dict(type=act_type, date=dates[i], from_x=round(pv, 2), to_x=round(cv, 2), instruction=instr)
    growth = dict(direction=dirn, regime=rgi, engines=engines, exposure_mult=round(expm, 2),
                  action=(f"{dirn} {expm:.1f}x equity" if sg2 else "FLAT — stand aside"),
                  entry_price=(round(entry_price, 2) if entry_price else None), entry_date=entry_date,
                  entry_exposure=entry_x, prev_exposure=round(pv, 2), latest_action=latest_action,
                  instruction=instr,
                  signal_basis="daily close (UTC)", margin_setting="5x",
                  confidence=round(abs(e_in[i]), 2), conviction_ok=bool(abs(e_in[i]) > 0),
                  margin_pct=round(expm / 5 * 100, 0), vol_scale=round(min(1.0, 1.5 / rv[i]), 2) if rv[i] > 0 else 1.0,
                  cutloss=cutl, liquidation=liqp,
                  note=(f"Max B holds this position since {entry_date or '—'} (entry ${entry_price:,.0f}, daily "
                        f"close); the action stays until the model exits/flips or re-sizes — a new day does NOT "
                        f"re-price it. Cut-loss & liquidation are fixed from the entry price. How to trade "
                        f"{expm:.1f}x: set margin 5x and open a position worth {expm:.1f}x your equity "
                        f"(= {expm/5*100:.0f}% of funds posted as margin). Protection stack: 200WMA floor + Pi Cycle de-risk. "
                        f"Honest: maxDD -56%; losing years remain (2024/2025 in backtest)."
                        if sg2 else "Max B is FLAT — no position; waiting for the next daily-close signal. "
                        "Honest: maxDD -56%; losing years happen (2024/2025 in backtest)."))
    core = dict(direction=dirn, regime=rgi, engines=engines,
                action=(f"{dirn} (spot 1x)" if sg2 else "FLAT — stand aside"),
                size_pct=round(min(1.0, abs(e_in[i])) * 100, 0), margin="SPOT 1x — no leverage, cannot be liquidated",
                cutloss=cutl,   # same entry-anchored cut-loss as Max B (stops fixed from entry)
                confidence=round(abs(e_in[i]), 2), take_profit="ride the trend; exit when the ensemble flips / regime changes")
    natbias = REG_BIAS.get(rgi, "ASIDE"); posbias = "UP" if sg2 > 0 else ("DOWN" if sg2 < 0 else "ASIDE")
    conflict = bool(sg2) and natbias in ("UP", "DOWN") and natbias != posbias
    if not sg2:
        head = f"{rgi}: no qualifying setup — stand aside."
    elif conflict:
        head = (f"Holding {dirn} into a {rgi} market (trailing signal). Manage with the cut-loss "
                f"${cutl:,.0f} (fixed from entry); Max B exits when the ensemble flips.")
    else:
        head = f"{rgi}: ensemble leans {dirn} (engines {', '.join(engines) or '—'})."
    fc = dict(regime=rgi, engines=engines, direction=dirn,
              bias=("POTENTIAL UP" if sg2 > 0 else ("POTENTIAL DOWN" if sg2 < 0 else "STAND ASIDE")),
              headline=head)
    s20 = float(df["SMA20"].iloc[i]); s50 = float(df["SMA50"].iloc[i]); s200 = float(sma200[i])
    bbu = float(df["BB_Upper"].iloc[i]); bbl = float(df["BB_Lower"].iloc[i])
    out = dict(as_of=dates[i], price=round(price, 2), rsi=round(float(df["RSI"].iloc[i]), 1),
               in_position=(dirn != "FLAT"), model_name="Max B",
               live=core, model_growth=growth, model_apex=growth, model_8b=growth, forecast=fc, regime_bias=REG_BIAS,
               no_trade_status=dict(market=rgi, bias=fc["bias"], next_action=fc["headline"]),
               levels=dict(price=round(price, 2), sma20=round(s20, 2), sma50=round(s50, 2), sma200=round(s200, 2),
                           bb_upper=round(bbu, 2), bb_lower=round(bbl, 2)),
               scenarios=scen, dates=chart_dates, close=chart_close, recent_trades=recent, trade_markers=markers,
               generated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    with open(os.path.join(OUT, save_as), "w") as f:
        json.dump(out, f)
    print("saved", save_as, "|", out["as_of"], "$%.0f" % out["price"], "| Max B:", growth["action"])
    for k, v in scen.items():
        print(f"  {k:16s} ${v['metrics']['final']:>15,.0f}  DD {v['metrics']['maxdd']*100:>4.0f}%  liq {v['liq']}")
    print(f"  recent trades: {len(recent)} | open trade flagged: {recent[0]['open'] if recent else None} | markers: {len(markers)}")
    return out


if __name__ == "__main__":
    main()
