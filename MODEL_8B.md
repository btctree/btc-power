# 8B Model — specification (5× leverage, HIGH RISK)

The "8B model" = diversified, regime-aware **ensemble** run at **5× leverage**, conviction-filtered
for ~60% trade win-rate. It earned ~$8.4B in backtest **only at ~0 slippage** (collapses by 20 bp)
with **−77% drawdown** and **liquidation risk**. Deployed as a labeled HIGH-RISK tier, not the core.

## 1. Market type (how it's decided)
Daily classification using **Wilder ADX** (trend strength), **+DI/−DI** (direction), **ATR%** (vol,
vs its trailing-365-day median), and SMA20/200 — with **2-day hysteresis** to avoid whipsaw:
- ADX ≥ 35 → STRONG_UP / STRONG_DOWN
- 20 ≤ ADX < 35 → TREND_UP (or PULLBACK_UP if below SMA20) / TREND_DOWN (or BOUNCE_DOWN above SMA20)
- ADX < 20 → CHOP_HIVOL (if ATR% high) else RANGE

## 2. Strategy used per market type
Each regime trades the **ensemble of engines that have proven robust edge there** (engines whose
*min(1st-half, 2nd-half) in-regime Sharpe ≥ 0.5*). The ensemble = the **average of those engines'
positions** (continuous −1…+1):

| Market type | Engines in the ensemble |
|---|---|
| STRONG_UP | OBV, BB, DSAM |
| TREND_UP | BB, MACD_SIG, DSAM |
| PULLBACK_UP | OBV, RSI |
| STRONG_DOWN | MFI (oversold bounce) |
| TREND_DOWN | MACD_SIG, BB |
| BOUNCE_DOWN | MACD, OBV_ROC, EMA |
| CHOP_HIVOL | DSAM, RSI |
| RANGE | MACD, OBV_ROC, EMA |

## 3. Confidence index
Two layers:
1. **Eligibility** — only engines with robust (both-halves) edge in the regime are used (≥0.5 Sharpe).
2. **Live confidence = |ensemble exposure|** (0→1) = how strongly the eligible engines agree on
   direction. A **conviction filter** requires |exposure| ≥ 0.4 to take a position (this raised the
   trade win-rate from 57% → ~60%; below 0.4 → stay flat).

## 4. Cut-loss
The model itself has **no per-trade trailing stop** (a key risk). Protection is:
- **Drawdown kill-switch** — halve exposure when equity is >30% below its peak.
- **Liquidation** at 5× ≈ a −20% adverse move (wipes the margin).
- **Recommended manual cut-loss = −15%** (placed *above* the −20% liquidation) so you exit before a
  forced liquidation. The live signal/Telegram publishes this exact price each day.

## 5. Sizing
`exposure = |ensemble| × 5 (leverage) × vol_scale`, where
`vol_scale = min(1, 60% / realized_vol_20d)` — caps exposure when volatility spikes.
Conviction filter zeroes it when |ensemble| < 0.4.

## 6. Margin level
At 5×, **margin = notional / 5**. A full-conviction signal (exposure 5.0× equity) uses **100% of
equity as margin** (notional = 5× equity); vol-scale and conviction reduce it. So margin usage ranges
0–100% of equity depending on conviction × volatility.

## Today's example (2026-06-23, BTC $62,735)
Regime STRONG_DOWN → engine MFI signals a bounce → ensemble +1.0 → **5× LONG**, margin 100%,
**cut-loss $53,324 (−15%)**, liquidation $50,188 (−20%). *(A 5× long bounce inside a downtrend — the
high-risk profile in a nutshell.)*

⚠️ Hypothetical; 5× leverage can be fully liquidated; the ~$8B headline assumes ~0 slippage and a
−77% drawdown path. Not financial advice. The safe alternative is the spot-1× signal shown alongside.
