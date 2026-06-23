"""Main analysis:
 A) Parity: reproduce user's $-per-position sums on the Excel (CoinGecko) data.
 B) Honest: run %-equity backtest on Binance daily data, full + walk-forward halves.
"""
import os, json
import numpy as np
import pandas as pd
import indicators as ind
import signals as sg
import backtest as bt

HERE = os.path.dirname(__file__)
NAMES = {"OBV": "OBV trend-reversal", "DSAM": "DSAM dual-SMA momentum",
         "MACD": "MACD reversal (long-only)", "RSI": "RSI breakout",
         "EMA": "EMA12/26 cross", "BB": "Bollinger breakout",
         "MFI": "MFI reversal", "OBV_ROC": "OBV vs ROC", "MACD_SIG": "MACD vs Signal"}


def load_excel():
    raw = pd.read_csv(os.path.join(HERE, "..", "data", "excel_indicators.csv"))
    raw = raw.rename(columns={"Close": "close", "Volumn": "volume"})
    df = ind.compute(raw[["Date", "close", "volume"]].copy()).reset_index(drop=True)
    return raw, df


def load_binance():
    raw = pd.read_csv(os.path.join(HERE, "..", "data", "btc_daily.csv"))
    df = ind.compute(raw[["date", "close", "volume"]].rename(columns={"date": "Date"})).reset_index(drop=True)
    return df


def parity():
    raw, df = load_excel()
    sigs = sg.run_all(df, single_lookahead=True)
    user = {"OBV": 161015.37, "DSAM": 195320.99, "MACD": 62787.60, "RSI": 89050.43,
            "EMA": 132920.78, "BB": 99802.73, "MFI": 79992.91, "OBV_ROC": 96719.09,
            "MACD_SIG": 146957.22}
    print("=== A) PARITY: my $-sum vs user's Excel cached $-sum (CoinGecko data) ===")
    print(f"{'strategy':12s} {'my $sum':>14s} {'user $sum':>14s} {'diff':>12s}")
    for k in sigs:
        tr = bt.trades_from_signals(df["close"].to_numpy(), sigs[k])
        mysum = sum(t["dollars"] for t in tr)
        print(f"{k:12s} {mysum:>14.2f} {user[k]:>14.2f} {mysum-user[k]:>12.2f}")


def run_set(df, sigs, fee=0.0005, label=""):
    close = df["close"].to_numpy()
    bh = bt.buyhold_metrics(close)
    rows = []
    for k in sigs:
        res = bt.backtest(close, sigs[k], fee_rate=fee)
        tr = bt.trades_from_signals(close, sigs[k])
        m = bt.metrics(res, tr)
        rows.append((k, m, res))
    return rows, bh


def fmt_pct(x):
    return f"{x*100:,.1f}%" if x == x else "  n/a"


def print_table(rows, bh, title):
    print(f"\n=== {title} ===")
    print(f"BUY&HOLD: total {fmt_pct(bh['total_return'])}  CAGR {fmt_pct(bh['cagr'])}  "
          f"Sharpe {bh['sharpe']:.2f}  maxDD {fmt_pct(bh['maxdd'])}  Calmar {bh['calmar']:.2f}")
    print(f"{'strategy':10s} {'tot.ret':>10s} {'CAGR':>8s} {'Sharpe':>7s} {'Sortino':>8s} "
          f"{'maxDD':>8s} {'Calmar':>7s} {'win%':>6s} {'PF':>5s} {'#tr':>5s} {'expo':>6s}")
    for k, m, _ in rows:
        print(f"{k:10s} {fmt_pct(m['total_return']):>10s} {fmt_pct(m['cagr']):>8s} "
              f"{m['sharpe']:>7.2f} {m['sortino']:>8.2f} {fmt_pct(m['maxdd']):>8s} "
              f"{m['calmar']:>7.2f} {m['winrate']*100:>5.0f}% {m['profit_factor']:>5.2f} "
              f"{m['n_trades']:>5d} {m['exposure']*100:>5.0f}%")


def honest():
    df = load_binance()
    print(f"\n=== B) HONEST BACKTEST on BINANCE daily {df['Date'].iloc[0]}..{df['Date'].iloc[-1]} "
          f"({len(df)} days), fees 5bp/side, no look-ahead ===")
    sigs = sg.run_all(df, single_lookahead=True)        # faithful (DSAM uses look-ahead Single)
    sigs_nl = sg.run_all(df, single_lookahead=False)    # DSAM honest variant
    rows, bh = run_set(df, sigs)
    print_table(rows, bh, "FULL SAMPLE 2017-2026 (faithful, incl. DSAM look-ahead)")

    # DSAM honest comparison
    close = df["close"].to_numpy()
    res_la = bt.backtest(close, sigs["DSAM"]); m_la = bt.metrics(res_la, bt.trades_from_signals(close, sigs["DSAM"]))
    res_nl = bt.backtest(close, sigs_nl["DSAM"]); m_nl = bt.metrics(res_nl, bt.trades_from_signals(close, sigs_nl["DSAM"]))
    print(f"\n  DSAM look-ahead impact: with-lookahead tot {fmt_pct(m_la['total_return'])} "
          f"Sharpe {m_la['sharpe']:.2f}  |  honest(no-lookahead) tot {fmt_pct(m_nl['total_return'])} "
          f"Sharpe {m_nl['sharpe']:.2f}")

    # walk-forward halves
    mid = len(df) // 2
    d1 = df.iloc[:mid].reset_index(drop=True)
    d2 = df.iloc[mid:].reset_index(drop=True)
    s1 = sg.run_all(d1, single_lookahead=True)
    s2 = sg.run_all(d2, single_lookahead=True)
    r1, b1 = run_set(d1, s1); r2, b2 = run_set(d2, s2)
    print_table(r1, b1, f"FIRST HALF {d1['Date'].iloc[0]}..{d1['Date'].iloc[-1]}")
    print_table(r2, b2, f"SECOND HALF {d2['Date'].iloc[0]}..{d2['Date'].iloc[-1]}")

    # save full-sample equity + metrics for dashboard
    out = {"dates": df["Date"].tolist(), "close": df["close"].round(2).tolist(),
           "buyhold": {k: (None if v != v else round(v, 4)) for k, v in bh.items()},
           "strategies": {}}
    for k, m, res in rows:
        out["strategies"][k] = {
            "name": NAMES[k],
            "metrics": {kk: (None if (isinstance(v, float) and v != v) else round(float(v), 4)) for kk, v in m.items()},
            "equity": [round(float(x), 4) for x in res["equity"]],
            "pos": [int(x) for x in res["pos"]],
        }
    # also second-half (robust/recent) metrics
    out["second_half"] = {k: {kk: (None if (isinstance(v, float) and v != v) else round(float(v), 4))
                              for kk, v in m.items()} for k, m, _ in r2}
    out["first_half"] = {k: {kk: (None if (isinstance(v, float) and v != v) else round(float(v), 4))
                             for kk, v in m.items()} for k, m, _ in r1}
    with open(os.path.join(HERE, "..", "out", "results.json"), "w") as f:
        json.dump(out, f)
    print("\nsaved out/results.json")
    return out


if __name__ == "__main__":
    parity()
    honest()
