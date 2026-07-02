# BTC Power — All Products: performance + how to use

**As of 2026-06-28.** All figures: honest backtest (no look-ahead, slippage charged on turnover,
50 bp BTC / tiered for alts, daily close, **$500 start**). Reproduce via the script named per product.
Treat dollar figures as order-of-magnitude — crypto profit is concentrated in a few trends.

> **Bottom line:** the **Multi-Asset Basket** is the best product (healthiest, best risk-adjusted,
> robust across eras). The **leveraged BTC "Apex"** is *not* recommended — it's front-loaded to
> 2019–20 and flat since 2021. The **BTC 1× spot** is the simple conservative single-coin option.
> There is **no honest path to "$500 → $1M"** — that number only ever existed at perfect (zero-cost)
> fills in two bull years.

---

## Product 1 — Multi-Asset Trend Basket ⭐ (recommended, not yet deployed as headline)

A diversified basket of major coins, each traded by the same 1× vol-targeted trend ensemble, blended.
No leverage → cannot be liquidated. Source: `src/multi_asset_engine.py`, validated in
`src/research_validate.py`. Preview: https://btctree.github.io/btc-power/index_multi.html

**Same-framework comparison (BTC daily 2018→2026):**

| Mode | $500 → (full) | Sharpe | maxDD | Calmar | **2021–26 CAGR** | **21–26 DD** | **21–26 Sharpe** |
|---|--:|--:|--:|--:|--:|--:|--:|
| **Basket top-8** (by liquidity) | $4,935 | **1.33** | **−23%** | 1.40 | **+33%** | −23% | **1.31** |
| **Basket equal-weight** | $3,721 | **1.33** | **−19%** | 1.48 | +28% | **−19%** | 1.30 |
| BTC-only (same engine) | $5,265 | 0.92 | −50% | 0.67 | +19% | −50% | 0.67 |

**Why it's the best:** roughly **double** BTC's risk-adjusted return at **~half the drawdown**, and —
unlike the leveraged BTC model — it is strong in **both** eras (2017–20 *and* 2021–26), so it is not a
front-loaded mirage. Cross-coin correlations are low (0.2–0.4), so the blend rides smoother than any
single coin. Validated against the overfitting traps: 14-coin universe (so it's not 4-coin luck),
non-peeking monthly selection by *trailing* liquidity (so dead/illiquid coins drop out with no
hindsight — survivorship-safe), tiered alt slippage.

**Honest weakness:** in pure **alt-bear years (2018, 2022)** it underperforms BTC-only — alts fall
harder and trend-following can't fully sidestep it. Over full cycles the up-years more than compensate.

**How to use it:**
1. Open the **Basket** tab — it lists today's 8 coins, each with **LONG / SHORT / FLAT** and a **size %**.
2. Split your capital into 8 equal slices (one per coin). For each coin, take its shown direction; the
   **size %** is how much of that slice to deploy (rest in cash). FLAT = hold cash for that slice.
   *Equal-weight mode* instead spreads across the whole majors list — lower drawdown, simpler.
3. **No leverage.** Spot only. Re-check ~weekly; the basket reselects coins monthly by liquidity.
4. **Returns** tab = the historical curve (toggle the three modes). **About** = caveats.
- Realistic expectation: **~25–35% CAGR at ~−20–25% drawdown** (Sharpe ~1.3). A smoother BTC, not a moonshot.

---

## Product 2 — BTC "Apex" (leveraged) ⚠️ currently live, NOT recommended

The single-BTC leveraged trend model. **Live now:** https://btctree.github.io/btc-power/
Source: `src/apex_engine.py` → `results_live.json`.

| Scenario | $500 → (full) | maxDD | Liq |
|---|--:|--:|--:|
| Apex @0 bp (perfect fill — fantasy) | ~$76,000,000 | −51% | 0 |
| **Apex @50 bp (realistic)** | **~$1,200,000** | **−54%** | 0 |
| Apex @100 bp | ~$77,000 | −68% | 0 |

**Why NOT to use the leverage:** the entire headline was earned by **end of 2020**. Since then it is
**flat: 2021→2026 = +19% total (+3%/yr) while suffering a −54% drawdown.** At realistic cost the leverage
is actually **net-negative** post-2020 (it turned the 1× spot's +115% / −30% DD into +19% / −54% DD).
Full-period Sharpe (1.29) and Calmar (1.59) *look* great only because they're dominated by 2019–20.

**How to use it (if you use this page at all):** read only the **1× (spot)** line — see Product 3.
Ignore the leveraged scenarios; treat them as a historical curiosity. Telegram alerts will fire once
the repo secrets are set (see `README.md`).

---

## Product 3 — BTC 1× spot (conservative single-coin)

The unleveraged BTC ensemble (the honest single-coin product). It's the "1× (spot)" scenario on the
live Apex page, and the "Core" card. Source: `src/apex_engine.py`.

| | $500 → (full) | maxDD | **2021–26 CAGR** | **21–26 DD** | **21–26 Sharpe** |
|---|--:|--:|--:|--:|--:|
| BTC 1× spot (gated ensemble) | ~$25,800 | −36% | **+16%** | −30% | 0.69 |
| *(benchmark)* BTC buy & hold | ~$19,000 | −65% | +15% | −77% | 0.53 |

**Honest read:** a legitimate **BTC drawdown-reducer** — similar return to holding BTC at **~40% of the
drawdown**, positive every year 2021–25. Modest but stable. Cannot be liquidated.

**How to use it:** hold BTC spot in the shown direction/size; exit when the signal flips. No leverage.
Realistic expectation: **~15%/yr at ~−30% DD.**

---

## Quick chooser

| You want… | Use |
|---|---|
| Best overall (smoothest growth, lower drawdown) | **Multi-Asset Basket — equal-weight** |
| A bit more return, still diversified | **Multi-Asset Basket — top-8** |
| Simplicity, single coin, conservative | **BTC 1× spot** |
| The leveraged BTC headline | **Avoid** — front-loaded, flat since 2021 |

**Reproduce:** `python multi_asset_engine.py` · `python research_validate.py` · `python apex_engine.py`
(all in `btc_signal/src`). Full model history in `MODELS_FINDINGS.md`; the 9-role critique in
`APEX_REVIEW.md`.

*Hypothetical backtests; not financial advice. Validate out-of-sample before risking capital.*
