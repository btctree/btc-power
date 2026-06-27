# Apex — 9-role review (review → comment → redo → re-review)

Reviewed: the Apex model (`apex_engine.py`), the dashboard, the Telegram bot, and `MODELS_FINDINGS.md`.
Each role gives a verdict, the concerns, and what was **redone** as a result. Honest throughout.

---

### 1. Mathematician — *is the math right?*
**Verdict: sound, with honest uncertainty.** No look-ahead (day *i* uses the signal from *i−1*; verified).
Vol-target, EMA dead-band, trailing ranks are all causal.
- **Concern:** the dollar outcomes are a *single historical path*; the bootstrap shows the **edge sign is
  robust but the magnitude is wide** (profit concentrated in ~10 trades). Point estimates over-state precision.
- **Concern:** the 3.25 vs 3.0 trend-aligned split is a small, principled tweak — low overfit risk but
  also marginal benefit; don't tune it further.
- **Redo:** `MODELS_FINDINGS.md` now states figures are order-of-magnitude, not forecasts.

### 2. IB Financial Analyst, CFA — *benchmarking & framing*
**Verdict: strong risk-adjusted (Sharpe 1.29, Calmar 1.59 vs B&H 0.85 / 0.52), but lead with risk.**
- **Concern:** never headline "$1.2M" alone — always next to the **1× ($25.8k)** and the **−54% DD**.
- **Concern:** 50 bp is fine for modest size; at scale, market impact rises (capacity limit).
- **Redo:** dashboard Returns tab shows all four scenarios side-by-side and defaults to **@50 bp** (the
  realistic one), with the 1× and DD always visible.

### 3. Actuary — *tail risk & ruin*
**Verdict: "0 liquidations" is true for this path, NOT a 0% ruin probability.**
- **Concern:** at up to 3.25× effective, a single >~31% adverse overnight gap = ruin. BTC has gapped that
  far (Mar-2020 ≈ −40% intraday). The model survived historically because the gates/vol-target had it
  small at those moments — but a worse-ordered gap *could* ruin it. This is a real tail, not zero.
- **Redo:** the live card shows the explicit **liquidation price**, and the model note now says "needs a
  ~X% adverse gap to liquidate; 0 liquidations in backtest (tail risk remains)." For tail-averse capital,
  the recommendation is **Core 1× (−29% DD, cannot be liquidated).**

### 4. Private-bank fund manager — *suitability*
**Verdict: Apex is a risk-seeking sleeve, not a default.** A −54% DD ends most client mandates.
- **Concern:** most clients should sit in Core 1×; Apex only for explicitly risk-tolerant capital.
- **Redo:** the Core (spot 1×, same direction) card sits directly under Apex on the Signal tab; the
  disclaimer states Apex uses leverage and can be liquidated while spot 1× cannot.

### 5. Quant Trader — *execution realism*
**Verdict: realistic for spot at modest size; turnover control is doing the real work.**
- **Concern:** the live signal showed "LONG in a TREND_DOWN regime" — correct behavior (smoothing +
  dead-band hold a lagging long into a fresh downtrend) but **confusingly worded**.
- **Redo (code):** the forecast headline now reads *"Holding LONG into a TREND_DOWN market (trailing
  signal). Manage with the cut-loss $X; Apex exits when the ensemble flips."*

### 6. Industry Specialist (crypto) — *crypto-specific realism*
**Verdict: honest on fees/slippage; one cost is missing.**
- **Concern:** Apex's >1× exposure implies **margin/borrow interest** (spot-margin or perp funding) that
  the backtest does **not** charge — real leveraged returns are somewhat lower than shown.
- **Concern:** the 0 bp column is physically impossible in crypto (spread+fees) — already labelled
  "untradeable / optimistic."
- **Redo:** documented as an open caveat in this review; the honest tradeable reference remains the 1×/50 bp
  columns. (Borrow-cost modelling is a future enhancement.)

### 7. Programmer — *code quality & failure modes*
**Verdict: clean, but two silent-failure risks.**
- **Concern (fixed):** `apex_engine` read `funding.csv` silently — if missing/stale the gates no-op and
  results change with **no error**. **Redo (code):** it now prints a loud WARNING if missing and a note if
  stale (this immediately caught that `funding.csv` is ~3 weeks stale → recent live FUND-gates inactive;
  backtest unaffected).
- **Concern (fixed):** Telegram failed silently on a bad/empty token. **Redo (code):** added a `getMe`
  self-check + full API-response logging — which **proved** the real #1 cause (empty repo secrets).
- **Tech debt:** `model_8b` is kept as a JSON alias for cutover — remove after the dashboard cache clears.
- **Open:** no automated tests; a smoke test asserting the 4 scenario keys + plausible ranges would help.

### 8. End user — *clarity*
**Verdict: the five reported issues are fixed and verified in-browser.**
text-selection guard on the chart (#2); solid ▲/▼ enter + hollow △/▽ exit, shown by default (#3); the open
position rendered as "● CURRENT" with live price + running % and no fake exit (#4); the Returns chart is the
real Apex curve, not the old 1B/8B line (#5); renamed 8B → Apex everywhere.

### 9. Investor — *money I can actually keep*
**Verdict: treat the headline as a ceiling, not an expectation.** The $1.2M is single-path, zero
cost-of-capital, no borrow cost, and you must survive −54%. Realistic expectation is lower and wide; the
honest, liquidation-proof floor is **Core 1× (~$25–40k from $500, −29/−36% DD)**. Position size small —
the edge is real, the magnitude isn't bankable to the dollar.

---

## Consensus
- **Ship Apex** as the leveraged/risk-seeking product **with the risk shown up-front**; **Core 1× is the
  default for most capital.**
- **Code redos done this pass:** honest forecast wording, funding-staleness warning, telegram self-check.
- **Open items (non-blocking):** borrow-cost modelling for >1× exposure; a smoke test; refresh `funding.csv`
  in `fetch_data.py`; remove the `model_8b` alias post-cutover; **set the repo Telegram secrets** (yours).
