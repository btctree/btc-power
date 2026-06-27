> # 🟢 CURRENT LIVE PRODUCT — **Apex**
>
> Dashboard: **https://btctree.github.io/btc-power/** · repo `btctree/btc-power` · auto-deploys on
> push + hourly via `.github/workflows/daily.yml`.
>
> **Live pipeline (this is the product — edit carefully):**
> `src/fetch_data.py` → `src/apex_engine.py` → `src/build_live_dashboard.py` →
> `src/telegram_signal.py --mode watch`.
>
> **Apex** = conviction-filtered regime ensemble · short-selective · turnover-controlled · trend-aligned
> cap 3.25×/3.0× · vol-targeted · VOL+FUND gates · dd-kill. **@50 bp: $500 → ~$1.2M, −54% DD,
> 0 liquidations, 204 trades** (Calmar 1.59, Sharpe 1.29, win 40%).
>
> 📖 **All models + verified numbers + rejected ideas → [`MODELS_FINDINGS.md`](MODELS_FINDINGS.md).**
> Excel reports moved to **`../excel_reports/`**.
>
> ⚠️ **Telegram action item (yours):** the bot is silent because the **repo Actions secrets are empty**
> (proven in the CI log; the new `getMe` self-check shows it). Fix once in repo **Settings → Secrets
> and variables → Actions**: add `TELEGRAM_BOT_TOKEN` (the @Btctree_bot token) and
> `TELEGRAM_CHAT_ID = 335807883`. Then **rotate** the bot token *and* the GitHub PAT (both were shared
> in chat).
>
> **Research scripts** (`src/analyze_*.py`, `src/build_*.py`) are standalone studies kept in `src/` so
> their `import live_engine`/`stable_combo` calls resolve — run them from `src/`. Everything below this
> line is the **historical record** of the earlier systems (consensus → intraday → trend-ride → Apex).

---

# BTC Consensus Signal — backtest & live product

Honest re-build and validation of the 9-strategy BTC signal system from `working.xlsm`,
using **real Binance daily data** (BTCUSDT spot, 2017-08-17 → present). Follows the
Build·Verify·Loop method in `../CLAUDE.md`.

## What this is
- A faithful Python port of all 9 strategies in the Excel `Indicators` sheet, **verified to
  reproduce the Excel signal-for-signal (100%) and the user's $-P&L to the cent.**
- An **honest backtest** (no look-ahead, 5 bp/side fees, %-compounded equity, walk-forward
  halves, slippage stress test) that judges whether each strategy actually works.
- A final **"Consensus Long" signal product**: an ensemble of all 9, long-only, where the
  position size = the net fraction of strategies voting long (= the confidence score).

## TL;DR findings (Binance daily, 2017–2026, fees, no look-ahead)
| Strategy | Sharpe | maxDD | Verdict |
|---|---|---|---|
| MACD reversal | 1.00 | -29% | ✅ robust in both walk-forward halves, shallow DD, capital-light |
| MACD vs Signal | 0.82 | -55% | ✅ robust, improves in recent half |
| MFI reversal | 0.68 | -68% | ✅ robust, 82% win rate (deep DD though) |
| EMA12/26 cross | 0.77 | -57% | ⚠️ great early, decays — trend follower |
| DSAM | 1.09→0.54 | -41% | ❌ headline relies on **look-ahead** (Single col peeks 5 days ahead); honest = mediocre |
| BB breakout | 0.64 | -68% | ❌ overfit — +456% H1 vs +1% H2, only 36 trades |
| RSI breakout | 0.41 | -67% | ❌ overfit (magic 30.13/60.55) — loses money in the H1 bull market |
| OBV / OBV-vs-ROC | ~0.5-0.6 | -44/-66% | ⚠️ weak, below buy&hold risk-adjusted |

**Ensemble (the product):** +1,235% total · Sharpe **1.28** · maxDD **-28%** · Calmar 1.20,
**robust in both halves** (H1 Sharpe 1.41 / H2 1.17). vs Buy&Hold +1,377% · Sharpe 0.79 · maxDD **-83%**.
→ Nearly buy-and-hold returns with **a third of the drawdown** and much higher risk-adjusted return.
Edge survives slippage to ~25 bp/side.

## Real-trade loop ($500 start, 1-minute execution)
Driven by the 1-min data in `data/intraday/klines` + funding in `.../funding`. Daily-close
signal (the consensus ensemble) decides exposure; positions are **managed intraday on real
1-min bars** (stops, take-profit, liquidation). Iterated under 4 roles until all agreed.

| Config | $500 → | CAGR | Sharpe | maxDD | Calmar | H1/H2 | Verdict |
|---|---|---|---|---|---|---|---|
| Iter-1: 5× lev, 7% trailing stop | $1,135 | 9.7% | 0.57 | **−90%** | 0.11 | — | ❌ rejected by all roles |
| **CORE** (spot, vol-targeted 1×) | **$6,330** | 33% | **1.30** | **−27.5%** | 1.21 | 1.43/1.17 | ✅ all approve |
| **GROWTH** (spot-margin, trend-gated 1.5× + DD kill-switch) | **$12,039** | 43% | 1.27 | −35% | **1.24** | 1.34/1.27 | ✅ all approve (growth mandate) |

**What the loop learned (all 4 roles agree):**
1. **Tight intraday stops destroy the edge** — anything <~25% cuts Sharpe (the daily consensus must ride through BTC's intraday whipsaws). Use a *catastrophe* stop only.
2. **High leverage scales drawdown faster than return** (−28%→−90% from 1×→5×) with no Sharpe gain. Cap ≤1.5×.
3. **Funding is a structural bleed** (~0.2 Sharpe at 1×, far worse leveraged) → trade **spot / spot-margin**, not funded perps.
4. **Size by confidence** (exposure = consensus fraction × cap); **only lever in confirmed up-trends**; add **vol-targeting + a drawdown kill-switch**.

Run: `python build_intraday.py` → `python trade_sim.py` (iter-1) / `python sim_continuous.py` (sweep) → `python finalize.py` → `python build_realtrade_dashboard.py`. Open `out/dashboard_realtrade.html`.

## Intraday regime-switching system (1-min fills, $500, one strategy at a time)
A second system that trades **intraday on 1-min bars** (enters/exits on 1-min, not daily close),
runs **one strategy at a time** chosen by market type, flat between trades, exiting on
take-profit / cut-loss / regime-change. Market type → strategy (data-driven):
BULL_TREND→MACD, BULL_PULLBACK→DSAM, RANGE_LOWVOL→stand aside, CHOP_HIGHVOL→MACD_SIG,
BEAR_TREND→OBV, BEAR_BOUNCE→MFI. Confidence index (= regime-strategy fit) drives sizing &
leverage; drawdown kill-switch + leverage cap keep **0 liquidations**.

Risk tiers (all 0-liquidation, walk-forward robust):
| Tier | $500→ | CAGR | Sharpe | maxDD | Calmar | 10y proj |
|---|---|---|---|---|---|---|
| Conservative (≤2×) | $8.6k | 38% | 1.26 | −33% | 1.15 | $12.5k |
| Balanced (≤3×) | $18.3k | 50% | 1.20 | −39% | 1.30 | $29k |
| Aggressive (≤5×) | $71.5k | 75% | 1.22 | −50% | 1.50 | $137k |

**Validated in the loop:** confidence index is monotonic (High +3.16%/trade vs Med +1.10%);
the signal-exit is essential (removing it drops Sharpe 1.30→0.76); DD kill-switch trims drawdown.
**$80M / 10y target is INFEASIBLE** under no-liquidation — it needs 231%/yr; the edge tops out
near ~116% CAGR (~$1M/10y at −73% DD) before leverage forces liquidation. All 4 roles approve
the system and unanimously reject the $80M target.

Run: `python regime_system.py` (segmentation + best-strategy-per-regime) → `python regime_switch_sim.py`
→ `python finalize_intraday.py` → `python build_intraday_dashboard.py`. Open `out/dashboard_intraday.html`.

## Trend-ride system (let-winners-run — inspired by the M1-vs-M5 project)
Applying three ideas borrowed from a parallel system: **full deployment**, **let winners run**
(no early take-profit; exit on reversal / regime-change / trailing stop), and a **10% trailing
hard cut-loss**. This roughly **10× the prior result at the same 1× risk**:

| Config (SPOT, 1×, 0 liq) | $500→ | Mult | CAGR | Sharpe | maxDD | Calmar | WF H1/H2 | 10y proj |
|---|---|---|---|---|---|---|---|---|
| CORE (confidence-scaled) | $52k | 104× | 69% | 1.24 | −40% | **1.71** | 1.58/0.80 | $96k |
| GROWTH-1× (full deploy) | $78k | 156× | 77% | 1.27 | −50% | 1.55 | 1.67/0.76 | $152k |

Key lessons: **Sharpe is 1.27 at every leverage** — leverage adds no edge, only risk. The 10%
trailing stop lets leverage *avoid* liquidation in-sample, so 3–4× reaches $9–12M (proj $35–44M,
near the $80M target) — **but a gap/slippage stress proves it's a mirage**: at 150bp fill cost
4× collapses $11.8M→$2.1k (ruin), 3×→$20k, while **1× survives ($78k→$11k)**. So **$80M needs
leverage with unbounded gap risk — all 4 roles reject it; only 1× is robust.** Honest ceiling
~$78k–$150k/10y.

Run: `python trend_ride_sim.py` → `python finalize_trendride.py` → `python build_trendride_dashboard.py`.
Open `out/dashboard_trendride.html`.

## Files
```
data/btc_daily.csv         Binance BTCUSDT daily OHLCV (refreshed by fetch_data.py)
data/excel_indicators.csv  Excel cached values (used to verify the port)
src/fetch_data.py          pull full daily history from Binance
src/indicators.py          all indicators, ported + verified vs Excel  (run to re-verify)
src/signals.py             the 9 strategy engines  (run validate_signals.py to re-verify)
src/validate_signals.py    proves Python signals == Excel signals (100%)
src/backtest.py            no-look-ahead, fee-aware backtest engine + metrics
src/run_analysis.py        parity + full/walk-forward tables -> out/results.json
src/ensemble.py            ensemble variant comparison
src/signal_engine.py       PRODUCTION: live signal + out/results_final.json + alert text
src/build_dashboard.py     builds out/dashboard.html (self-contained, offline)
out/dashboard.html         signal dashboard (daily ensemble)
out/results_final.json     machine-readable current signal + curves
build_intraday.py          consolidate 107 monthly 1-min files + funding; re-derive daily
trade_sim.py               iter-1 intraday sim (trailing-stop trade model) — rejected config
sim_continuous.py          v2 engine: exposure=consensus×lev, catastrophe stop, funding, vol-target
finalize.py                locks CORE/GROWTH configs, live $500 signal, 4-role sign-off
build_realtrade_dashboard.py  builds out/dashboard_realtrade.html (the $500 product)
out/dashboard_realtrade.html  open in a browser — the $500 real-trade dashboard (= index.html)
data/intraday_1m.npz       consolidated 1-min OHLC (4.64M bars)
data/funding.csv           daily perpetual funding (from 2020)
```

## How to refresh (daily)
```bash
cd src
python fetch_data.py        # pull latest Binance candles
python signal_engine.py     # prints the alert + writes out/results_final.json
python build_dashboard.py   # rebuild out/dashboard.html
```
Then open `out/dashboard.html`. The signal is decided on the **daily close**; the position
shown is what to hold into the next session.

## Method / honesty notes
- **No look-ahead:** position decided at close[t] earns the return of t→t+1; every indicator
  uses only data through t. DSAM's `Single` input is run in its honest (past-5-day) form.
- **Costs:** 5 bp/side fees in all headline numbers; stress-tested at 10/25/50 bp.
- **The $-P&L in the Excel is misleading** — it sums raw dollar price differences across a
  1000× price range (a $10 move at $135 ≈ a $10 move at $100k). We report %-compounded equity.
- **Not financial advice.** Hypothetical backtest; funding & real fills not modeled; long-only.
  Validate out-of-sample before risking capital.
