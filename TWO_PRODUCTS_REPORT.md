# Two Products — All-Year Return vs Risk Report

**As of 2026-06-28.** Honest backtest: BTC daily 2017–2026, $500 start, slippage on turnover (BTC 50 bp,
equity ETFs 5–10 bp), correct weekend handling, daily ruin check, 6%/yr borrow on leverage, no look-ahead.
Both products use the same trend engine; crypto = **BTC only**; the basket adds **global products**
(US/HK/JP/EU equity ETFs + gold + silver + oil + bonds). Reproduce: `python research_two_products.py`.

- **A — ALL-WEATHER:** equal-weight BTC + global, **1× (no leverage)**.
- **B — AGGRESSIVE:** the highest honest CAGR within your **60% drawdown budget** — the scan picked
  **100% BTC at 1.5×** (concentration + modest leverage beats diluting into a levered blend).

---

## Year-by-year — return AND risk (max drawdown that year)

| Year | A return | A maxDD | | B return | B maxDD |
|---|--:|--:|--|--:|--:|
| 2017 | +14% | −3% | | **+423%** | −37% |
| **2018** ⚠ | **−0%** | −6% | | **−20%** | −54% |
| 2019 | +6% | −5% | | +20% | −59% |
| 2020 | +34% | −3% | | **+313%** | −18% |
| 2021 | +6% | −3% | | +35% | −48% |
| **2022** ⚠ | **+4%** | −4% | | **+3%** | −36% |
| 2023 | +5% | −3% | | +25% | −31% |
| 2024 | +8% | −2% | | +26% | −36% |
| 2025 | +10% | −2% | | +9% | −22% |
| 2026 | +11% | −5% | | +13% | −18% |

⚠ = the bear years. **A keeps both green/flat (2018 ≈0%, 2022 +4%). B wins the bull years huge (+423%,
+313%) but loses 2018 (−20%) and rides −50%+ intra-year drawdowns.**

---

## Summary — return vs risk

| Metric | A — All-Weather | B — Aggressive |
|---|--:|--:|
| **CAGR** | +10% | **+53%** |
| **Max drawdown** | **−6%** | −59% |
| **Sharpe** | **1.76** | 1.01 |
| **Calmar** (CAGR/DD) | **1.69** | 0.89 |
| **$500 → (10y)** | $1,248 | **$27,857** |
| Best year | +34% | +423% |
| Worst year | −0% | −20% |
| Positive years | 9 / 10 | 9 / 10 |
| 2018 / 2022 | **+0% / +4%** | −20% / +3% |

---

## How to read it

- **A is far more *efficient*** (Sharpe 1.76 vs 1.01, Calmar 1.69 vs 0.89, drawdown −6% vs −59%). Every
  year is calm and green; both bear years survive. The cost: only ~10%/yr → $500 becomes ~$1,250 in 10y.
- **B makes ~5× the return** (53% vs 10% → ~$28k vs ~$1.25k) but takes **~10× the risk**: −59% peak
  drawdown, a −20% loss in 2018, and several years with −30% to −59% intra-year pain. Its return is
  front-loaded into the bull years (2017 +423%, 2020 +313%); the rest are ordinary.
- **Neither reaches $1,000,000** from $500 — that needs +114%/yr, which is above the honest ceiling of
  these assets at any survivable leverage (proven across nine strategy tests).

**The core trade-off, in one line:** A protects the bad years and compounds quietly; B chases the great
years and pays for it in drawdown. You cannot have B's return *and* A's smoothness — that dial is the
risk you take, and the market sets the exchange rate.

*Hypothetical backtest; not financial advice. Validate out-of-sample before risking capital.*
