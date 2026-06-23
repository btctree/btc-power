"""Production engine — single source of truth for the live signal, honest production
curves, market forecast, and the optimistic-vs-realistic (slippage) comparison vs the
M1-vs-M5 project. Writes out/results_production.json (consumed by the mobile dashboard
and the Telegram bot).
"""
import os, json, datetime as dt
import numpy as np
import pandas as pd
import indicators as ind
import signals as sg
import backtest as bt
import regime_system as rs
import regime_switch_sim as rss
import trend_ride_sim as tr
import fast_search as fs
import compare_m1m5 as cm

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "out")
M1M5_UNLEV = 419697.90        # from their equity_curve_hist.json  e=839.4x
M1M5_LEV = 71300995.07        # their production leveraged n


def lev_cells(long_lev, short_lev, margin=0.5, cl=0.07):
    m = {(r, 1): (margin, long_lev, cl) for r in fs.LONG_REGIMES}
    for r in fs.SHORT_REGIMES:
        m[(r, -1)] = (margin, short_lev, cl)
    return m


def asym_cells(deploy_high, deploy_med, deploy_low):
    """our principled config as a per-cell map (longs full conf-scaled, shorts half/7%)."""
    m = {}
    dep = {"BULL_TREND": deploy_high, "BULL_PULLBACK": deploy_high, "CHOP_HIGHVOL": deploy_high,
           "BEAR_TREND": deploy_med, "BEAR_BOUNCE": deploy_med}
    for r in fs.LONG_REGIMES:
        m[(r, 1)] = (dep[r], 1, 0.10)
    for r in ["CHOP_HIGHVOL", "BEAR_TREND"]:
        m[(r, -1)] = (0.5 * dep[r], 1, 0.07)
    return m


def setup_combined():
    df = cm.prep(cm.build_combined())
    reg = rs.classify(df)
    sigs = sg.run_all(df, single_lookahead=False)
    memb = {k: bt.signals_to_position(sigs[k]) for k in rs.MEMBERS}
    fmap = {}
    p = os.path.join(HERE, "..", "data", "funding.csv")
    if os.path.exists(p):
        f = pd.read_csv(p); fmap = dict(zip(f["date"], f["funding_rate"]))
    fundarr = np.array([fmap.get(d, 0.0) for d in df["Date"]])
    fs._C = dict(close=df["close"].to_numpy(), high=df["high"].to_numpy(), low=df["low"].to_numpy(),
                 reg=reg, memb=memb, fundarr=fundarr, dates=df["Date"].tolist())
    return df, reg, memb


def idx_of(dates, d):
    return next(i for i, x in enumerate(dates) if x >= d)


def run(cells, lo, hi, slip=0.0, use_funding=False):
    eq, liq = fs.fast_sim(cells, lo, hi, slip=slip, use_funding=use_funding, start=500.0)
    return fs.metrics(eq), liq, eq


def main():
    df, reg, memb = setup_combined()
    dates = df["Date"].tolist(); n = len(df)
    i14 = idx_of(dates, "2014-01-01"); i17 = idx_of(dates, "2017-08-17")

    REAL_SLIP = 0.003   # ~30bp realistic spot slippage on stop fills

    # ---- honest production curves (the numbers to trade on) ----
    core = asym_cells(1.0, 0.7, 0.4)              # 1x conf-scaled (CORE)
    growth = asym_cells(1.0, 1.0, 1.0)            # 1x full (GROWTH)
    prod = {}
    for label, cells, start_i, slip in [
        ("CORE_1x_2017", core, i17, REAL_SLIP),
        ("GROWTH_1x_2017", growth, i17, REAL_SLIP),
        ("CORE_1x_2014", core, i14, REAL_SLIP),
        ("MODEST_2x_2017", lev_cells(2, 2, margin=0.5, cl=0.07), i17, REAL_SLIP),
    ]:
        m, liq, eq = run(cells, max(start_i, 260), n, slip=slip)
        prod[label] = dict(final=round(m["final"], 0), mult=round(m["final"] / 500, 1),
                           cagr=round(m["cagr"], 4), sharpe=round(m["sharpe"], 3),
                           maxdd=round(m["maxdd"], 4), calmar=round(m["calmar"], 3), liq=liq,
                           start=dates[max(start_i, 260)],
                           eq=([round(float(x), 2) for x in eq] if "2017" in label else None))

    # ---- optimistic vs realistic comparison (ours w/ M1vM5 leverage, from 2014) ----
    levc = lev_cells(5, 2, margin=0.5, cl=0.07)
    comp = {"m1m5": {"unlev": M1M5_UNLEV, "lev_optimistic": M1M5_LEV}}
    ours_lev = {}
    for slip, key in [(0.0, "perfect"), (0.005, "slip_50bp"), (0.015, "slip_150bp")]:
        m, liq, _ = run(levc, max(i14, 260), n, slip=slip)
        ours_lev[key] = dict(final=round(m["final"], 0), maxdd=round(m["maxdd"], 4), liq=liq)
    m1x, _, _ = run(asym_cells(1.0, 1.0, 1.0), max(i14, 260), n, slip=0.0)
    comp["ours"] = {"unlev_2014": round(m1x["final"], 0), "lev_2014": ours_lev}

    # ---- live signal + forecast (latest day, real Binance) ----
    i = n - 1
    rg = reg[i]; strat, kind, cs = rss.MAP.get(rg, (None, "flat", 0))
    active = strat if (strat and cs >= 0.5) else None
    m = memb[active][i] if active else 0
    d = 1 if m > 0 else (-1 if m < 0 else 0)
    price = float(df["close"].iloc[i])
    sma20 = float(df["SMA20"].iloc[i]); sma50 = float(df["SMA50"].iloc[i]); sma200 = float(df["SMA200"].iloc[i])
    bbu = float(df["BB_Upper"].iloc[i]); bbl = float(df["BB_Lower"].iloc[i]); rsi = float(df["RSI"].iloc[i])
    swing_hi = float(df["high"].iloc[i - 20:i + 1].max()); swing_lo = float(df["low"].iloc[i - 20:i + 1].min())
    conf_bucket = "High" if cs >= 1.8 else ("Med" if cs >= 1.0 else "Low/aside")
    size_pct = {"High": 100, "Med": 70, "Low/aside": 0}.get(conf_bucket, 0)
    action = "FLAT — stand aside"
    stop = None
    if active and d == 1:
        action = f"LONG via {active}"; stop = round(price * 0.90, 2)
    elif active and d == -1 and rg in ("CHOP_HIGHVOL", "BEAR_TREND"):
        action = f"SHORT via {active}"; stop = round(price * 1.07, 2); size_pct = int(size_pct * 0.5)

    bias = "BULLISH" if price > sma50 > sma200 else ("BEARISH" if price < sma50 < sma200 else "NEUTRAL")
    forecast = dict(
        bias=bias, regime=rg,
        arms_long_above=round(max(sma20, bbu * 0.999), 2),
        arms_short_below=round(min(sma20, bbl * 1.001), 2),
        note=("Uptrend intact while above SMA50 $%.0f; dips to SMA20 $%.0f are buy zones." % (sma50, sma20))
        if bias == "BULLISH" else
        ("Downtrend while below SMA50 $%.0f; bounces fade near SMA20 $%.0f." % (sma50, sma20))
        if bias == "BEARISH" else
        ("Rangebound; favor edges — buy near BB low $%.0f, lighten near BB high $%.0f." % (bbl, bbu))),

    out = dict(
        as_of=dates[i], price=round(price, 2),
        live=dict(action=action, regime=rg, active_strategy=(active or "STAND ASIDE"),
                  direction=("LONG" if d == 1 else "SHORT" if d == -1 else "FLAT"),
                  confidence=conf_bucket, confidence_score=round(cs, 2),
                  size_pct_equity=size_pct, margin_note="SPOT 1x (no leverage, no liquidation)",
                  trailing_stop=stop,
                  take_profit="none — ride trend; exit on reversal / regime-change / trailing stop",
                  rsi=round(rsi, 1)),
        forecast=forecast[0] if isinstance(forecast, tuple) else forecast,
        levels=dict(price=round(price, 2), sma20=round(sma20, 2), sma50=round(sma50, 2),
                    sma200=round(sma200, 2), bb_upper=round(bbu, 2), bb_lower=round(bbl, 2),
                    swing_high_20d=round(swing_hi, 2), swing_low_20d=round(swing_lo, 2)),
        production=prod, comparison=comp,
        regime_map={k: (v[0] or "STAND ASIDE") for k, v in rss.MAP.items()},
        dates_2017=[d for d in dates if d >= dates[max(i17, 260)]],
        generated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    with open(os.path.join(OUT, "results_production.json"), "w") as f:
        json.dump(out, f)
    _print(out)
    return out


def _print(o):
    print(f"\n=== PRODUCTION ENGINE — {o['as_of']}  BTC ${o['price']:,.0f} ===")
    L = o["live"]
    print(f"Signal: {L['action']} | regime {L['regime']} | conf {L['confidence']} | size {L['size_pct_equity']}% | stop {L['trailing_stop']}")
    print(f"Forecast: {o['forecast']['bias']} — {o['forecast']['note']}")
    print("\nHonest production curves (real ~30bp slippage, $500 start):")
    for k, p in o["production"].items():
        print(f"  {k:16s} ${p['final']:>12,.0f} ({p['mult']:>7.0f}x) CAGR {p['cagr']*100:>5.0f}% Sharpe {p['sharpe']:.2f} DD {p['maxdd']*100:.0f}% liq {p['liq']} [from {p['start']}]")
    c = o["comparison"]
    print(f"\nOptimistic vs realistic (5x/2x leverage from 2014):")
    print(f"  M1vM5 reported: unlev ${c['m1m5']['unlev']:,.0f} | leveraged(optimistic) ${c['m1m5']['lev_optimistic']:,.0f}")
    print(f"  OURS unlev ${c['ours']['unlev_2014']:,.0f} | lev perfect ${c['ours']['lev_2014']['perfect']['final']:,.0f}"
          f" | 50bp ${c['ours']['lev_2014']['slip_50bp']['final']:,.0f} | 150bp ${c['ours']['lev_2014']['slip_150bp']['final']:,.0f}")
    print("\nsaved out/results_production.json")


if __name__ == "__main__":
    main()
