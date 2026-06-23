"""Parameter sweep for the 4-role review: how do leverage / trailing-stop / funding
affect the $500 outcome? Pre-computes daily signals once; only re-runs the cheap
intraday loop per config."""
import copy
import numpy as np
import trade_sim as ts

BASE = ts.CONFIG


def run(over):
    cfg = copy.deepcopy(BASE)
    cfg.update(over)
    return ts.simulate(cfg)


def row(label, r):
    return (f"{label:26s} ${r['final']:>9,.0f}  {r['total']*100:>+8.0f}%  {r['cagr']*100:>6.1f}%  "
            f"{r['sharpe']:>5.2f}  {r['maxdd']*100:>6.1f}%  {r['calmar']:>5.2f}  "
            f"{r['n_trades']:>4d}  {r['winrate']*100:>3.0f}%  {r['liquidations']:>3d}  "
            f"${r['fees_paid']:>7,.0f}  ${r['funding_paid']:>8,.0f}")


def main():
    print("config                         final     total    CAGR  Shrp   maxDD  Calm  "
          "  #tr  win  liq      fees   funding")
    print("-" * 118)
    # leverage sweep (7% trail)
    for lev in [1.0, 1.5, 2.0, 3.0, 5.0]:
        print(row(f"lev {lev:g}x  trail7%", run(dict(lev_long=lev))))
    print("-" * 118)
    # trail sweep at lev 2x
    for tr in [0.05, 0.07, 0.10, 0.15, 0.20]:
        print(row(f"lev 2x  trail{int(tr*100)}%", run(dict(lev_long=2.0, trail=tr))))
    print("-" * 118)
    # funding off (to isolate funding drag) at a few levs
    for lev in [1.0, 2.0, 5.0]:
        print(row(f"lev {lev:g}x  NO-funding", run(dict(lev_long=lev, use_funding=False))))
    print("-" * 118)
    # conservative sizing at low lev
    for lev in [1.0, 2.0]:
        print(row(f"lev {lev:g}x sz30/25/20", run(dict(lev_long=lev, size_high=0.30, size_med=0.25, size_low=0.20))))


if __name__ == "__main__":
    main()
