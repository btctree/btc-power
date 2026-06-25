"""Live data engine v2 -> out/results_live.json (feeds dashboard v2 + Telegram).
Produces, over the full 2014+ history (CoinGecko pre-2017 + Binance):
 - 5 equity scenarios: Spot 1x, Lev perfect, Lev 50bp, Lev 100bp, Lev 150bp
 - daily dates + price for the interactive chart
 - recent-20 completed trades (with no-lev & lev PnL, minute timestamps where available)
 - live signal + forecast + no-trade next-action status
One strategy set (regime-switch, conf-scaled, asymmetric shorts, 10%/7% trailing);
scenarios differ only by leverage (5x long / 2x short) and assumed stop-fill slippage.
"""
import os, json, datetime as dt
import numpy as np
import pandas as pd
import compare_m1m5 as cm
import regime_system as rs
import regime_switch_sim as rss
import signals as sg
import backtest as bt
import fast_search as fs
import regime_v2 as r2
import stable_combo as sc

HERE = os.path.dirname(__file__)


def ensemble_ctx(df, memb):
    """Shared v2-ensemble context (regime_v2 + eligible engines + exposure series) used by
    BOTH the Returns scenarios and the live signal, so the chart matches the signal."""
    d = df.copy()
    h, l, c = d["high"], d["low"], d["close"]
    d["ATRpct"] = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1).rolling(14).mean() / c
    d["ADX"], d["PDI"], d["MDI"] = r2.wilder_adx(h, l, c, 14)
    reg = r2.classify(d)
    emap = sc.eligible_map(d, reg, memb)
    exp = sc.exposure_series(d, reg, memb, emap)
    return reg, emap, exp


def compute_models(df, memb, ctx=None, conv=0.4, lev=5.0, vol_target=0.60):
    """Both signals from the SAME diversified regime_v2 ensemble so they always agree on
    direction: CORE = spot 1x, 8B = 5x leverage (conviction-filtered)."""
    c = df["close"]
    reg, emap, exp = ctx if ctx else ensemble_ctx(df, memb)
    i = len(df) - 1
    price = float(c.iloc[i]); e = float(exp[i]); rgi = reg[i]; engines = emap.get(rgi) or []
    rv = float(pd.Series(c.pct_change()).rolling(20).std().iloc[i] * np.sqrt(365))
    vscale = min(1.0, vol_target / rv) if rv > 0 else 1.0
    ef = e if abs(e) >= conv else 0.0                      # conviction filter
    sgn = 1 if ef > 0 else (-1 if ef < 0 else 0)
    dirn = "LONG" if sgn > 0 else ("SHORT" if sgn < 0 else "FLAT")
    # CORE spot 1x: same direction, size = |exposure| of equity, no leverage/liquidation
    core_size = round(abs(ef) * vscale * 100, 0)
    core = dict(direction=dirn, regime=rgi, engines=engines,
                action=(f"{dirn} (spot 1x)" if sgn else "FLAT — stand aside"),
                size_pct=core_size, margin="SPOT 1x — no leverage, cannot be liquidated",
                cutloss=(round(price * (0.85 if sgn > 0 else 1.15), 2) if sgn else None),
                confidence=round(abs(e), 2),
                take_profit="ride the regime; exit when the ensemble flips or regime changes")
    # 8B model: 5x leverage on the same exposure
    tgt = ef * lev * vscale
    m8b = dict(direction=dirn, regime=rgi, engines=engines,
               exposure_mult=round(tgt, 2),
               action=(f"{dirn} {abs(tgt):.1f}x equity" if sgn else "FLAT — stand aside"),
               confidence=round(abs(e), 2), conviction_ok=bool(abs(e) >= conv),
               margin_pct=round(abs(tgt) / lev * 100, 0), vol_scale=round(vscale, 2),
               cutloss=(round(price * (0.85 if sgn > 0 else 1.15), 2) if sgn else None),     # -15%
               liquidation=(round(price * (0.80 if sgn > 0 else 1.20), 2) if sgn else None),  # ~-20% at 5x
               note="0 liquidations in this backtest, but at 5x a >20% intraday gap COULD liquidate (future tail risk).")
    forecast = dict(regime=rgi, engines=engines, direction=dirn,
                    bias=("POTENTIAL UP" if sgn > 0 else ("POTENTIAL DOWN" if sgn < 0 else "STAND ASIDE")),
                    headline=(f"{rgi}: engines ({', '.join(engines) or '—'}) lean {dirn}." if sgn
                              else f"{rgi}: no qualifying setup — stand aside (confidence {abs(e):.2f} < 0.40)."))
    return dict(core=core, m8b=m8b, forecast=forecast, regime=rgi, exposure=round(e, 3), price=round(price, 2))
OUT = os.path.join(HERE, "..", "out")
CONF = {"BULL_TREND": 1.0, "BULL_PULLBACK": 1.0, "CHOP_HIGHVOL": 1.0, "BEAR_TREND": 0.7, "BEAR_BOUNCE": 0.7}
LONG_REGIMES = ["BULL_TREND", "BULL_PULLBACK", "CHOP_HIGHVOL", "BEAR_TREND", "BEAR_BOUNCE"]
SHORT_REGIMES = ["CHOP_HIGHVOL", "BEAR_TREND"]


def build_map(lev_l, lev_s):
    m = {(r, 1): (CONF[r], lev_l, 0.10) for r in LONG_REGIMES}
    for r in SHORT_REGIMES:
        m[(r, -1)] = (CONF[r] * 0.5, lev_s, 0.07)
    return m


def setup():
    df = cm.prep(cm.build_combined())
    reg = rs.classify(df)
    sigs = sg.run_all(df, single_lookahead=False)
    memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
    p = os.path.join(HERE, "..", "data", "funding.csv")
    fmap = dict(zip(*[pd.read_csv(p)[c] for c in ["date", "funding_rate"]])) if os.path.exists(p) else {}
    fs._C = dict(close=df["close"].to_numpy(), high=df["high"].to_numpy(), low=df["low"].to_numpy(),
                 reg=reg, memb=memb, fundarr=np.array([fmap.get(d, 0.0) for d in df["Date"]]),
                 dates=df["Date"].tolist())
    return df, reg, memb


def gen_trades(i0, n):
    """Daily-fidelity trade log (no .npz needed -> works in CI). Tracks no-lev (1x)
    and lev (5x/2x) equity so each trade carries both PnLs. SPOT sizing = conf-scaled,
    asymmetric shorts; 10%/7% trailing stop via daily high/low."""
    C = fs._C; close = C["close"]; high = C["high"]; low = C["low"]; reg = C["reg"]
    memb = C["memb"]; dates = C["dates"]; FEE = 0.0005
    eq_nm = eq_wm = 500.0; pos = None; trades = []
    for i in range(i0, n):
        rg = reg[i]
        if pos is not None:
            d = pos["dir"]; cl = pos["cl"]; ex = False; fillp = None; reason = None
            if d == 1:
                if low[i] <= pos["stop"]:
                    fillp = pos["stop"]; reason = "Trailing stop"; ex = True
                elif high[i] > pos["hi"]:
                    pos["hi"] = high[i]; pos["stop"] = max(pos["stop"], pos["hi"] * (1 - cl))
            else:
                if high[i] >= pos["stop"]:
                    fillp = pos["stop"]; reason = "Trailing stop"; ex = True
                elif low[i] < pos["lo"]:
                    pos["lo"] = low[i]; pos["stop"] = min(pos["stop"], pos["lo"] * (1 + cl))
            if not ex:
                m = memb[pos["strat"]][i]
                su = (rg in rss.TREND_GROUP) if (pos["kind"] == "trend" and pos["regime"] in rss.TREND_GROUP) \
                    else ((rg in rss.BEAR_GROUP) if pos["regime"] in rss.BEAR_GROUP else rg == pos["regime"])
                sigx = (m * d < 0) if pos["kind"] == "trend" else (m * d <= 0)
                if (not su) or sigx:
                    fillp = close[i]; reason = "Regime-change" if not su else "Signal-exit"; ex = True
            if ex:
                ret = (fillp / pos["entry"] - 1.0) * d
                pnl_nm = pos["nn"] * ret - pos["nn"] * FEE * 2; eq_nm += pnl_nm
                pnl_wm = pos["nw"] * ret - pos["nw"] * FEE * 2; eq_wm += pnl_wm
                trades.append(dict(entry_dt=pos["edt"], exit_dt=dates[i], market=pos["regime"],
                                   strategy=pos["strat"], direction="LONG" if d == 1 else "SHORT",
                                   confidence=pos["bucket"], entry=round(pos["entry"], 2),
                                   exit=round(float(fillp), 2), ret=round(ret, 4),
                                   cutloss_lvl=round(pos["cutloss"], 2), pnl_nm=round(pnl_nm, 2),
                                   pnl_wm=round(pnl_wm, 2), reason=reason))
                pos = None
        if pos is None and eq_nm > 1:
            strat, kind, cs = rss.MAP.get(rg, (None, "flat", 0))
            if strat and cs >= 0.5:
                m = memb[strat][i]; d = 1 if m > 0 else (-1 if m < 0 else 0)
                if d == -1 and rg not in SHORT_REGIMES:
                    d = 0
                if d != 0:
                    bk = "High" if cs >= 1.8 else "Med"; dep = CONF[rg] * (0.5 if d == -1 else 1.0)
                    cl = 0.10 if d == 1 else 0.07; lev = 5 if d == 1 else 2
                    entry = close[i]; nn = dep * eq_nm; nw = dep * eq_wm * lev
                    cutloss = entry * (1 - cl) if d == 1 else entry * (1 + cl)
                    pos = dict(entry=entry, edt=dates[i], dir=d, strat=strat, kind=kind, regime=rg,
                               bucket=bk, cl=cl, hi=entry, lo=entry, stop=cutloss, cutloss=cutloss, nn=nn, nw=nw)
    return trades


def metrics(eq):
    eq = np.asarray(eq, float)
    if eq[-1] <= 0:
        return dict(final=float(eq[-1]), cagr=-1.0, sharpe=float("nan"), maxdd=-1.0)
    r = np.diff(eq) / eq[:-1]; r = r[np.isfinite(r)]
    yrs = len(eq) / 365
    return dict(final=float(eq[-1]), cagr=(eq[-1] / 500) ** (1 / yrs) - 1,
                sharpe=float(r.mean() * 365 / (r.std(ddof=1) * np.sqrt(365))) if r.std() > 0 else float("nan"),
                maxdd=float((eq / np.maximum.accumulate(eq) - 1).min()))


def main():
    df, reg, memb = setup()
    dates = df["Date"].tolist(); n = len(df)
    i0 = 260
    # v2 ensemble (same model as the live signal) -> Returns curves match the deployed signal
    reg2, emap2, exp_raw = ensemble_ctx(df, memb)
    expf = np.where(np.abs(exp_raw) >= 0.4, exp_raw, 0.0)      # conviction filter (matches 8B)
    scen = {}
    specs = [("Core 1x", 1, 0.003, "Core spot 1x — the safe, tradeable curve"),
             ("8B 5x (0bp)", 5, 0.0, "8B model perfect-fill — optimistic"),
             ("8B 5x · 50bp", 5, 0.005, "8B at 50bp slippage"),
             ("8B 5x · 150bp", 5, 0.015, "8B at 150bp slippage (crisis)")]
    for name, lev, slip, desc in specs:
        eq, liq = sc.simulate(df, expf, lev=lev, slip=slip, vol_target=0.60, dd_kill=0.30)
        eq = eq[i0:]
        m = metrics(eq)
        scen[name] = dict(eq=[round(float(x), 2) for x in eq],
                          metrics={k: (None if (isinstance(v, float) and v != v) else round(float(v), 4)) for k, v in m.items()},
                          liq=int(liq), slip=slip, desc=desc)
    chart_dates = dates[i0:n]
    chart_close = [round(float(x), 2) for x in df["close"].to_numpy()[i0:n]]

    # recent-20 trades (daily-fidelity; CI-safe, no .npz needed)
    trs = gen_trades(i0, n)
    recent = []
    for t in trs[-20:][::-1]:
        recent.append(dict(entry_dt=t["entry_dt"], exit_dt=t["exit_dt"], market=t["market"],
                           strategy=t["strategy"], direction=t["direction"], conf=t["confidence"],
                           entry=round(float(t["entry"]), 2), exit=round(float(t["exit"]), 2),
                           ret=round(float(t["ret"]), 4), cutloss=round(float(t["cutloss_lvl"]), 2),
                           pnl_nolev=round(float(t["pnl_nm"]), 2), pnl_lev=round(float(t["pnl_wm"]), 2),
                           reason=t["reason"], exit_date=t["exit_dt"][:10]))

    # both signals from the SAME ensemble (CORE 1x + 8B 5x) -> always agree on direction
    M = compute_models(df, memb, ctx=(reg2, emap2, exp_raw))
    core = M["core"]; m8b = M["m8b"]; fc = M["forecast"]
    i = n - 1; price = float(df["close"].iloc[i])
    s20 = float(df["SMA20"].iloc[i]); s50 = float(df["SMA50"].iloc[i]); s200 = float(df["SMA200"].iloc[i])
    bbu = float(df["BB_Upper"].iloc[i]); bbl = float(df["BB_Lower"].iloc[i])
    in_pos = core["direction"] != "FLAT"
    # regime -> directional bias map (for the colour-coded forecast playbook)
    REG_BIAS = {"STRONG_UP": "UP", "TREND_UP": "UP", "PULLBACK_UP": "UP", "BOUNCE_DOWN": "UP",
                "STRONG_DOWN": "DOWN", "TREND_DOWN": "DOWN", "CHOP_HIVOL": "ASIDE", "RANGE": "ASIDE", "NEUTRAL": "ASIDE"}

    out = dict(
        as_of=dates[i], price=round(price, 2), rsi=round(float(df["RSI"].iloc[i]), 1),
        in_position=in_pos,
        live=core, model_8b=m8b, forecast=fc,
        regime_bias=REG_BIAS,
        no_trade_status=dict(market=M["regime"], bias=fc["bias"], next_action=fc["headline"]),
        levels=dict(price=round(price, 2), sma20=round(s20, 2), sma50=round(s50, 2), sma200=round(s200, 2),
                    bb_upper=round(bbu, 2), bb_lower=round(bbl, 2)),
        scenarios=scen, dates=chart_dates, close=chart_close, recent_trades=recent,
        generated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    with open(os.path.join(OUT, "results_live.json"), "w") as f:
        json.dump(out, f)
    print("saved results_live.json |", out["as_of"], "$%.0f" % out["price"], "|", out["live"]["action"])
    for k, v in scen.items():
        print(f"  {k:12s} ${v['metrics']['final']:>14,.0f}  CAGR {v['metrics']['cagr']*100:>5.0f}%  DD {v['metrics']['maxdd']*100:.0f}%")
    print(f"  recent trades: {len(recent)}  chart points: {len(chart_dates)}")
    return out


if __name__ == "__main__":
    main()
