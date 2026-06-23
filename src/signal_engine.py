"""PRODUCTION signal engine — the final BTC signal product.

Strategy (validated): 'Consensus Long' ensemble = clipped mean of all 9 ported
strategies' positions, LONG-ONLY (shorts -> flat). The position fraction (0-100%)
is also the confidence / size score. Chosen by walk-forward robustness:
full Sharpe 1.28, maxDD -28%, robust in both halves (H1 1.41 / H2 1.17).

Outputs:
  ../out/results_final.json  -> for the dashboard
  prints a Telegram-style alert (title -> state -> sections -> levels -> disclaimer)
No look-ahead anywhere; DSAM uses the honest (past) Single. Fees 5bp/side in backtest.
"""
import os, json, datetime as dt
import numpy as np
import pandas as pd
import indicators as ind
import signals as sg
import backtest as bt

HERE = os.path.dirname(__file__)
FEE = 0.0005
ANN = 365
NAMES = {"OBV": "OBV trend-reversal", "DSAM": "DSAM dual-SMA momentum",
         "MACD": "MACD reversal", "RSI": "RSI breakout", "EMA": "EMA12/26 cross",
         "BB": "Bollinger breakout", "MFI": "MFI reversal", "OBV_ROC": "OBV vs ROC",
         "MACD_SIG": "MACD vs Signal"}
MEMBERS = list(NAMES.keys())


def load():
    raw = pd.read_csv(os.path.join(HERE, "..", "data", "btc_daily.csv"))
    df = ind.compute(raw[["date", "close", "volume", "high", "low"]]
                     .rename(columns={"date": "Date"})).reset_index(drop=True)
    df["SMA50"] = df["close"].rolling(50).mean()
    return df


def consensus_position(df):
    sigs = sg.run_all(df, single_lookahead=False)
    memb = {k: bt.signals_to_position(sigs[k]) for k in MEMBERS}
    mean_pos = np.mean([memb[k] for k in MEMBERS], axis=0)
    pos = np.clip(mean_pos, 0.0, None)         # long-only consensus
    return pos, memb, sigs


def bt_position(close, pos, fee=FEE):
    close = np.asarray(close, float); pos = np.asarray(pos, float)
    n = len(close)
    px = np.zeros(n); px[1:] = close[1:] / close[:-1] - 1
    held = np.zeros(n); held[1:] = pos[:-1]
    turn = np.zeros(n); turn[1:] = np.abs(pos[1:] - pos[:-1]); turn[0] = abs(pos[0])
    ret = held * px - turn * fee
    eq = np.cumprod(1 + ret)
    return ret, eq


def metr(ret, eq):
    years = len(eq) / ANN
    cagr = eq[-1] ** (1 / years) - 1 if eq[-1] > 0 else float("nan")
    sharpe = ret.mean() * ANN / (ret.std(ddof=1) * np.sqrt(ANN)) if ret.std() > 0 else float("nan")
    peak = np.maximum.accumulate(eq); maxdd = (eq / peak - 1).min()
    calmar = cagr / abs(maxdd) if maxdd < 0 else float("nan")
    down = ret[ret < 0].std(ddof=1) * np.sqrt(ANN)
    sortino = ret.mean() * ANN / down if down > 0 else float("nan")
    return dict(total=eq[-1] - 1, cagr=cagr, sharpe=sharpe, sortino=sortino,
                maxdd=maxdd, calmar=calmar, final=float(eq[-1]))


def regime(df, i):
    c = df["close"].iloc[i]; sma20 = df["SMA20"].iloc[i]; sma50 = df["SMA50"].iloc[i]
    bbu = df["BB_Upper"].iloc[i]; bbl = df["BB_Lower"].iloc[i]; rsi = df["RSI"].iloc[i]
    bbw = (bbu - bbl) / sma20 if sma20 else 0
    bbw_series = ((df["BB_Upper"] - df["BB_Lower"]) / df["SMA20"]).iloc[max(0, i - 365):i + 1]
    bbw_med = bbw_series.median()
    ext = (c - sma20) / sma20 if sma20 else 0
    chg14 = (c - df["close"].iloc[i - 14]) / df["close"].iloc[i - 14] if i >= 14 else 0
    rng14 = (df["close"].iloc[i - 14:i + 1].max() - df["close"].iloc[i - 14:i + 1].min()) / c
    if bbw > bbw_med * 1.15 and abs(ext) > 0.04:
        return ("TREND ▲" if ext > 0 else "TREND ▼"), bbw, ext
    if rng14 > 0.12 and abs(chg14) < 0.03:
        return "TOXIC (chop, no follow-through)", bbw, ext
    if 38 <= rsi <= 62 and bbw < bbw_med:
        return "RANGING", bbw, ext
    return ("LEANING UP" if ext > 0 else "LEANING DOWN"), bbw, ext


def main():
    df = load()
    close = df["close"].to_numpy()
    pos, memb, sigs = consensus_position(df)
    ret, eq = bt_position(close, pos)
    m_full = metr(ret, eq)
    mid = len(df) // 2
    m_h1 = metr(*bt_position(close[:mid], pos[:mid]))
    m_h2 = metr(*bt_position(close[mid:], pos[mid:]))
    bh = bt.buyhold_metrics(close)

    # per-strategy honest metrics (full)
    per = {}
    for k in MEMBERS:
        r = bt.backtest(close, sigs[k], fee_rate=FEE)
        tr = bt.trades_from_signals(close, sigs[k])
        mm = bt.metrics(r, tr)
        per[k] = mm

    # ---- current live state ----
    i = len(df) - 1
    last = df.iloc[i]
    conf = float(pos[i])                      # 0..1 net-long consensus
    n_long = int(sum(1 for k in MEMBERS if memb[k][i] > 0))
    n_short = int(sum(1 for k in MEMBERS if memb[k][i] < 0))
    n_flat = len(MEMBERS) - n_long - n_short
    reg, bbw, ext = regime(df, i)
    votes = {NAMES[k]: ("LONG" if memb[k][i] > 0 else ("SHORT" if memb[k][i] < 0 else "FLAT"))
             for k in MEMBERS}
    # action label
    prev_conf = float(pos[i - 1])
    if conf >= 0.5:
        action = "STRONG LONG"
    elif conf >= 0.2:
        action = "LONG (scaled)"
    elif conf > 0:
        action = "LIGHT LONG"
    else:
        action = "FLAT / STAND ASIDE"
    delta = "↑ adding" if conf > prev_conf + 1e-9 else ("↓ trimming" if conf < prev_conf - 1e-9 else "→ steady")

    # key levels
    sma20 = float(last["SMA20"]); sma50 = float(last["SMA50"])
    bbu = float(last["BB_Upper"]); bbl = float(last["BB_Lower"])
    swing_hi = float(df["high"].iloc[i - 20:i + 1].max())
    swing_lo = float(df["low"].iloc[i - 20:i + 1].min())
    price = float(last["close"])

    out = {
        "as_of": str(last["Date"]),
        "price": round(price, 2),
        "action": action, "delta": delta,
        "confidence": round(conf, 3),
        "votes_long": n_long, "votes_short": n_short, "votes_flat": n_flat,
        "regime": reg, "rsi": round(float(last["RSI"]), 1),
        "bb_width_pct": round(bbw * 100, 1), "ext_from_sma20_pct": round(ext * 100, 1),
        "levels": {"price": round(price, 2), "sma20": round(sma20, 2), "sma50": round(sma50, 2),
                   "bb_upper": round(bbu, 2), "bb_lower": round(bbl, 2),
                   "swing_high_20d": round(swing_hi, 2), "swing_low_20d": round(swing_lo, 2)},
        "votes": votes,
        "ensemble_metrics": {"full": m_full, "h1": m_h1, "h2": m_h2},
        "buyhold": bh,
        "per_strategy": per,
        "dates": df["Date"].tolist(),
        "close": [round(float(x), 2) for x in close],
        "equity": [round(float(x), 4) for x in eq],
        "pos": [round(float(x), 3) for x in pos],
        "bh_equity": [round(float(x), 4) for x in (close / close[0])],
        "names": NAMES,
    }
    with open(os.path.join(HERE, "..", "out", "results_final.json"), "w") as f:
        json.dump(out, f)

    print_alert(out)
    return out


def _pct(x):
    return f"{x*100:,.1f}%" if x == x else "n/a"


def print_alert(o):
    L = o["levels"]
    print("=" * 56)
    print(f"📊 BTC CONSENSUS SIGNAL — {o['as_of']}")
    print(f"Price ${o['price']:,.0f}  |  {o['action']}  ({o['delta']})")
    print("-" * 56)
    print(f"Confidence: {o['confidence']*100:.0f}% net-long consensus "
          f"({o['votes_long']} long / {o['votes_flat']} flat / {o['votes_short']} short of 9)")
    print(f"Regime: {o['regime']}   RSI {o['rsi']}   BBwidth {o['bb_width_pct']}%   "
          f"ext vs SMA20 {o['ext_from_sma20_pct']:+}%")
    print("-" * 56)
    print("Strategy votes:")
    for name, v in o["votes"].items():
        mark = "🟢" if v == "LONG" else ("🔴" if v == "SHORT" else "⚪")
        print(f"  {mark} {name:22s} {v}")
    print("-" * 56)
    mf = o["ensemble_metrics"]["full"]; bh = o["buyhold"]
    print(f"Backtest (2017-2026, 5bp fees, no look-ahead):")
    print(f"  Ensemble: {_pct(mf['total'])} total | Sharpe {mf['sharpe']:.2f} | "
          f"maxDD {_pct(mf['maxdd'])} | Calmar {mf['calmar']:.2f}")
    print(f"  Buy&Hold: {_pct(bh['total_return'])} total | Sharpe {bh['sharpe']:.2f} | "
          f"maxDD {_pct(bh['maxdd'])} | Calmar {bh['calmar']:.2f}")
    print("-" * 56)
    print(f"Levels: spot ${L['price']:,.0f} | SMA20 ${L['sma20']:,.0f} | SMA50 ${L['sma50']:,.0f} | "
          f"BB ${L['bb_lower']:,.0f}-${L['bb_upper']:,.0f} | 20d range ${L['swing_low_20d']:,.0f}-${L['swing_high_20d']:,.0f}")
    print("-" * 56)
    print("⚠️ Daily-close signal, BTCUSDT spot. Backtest is hypothetical, no funding/")
    print("   slippage modeled; long-only. Not financial advice — validate before risking capital.")
    print("=" * 56)


if __name__ == "__main__":
    main()
