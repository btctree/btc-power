# BTC Signal — All-Models Findings & Reference

**Purpose:** a single honest record of every model explored, its verified numbers, and the
principles learned — so future work (this product or any new one) doesn't re-derive from scratch.

**Last updated:** 2026-06-27 · **Live product:** Apex (`src/apex_engine.py`) →
https://btctree.github.io/btc-power/

> All figures below are from the *same* validated engine (no look-ahead, honest intraday
> liquidation, slippage charged on turnover), BTC daily **2017→2026**, **$500 start**.
> Reproduce with the scripts named in each row. Numbers move slightly as new daily bars arrive.

---

## 1. Current production model — **Apex**

Apex = conviction-filtered regime ensemble, **short-selective**, **turnover-controlled**,
**trend-aligned leveraged**, **vol-targeted**, with VOL+FUND gates and a draw-down kill-switch.

| | 1× (spot) | @0 bp | **@50 bp (real)** | @100 bp |
|---|--:|--:|--:|--:|
| **$500 →** | $25,811 | $75,921,978 | **$1,198,372** | $77,451 |
| **max DD** | −36% | −51% | **−54%** | −68% |
| **Liquidations** | 0 | 0 | **0** | 0 |

Calmar **1.59** · Sharpe **1.29** · CAGR ~**87%** · win **40%** (long **45%** / short **34%**) ·
**204** in-&-out trades · max fund usage capped ~60%. Source: `src/apex_engine.py`,
`src/build_short_selective_report.py`.

**The recipe (why it works):**
1. **Turnover control** (EMA-smooth span 5 + 0.15 dead-band) — the single biggest "free lunch":
   it cuts trade count so 50 bp slippage stops eating the edge. This is what separates a model
   that survives real fills from one that only looks good at 0 bp.
2. **Vol-targeting** (target 60%): exposure = signal × min(cap, vol_target / realized_vol).
   Scales **up** in calm markets toward the cap, **down** in violent ones.
3. **Trend-aligned cap** (3.25× when the position agrees with the SMA200 trend, 3.0× counter-trend):
   adds leverage *only* where it's cheap in risk — best Calmar of the leveraged family.
4. **Short-selectivity** (short *only* confirmed downtrends: regime STRONG_DOWN/TREND_DOWN **and**
   price < SMA200): cuts the slippage-costly chop shorts that bleed money. Raises @50 bp profit.
5. **VOL+FUND gates** (halve exposure when vol-rank > 0.85 or funding-rank > 0.90 / < 0.10) and
   **dd-kill** (halve exposure below 70% of equity peak) — the safety rails that hold liquidations at 0.

> **Honest caveat:** Apex is **not** the highest-profit model (Growth 5× and Aggressive B make
> more @50 bp — see below). Apex is the best model that satisfies the **hard constraints** you set:
> > 200 in-&-out trades · 0 liquidations · max DD ≤ 55% · ≥ $1M @50 bp · Calmar > 1 · Sharpe > 1 ·
> fund usage ≤ 60%. It trades raw profit for safety and tradeability.

---

## 2. Full comparison — every model on one engine

| Model | $@0 bp | $@50 bp | $@1× | CAGR | Calmar | Sharpe | maxDD | Win% | 3 big drops (W1/W2/W3) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Buy & Hold (BTC) | $39,506 | $19,000 | $19,000 | 34% | 0.52 | 0.85 | −65% | — | −55 / −34 / −33% |
| Raw 8B 5× (original) | $13.5 B | $13,331 | $6,417 | 30% | 0.36 | 0.77 | −84% | 50% | −82 / −77 / −66% |
| **Core 1× (spot, safe)** | $134,724 | $41,164 | $41,164 | 43% | **1.45** | **1.33** | **−29%** | 46% | −29 / −28 / −20% |
| Balanced 2× (cap2) | $7.85 M | $496,022 | $26,623 | 74% | 1.68 | 1.26 | −44% | 41% | −44 / −41 / −35% |
| Balanced 2.5× | $45.6 M | $504,210 | $26,623 | 74% | 1.54 | 1.21 | −48% | 41% | −47 / −47 / −28% |
| Balanced 3× (cap3) | $50.6 M | $931,379 | $26,623 | 83% | 1.54 | 1.25 | −54% | 41% | −49 / −51 / −31% |
| **Apex (3.25/3 short-selective)** | **$75.9 M** | **$1,198,372** | $25,811 | 87% | **1.59** | **1.29** | −54% | 40% | (0 liq, 204 trades) |
| Growth 5× (A) | $361 M | $3,536,933 | $26,623 | 104% | 1.75 | 1.35 | −59% | 38% | −52 / −54 / −44% |
| Aggressive B (vt2/cap5) | $430 M | $3,978,428 | $34,972 | 106% | 1.58 | 1.27 | −67% | 41% | −59 / −57 / −47% |
| Smooth C (sm10/cap5) | $14.9 M | $1,768,003 | $18,858 | 93% | 1.55 | 1.30 | −60% | 40% | −44 / −47 / −40% |
| Conditional-lev | $14.9 M | $545,916 | $26,623 | 75% | 1.58 | 1.23 | −48% | 37% | −45 / −46 / −35% |
| Cycle math *(in-sample, overfit)* | $58.3 M | $5,298,397 | $343,710 | 111% | 1.69 | 1.35 | −66% | 88% | −47 / −44 / −49% |

Source: `src/build_full_compare.py` → `BTC_ALL_MODELS_compare.xlsx`. "Cycle math" is flagged
**in-sample** (uses the realized cycle) and must not be trusted out-of-sample.

**How to read it:**
- **Core 1×** is the only model that *cannot* be liquidated and has the lowest DD (−29%). The honest
  floor of the product. Everything above it buys return with draw-down and tail risk.
- **The 0 bp column is a mirage.** Raw 8B 5× shows **$13.5 B** at perfect fills and **$13,331** at
  50 bp — a 1,000,000× collapse. Any model whose story lives in the 0 bp column is untradeable.
- @50 bp, the leveraged family clusters around $0.5 M–$4 M; the differentiator is **draw-down and
  liquidation risk**, not headline profit.
- **Win rate is structurally ~40%.** This is a convex trend-follower: it wins on a few big trends and
  bleeds small on the chop. Pushing win% > 50% kills the trade count and the edge (tested, §4).

---

## 3. The 8B X/Y and the M1-vs-M5 "$1.6B" engine

- **Raw 8B 5×** (the old headline): the **$13.5 B / $1.6 B** figures are **0 bp, perfect-fill**.
  At realistic 50 bp it's **$13,331** with an **−84%** draw-down — it is not a tradeable product.
  Apex is the honest successor: same family, but turnover-controlled and risk-gated.
- **M1-vs-M5 X/Y engine** (50% deploy × 5×/2× long/short, 7% trailing stop) reproduces the famous
  ~$1.6 B at 0 bp but collapses under slippage just the same. Their own code labels it "optimistic,
  assumes the stop holds intraday." Source: `src/build_m1m5_compare.py`, `src/trade_log_2014.py`.
  **Lesson:** every "huge" BTC backtest number you'll see quoted is a 0 bp / perfect-fill artifact.

---

## 4. Things tried and **rejected** (don't redo these)

- **Tighter intraday stops** (< ~25%): destroy the edge — BTC whipsaws stop you out before the trend.
  Use a catastrophe stop only.
- **Higher win-rate tuning** (conviction filters on shorts to push win% > 50%): works on paper but
  drops the trade count below the >200 constraint and *lowers* @50 bp profit. ~48% is the practical
  ceiling. Source: `src/analyze_short_conv.py`, `analyze_winrate.py`.
- **Reducing draw-downs via signal/tail hedges** (5 signal families + a tail hedge tested): the three
  big crashes (2018 / 2022 / 2025) are **not separable** ahead of time — every overlay either lagged
  or cost more than it saved. Draw-downs of ~−45% to −55% are irreducible for this return level.
  Source: `analyze_drawdowns.py`, `analyze_tailhedge.py`, `analyze_onchain_separability.py`.
- **On-chain (MVRV) regime overlay:** no usable out-of-sample separation on the free-tier metrics.
- **Pure cycle / "cycle math" timing:** great in-sample (uses the realized top/bottom), not trustworthy
  out-of-sample — kept only as an upper-bound reference. Source: `pure_cycle.py`.
- **Leverage above ~3–5×:** scales draw-down faster than return and re-introduces liquidation risk on
  gaps; fails the slippage stress test.

---

## 5. Sampling / robustness

Bootstrap of the trade sequence (`analyze_bootstrap.py`): the **edge sign is robust** (the model
beats B&H in the large majority of resamples) but the **magnitude is wide** — profit is concentrated
in ~10 trades (top-10 ≈ 100%+ of log-profit). Treat the dollar figures as *order-of-magnitude*, not
precise forecasts. 200+ trades is enough to trust the *direction* of the edge, not its exact size.

---

## 6. Reproduce any number

```
cd btc_signal/src
python apex_engine.py            # live Apex model + 1x/0/50/100bp scenarios -> ../out/results_live.json
python build_full_compare.py     # the §2 table -> ../../BTC_ALL_MODELS_compare.xlsx
python build_short_selective_report.py   # Apex trade-by-trade + long/short win rates
python build_m1m5_compare.py     # the M1-vs-M5 / 8B X/Y "$1.6B" honest re-run
```

Core building blocks: `live_engine.py` (setup, ensemble_ctx, metrics), `stable_combo.py`
(simulator), `regime_v2.py` (regime taxonomy), `signals.py` (9 engines), `fast_search.py`
(regime→engine map). Research scripts live in `src/research/` (see `ARCHIVE_README` there).
