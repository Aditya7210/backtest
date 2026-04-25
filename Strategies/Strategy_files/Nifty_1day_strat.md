# Strategy: Nifty OI Pulse
### NSE Options Chain (OPTIDX) | Daily Timeframe

---

## Core Idea

> This strategy is built **exclusively on NSE Options Chain data** — signals invisible in regular price feeds.
> It exploits predictable institutional behavior through three quantitative signals:
> **PCR**, **Max Pain**, and **OI Writing Skew**.
>
> The underlying Nifty price itself is reconstructed from the options data via Put-Call Parity.
> No external price feed is needed.

---

## Why This Data is Special

Unlike standard OHLCV strategies, this strategy uses fields unique to the NSE Bhavcopy options dataset:

| CSV Column | Signal Derived |
|------------|----------------|
| `OPEN_INT` (per strike / type) | PCR and Max Pain computation |
| `CHG_IN_OI` at ATM strike | OI Writing Skew (institutional bias) |
| `SETTLE_PR` (CE + PE pairs) | Underlying price reconstruction via Put-Call Parity |
| `CONTRACTS` | Daily volume proxy / liquidity filter |
| `EXPIRY_DT` | Expiry cycle management — gamma risk avoidance |

---

## Price Reconstruction

Since only OPTIDX data is used, the underlying Nifty spot price is reconstructed daily using **Put-Call Parity**:

```
Spot ≈ Strike + CE_SETTLE_PR − PE_SETTLE_PR
```

- The ATM strike is the one where `|CE_price − PE_price|` is minimized
- That strike's implied spot is used as the daily **close price**
- High / Low are taken from the range of implied spots across ±5 strikes around ATM

---

## Signal Definitions

### Signal 1 — Put-Call Ratio (PCR)

```
PCR = Sum(PE Open Interest) / Sum(CE Open Interest)
      (for near-expiry strikes on a given trade date)
```

PCR is a classic **contrarian** indicator. When retail traders pile into puts (PCR spikes), the crowd is usually wrong — the market tends to reverse.

| PCR Value | Crowd Sentiment | Contrarian Signal |
|-----------|----------------|-------------------|
| > 1.30 | Extremely bearish | Bullish fade |
| 0.80 – 1.20 | Neutral / Sideways | No Trade Zone |
| < 0.70 | Extremely bullish | Bearish fade |

---

### Signal 2 — Max Pain

Max Pain is the strike price where **option writers (sellers) collectively lose the least** if the index expires there. Because option sellers are mostly institutional players with deep pockets, the market has a measurable tendency to gravitate toward Max Pain as expiry approaches.

```
For each candidate expiry price K (each strike):

  Total_Loss(K) =  Σ max(0, K − strike) × CE_OI    ← CE writer loss
                 + Σ max(0, strike − K) × PE_OI    ← PE writer loss

Max Pain = argmin(Total_Loss)
```

| Price vs Max Pain | Implication |
|-------------------|-------------|
| Price < Max Pain | Bullish gravitational pull toward Max Pain |
| Price > Max Pain | Bearish gravitational pull toward Max Pain |

Max Pain serves as both a **directional filter** and a **natural profit target**.

---

### Signal 3 — OI Writing Skew at ATM

```
OI Skew = CHG_IN_OI(ATM CE) − CHG_IN_OI(ATM PE)
```

When institutional market makers write (sell) options at ATM, they create directional pressure:

| OI Skew | Interpretation | Bias |
|---------|----------------|------|
| Negative ( < 0 ) | More puts being written = support at ATM | Bullish |
| Near zero | Balanced, no directional bias | Neutral |
| Positive ( > 0 ) | More calls being written = resistance at ATM | Bearish |

---

## Entry Conditions

All conditions must be TRUE simultaneously. No partial signals.

### Long Entry (Contrarian Bullish)

| # | Condition | Threshold | Reason |
|---|-----------|-----------|--------|
| 1 | PCR | > 1.30 | Crowd is excessively bearish |
| 2 | Reconstructed Close | < Max Pain | Price has room to rise toward gravity |
| 3 | OI Writing Skew | ≤ 0 | Institutions writing puts = support |
| 4 | Candle confirmation | Close > Open (green day) | Price beginning to reverse |
| 5 | Days to expiry | > 2 | Avoid explosive gamma risk near expiry |

### Short Entry (Contrarian Bearish)

| # | Condition | Threshold | Reason |
|---|-----------|-----------|--------|
| 1 | PCR | < 0.70 | Crowd is excessively bullish |
| 2 | Reconstructed Close | > Max Pain | Price has room to fall toward gravity |
| 3 | OI Writing Skew | ≥ 0 | Institutions writing calls = resistance |
| 4 | Candle confirmation | Close < Open (red day) | Price beginning to reverse |
| 5 | Days to expiry | > 2 | Avoid explosive gamma risk near expiry |

---

## Exit Conditions

Multiple exit conditions are checked on every bar. The first one triggered closes the position.

| Exit Type | Condition | Notes |
|-----------|-----------|-------|
| Fixed Stop Loss | 0.5% adverse move from entry | Hard floor — always active |
| Trailing Stop | 3% from peak (long) / trough (short) | Tightens as trade moves in profit |
| Target | Price reaches Max Pain level | Natural gravitational exit |
| Minimum R:R Target | Entry ± (SL × 2.0) | Ensures minimum 1:2 Risk:Reward |
| Time Exit | ≤ 2 days to expiry | Force close — avoids gamma explosion |
| PCR Reset (long) | PCR drops below 0.80 | Original signal invalidated |
| PCR Reset (short) | PCR rises above 1.20 | Original signal invalidated |

---

## Position Sizing

| Rule | Value |
|------|-------|
| Capital risked per trade | 1% of current portfolio value |
| Size formula | `floor(Capital × 1% / Stop Distance)` |
| Minimum size | 1 unit |
| Max trades per weekly expiry cycle | 2 |
| Pause after N consecutive losses | 2 |

---

## Major Rules (Non-Negotiable)

- [ ] Never trade when PCR is in neutral zone (0.70 – 1.30)
- [ ] Never enter within 2 days of expiry
- [ ] OI Skew must agree with PCR direction — both signals must align
- [ ] A confirmation candle (green for long, red for short) is mandatory
- [ ] Max Pain is always the primary profit target
- [ ] Stop loss is mandatory — no position averaging
- [ ] Pause all trading after 2 consecutive losses

---

## When NOT to Trade

| Condition | Reason |
|-----------|--------|
| PCR between 0.70 and 1.30 | No extreme sentiment — no edge |
| Days to expiry ≤ 2 | Gamma risk makes moves unpredictable |
| OI Skew contradicts PCR | Mixed institutional signal — skip |
| 2 consecutive losses | Circuit breaker — reassess the market |

---

## Strategy Logic Summary

```
Load Options Chain CSV
  → Compute PCR, Max Pain, OI Skew from OPEN_INT and CHG_IN_OI
  → Reconstruct spot price via Put-Call Parity
  → If PCR extreme + Max Pain directional + OI Skew agrees + Candle confirms
      → Enter with 0.5% SL and Max Pain target
  → Trail at 3% from peak/trough
  → Exit on: SL hit / Target reached / PCR reset / Expiry proximity
```