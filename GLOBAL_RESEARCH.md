# Global Trend Portfolio — full report, all-years backtest & improvement roadmap

**As of 2026-06-28.** A 12-product, no-leverage trend portfolio across **US/HK/JP/EU equities + Gold,
Silver, Oil + Bonds + BTC/ETH** (all USD-denominated ETFs → one currency, FX baked in, directly
tradeable). The same 1× vol-targeted trend ensemble runs on every asset *unchanged*; the portfolio is
**equal-weight** (the validated best combination). Built as a product: `src/global_engine.py` →
`results_global.json` → `src/build_global_dashboard.py` → `out/index_global.html` (Holdings · Returns ·
Years · About). Data: Yahoo Finance daily 2016–2026 (`data/global/`). Reproduce: `python global_engine.py`.

> Honest framing: this optimizes **consistency and drawdown control**, not maximum return. It earns
> *less* raw return than crypto-only, in exchange for a far smoother, all-weather ride.

---

## 1. Headline

| | CAGR | maxDD | Sharpe | Calmar | Positive years |
|---|--:|--:|--:|--:|--:|
| **GLOBAL blend (equal-wt) ⭐** | **+22%** | **−15%** | 1.2–1.4¹ | **1.47** | **10 / 10** |
| Crypto-only basket | +44% | −31% | 1.14 | 1.39 | 8 / 10 |
| Equities-only blend | +5% | −4% | 1.11 | 1.22 | 10 / 10 |
| Global (risk-parity) | +11% | −16% | 0.90 | 0.69 | 10 / 10 |
| BTC buy & hold | +54% | −83% | 0.81 | — | no |
| US-SPY buy & hold | +13% | −34% | 0.64 | — | no |

¹ Sharpe is 1.19 annualising at √252 (equity convention) or 1.43 at √365 (the mixed crypto/equity
calendar). Cited as ~1.2–1.4 to avoid overstating. **$500 → $3,249** over ~9.5 years.

Adding **oil and silver** improved the blend (Calmar 1.37→**1.47**, recent Sharpe 0.93→**1.08**) —
oil especially (its trend sleeve: +18% CAGR, Sharpe 0.94, and uncorrelated to everything else).

---

## 2. Full backtest — every year

| Year | Return | maxDD | Note |
|---|--:|--:|---|
| 2017 | +34.4% | −13.1% | crypto bull |
| **2018** | **+3.5%** | −8.3% | crypto −80%, stocks −20% → **still positive** |
| 2019 | +30.5% | −14.8% | |
| 2020 | +71.8% | −7.1% | COVID crash + recovery, only −7% DD |
| 2021 | +19.5% | −8.9% | |
| **2022** | **+10.6%** | −5.9% | crypto −65%, stocks −20%, bonds −30% → **best relative year** |
| 2023 | +13.5% | −5.8% | |
| 2024 | +15.7% | −5.1% | |
| 2025 | +11.0% | −5.9% | |
| 2026 | +8.0% | −5.7% | YTD |

**The proof:** positive **every year**, max drawdown only −15%, and it *made money in 2018 and 2022* —
the bear years that wrecked the crypto-only and leveraged-BTC products. When crypto and stocks fell, the
trend engine went short/flat on them while gold, oil and other trends carried. This is the "healthy,
stable" behaviour the BTC products never had.

---

## 3. Per-asset trend sleeves (1×, full period)

| Product | Region | CAGR | maxDD | Sharpe | Role |
|---|---|--:|--:|--:|---|
| US-SPY | US | +8% | −7% | 1.02 | low-DD core |
| US-QQQ | US | +9% | −8% | 1.03 | best US |
| HK-EWH | HK | +3% | −22% | 0.38 | weak (diversifier) |
| JP-EWJ | JP | +1% | −4% | 0.47 | low-vol ballast |
| EU-VGK | EU | +2% | −16% | 0.34 | weak (diversifier) |
| EU-EWG | EU | +6% | −10% | 0.61 | decent |
| **Gold** | Commod | +5% | −12% | 0.72 | strong diversifier |
| **Silver** | Commod | +11% | −30% | 0.61 | higher-octane metal |
| **Oil (USO)** | Commod | +18% | −20% | 0.94 | excellent, uncorrelated |
| Bond-TLT | Bond | +2% | −7% | 0.43 | near-zero-corr ballast |
| BTC | Crypto | +40% | −43% | 0.88 | return engine |
| ETH | Crypto | +33% | −32% | 0.99 | return engine |

**Why diversification works:** cross-asset-class correlations are near zero (crypto↔equities 0.0–0.2;
gold/bonds/oil ↔ everything ~0). Twelve weakly-correlated positive-expectancy streams average into a
smooth curve — the lowest-drawdown product we've built.

---

## 4. How the system signals — "when to do what, in which product"

Each product independently produces a daily **LONG / SHORT / FLAT + size %**:
1. Classify the regime (8 types) from trend (SMA/ADX) + volatility.
2. The 9 strategy engines (MACD, RSI, MFI, BB, OBV, …) vote; the regime picks which vote.
3. Net the votes → conviction; act only if ≥ 0.40, else FLAT.
4. Smooth (EMA-5 + dead-band) to cut turnover; short only confirmed downtrends.
5. Vol-target the size, capped at 1× (no leverage).

The portfolio holds all 12 **equal-weight** (1/12 each; deploy each at its size %, rest in cash),
rebalanced ~monthly. **Today (2026-06-28):** Gold LONG 69% · JP LONG 37% · QQQ LONG 26% · Silver LONG 15%
· EWG LONG 11% · SPY LONG 5% · **BTC SHORT 47%** · ETH LONG 3% · Oil/VGK/Bonds FLAT. See the dashboard
**Holdings** tab (saved to `out/global_signals.json` / `results_global.json`).

---

## 5. What needs to improve first (priority order)

1. **Long-or-cash variant (tradeability) — do this first.** The backtest *shorts* ETFs; most retail
   accounts can't short, and inverse ETFs have decay. Build & measure a **long-only / inverse-ETF**
   version. Expect lower return (shorting contributed most of the 2018 & 2022 gains) but it must stay
   positive and shallow-DD to be a real retail product. *This is the gap between backtest and tradeable.*
2. **Per-asset-class validation.** The rules are crypto-derived, applied unchanged. The weak sleeves
   (HK/JP/EU, Sharpe 0.3–0.6) may improve with a **walk-forward** per-class check (longer SMAs / different
   conviction for slow equities) — but only if it survives out-of-sample, no curve-fitting.
3. **Extend the history.** Only a 10-year window (2016–2026) = one secular regime. Pull pre-2016 for the
   equity/gold/bond sleeves (ETFs go back to 1990s–2000s) to test 2008-style crises and rising-rate eras.
4. **Portfolio-level rebalancing cost.** Per-asset turnover cost is modeled, but the *monthly rebalance*
   to equal weight has its own cost — estimate it (small, but be honest).
5. **Better weighting than equal / inverse-vol.** Inverse-vol underperformed (it starved crypto). Try
   **vol-scaling each sleeve to a common target vol** then equal-weight, or a capped risk budget — may
   lift Sharpe without leverage.
6. **Live-data robustness for deployment.** Yahoo fetch needs incremental top-up + cached `data/global/`
   for CI (rate limits), plus a daily refresh path, before this can auto-update like the BTC product.
7. **Signal alerts.** No Telegram yet for the global product — add once the long-only variant is locked.
8. **If more return is wanted:** a *modest* risk-budget tilt toward crypto/oil (the high-Sharpe sleeves)
   — carefully, since it re-introduces drawdown. Don't reach for leverage (proven net-negative).

---

## 6. How to use it (today)
Split capital into 12 equal slices; for each product take its **signal** at the shown **size %** (rest in
cash); FLAT = cash. Trade via the USD ETFs (SPY/QQQ/EWH/EWJ/VGK/EWG/GLD/SLV/USO/TLT) or spot crypto.
**No leverage.** Re-check weekly; rebalance monthly. Can't short? Hold cash for that slice (see
improvement #1). Realistic expectation: **~15–22% CAGR at ~−15% max drawdown, positive most years.**

*Hypothetical backtest; not financial advice. Validate out-of-sample before risking capital.*
