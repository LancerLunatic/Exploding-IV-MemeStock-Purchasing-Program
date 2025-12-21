# Option Trading Strategies

A collection of option trading strategies developed and tested over several years in live markets. Strategies are ranked by profitability and longevity (duration of sustained profitability in live trading).

---

## 1. VIX Put Spread Strategy ⭐ (Highest Performer)

**Status:** Manual trading only (not yet automated on QuantConnect)

### Strategy Overview
Sell put spreads on the VIX whenever it dips to $16 or below—historically, this is a reliable base level over the past several years. Monthly $1-wide spreads consistently deliver strong risk-adjusted returns.

**Target Entry Condition:** VIX ≤ $16

### Position Specifications
- **Sell:** 25 lots of 0.25 delta VIX puts (45 DTE)
- **Buy:** 25 lots of 0.20 delta VIX puts (45 DTE)
- **Spread Width:** $1.00
- **Expiration:** 45 days to expiration
- **Execution Frequency:** Every other Friday (26 entries per year)
- **Risk-Reward Ratio Target:** 2:3

### Concurrent Risk Profile
- **Overlapping Positions:** ~4 concurrent spreads typically active
- **Maximum Simultaneous Spreads:** 100
- **Capital Required:** $13,920 (maximum concurrent risk exposure)

### Performance Metrics

#### Returns & Risk-Adjusted Performance
| Metric | Value | Notes |
|--------|-------|-------|
| **Cash-on-Cash Return** | 100.9% | Annual return relative to capital at risk |
| **Annual Expected P&L** | $14,040 | Based on 26 annual entries |
| **Credit per Entry** | $907 | 25 spreads × per-spread credit |
| **Max Loss per Entry** | $3,480 | 25 spreads × $1.00 width |

#### Sharpe Ratio Analysis
| Metric | Value | Benchmark | Outperformance |
|--------|-------|-----------|-----------------|
| **Strategy Sharpe** | 4.43 | Exceptional | — |
| **S&P 500 Sharpe** | ~0.85 | Typical | +3.58 |
| **Hedge Fund Average** | ~1.12 | Industry avg | +3.31 |

**Interpretation:** A Sharpe ratio of 4.43 represents world-class risk-adjusted returns. This indicates the strategy generates $4.43 of excess return per unit of volatility—a significant edge over traditional equity and hedge fund strategies.

#### Additional Risk Metrics
| Metric | Value | Benchmark | Outperformance |
|--------|-------|-----------|-----------------|
| **Annualized Return** | 108.8% | — | — |
| **Annualized Volatility** | 23.7% | — | — |
| **MAR Ratio** | 5.62 | Excellent | — |
| **Max Drawdown** | -19.4% | Acceptable for strategy type | — |

**MAR Ratio Comparison:**
- **Strategy MAR:** 5.62 (Return ÷ |Max Drawdown|)
- **S&P 500 MAR:** ~0.45
- **Hedge Fund Average:** ~0.78
- **Strategy Advantage:** +4.84 vs hedge funds

---

## 2. Buy & Hold: SPY:XLU (3:1 Ratio)

**Status:** Simple, mechanical, fully tradeable on QuantConnect

### Strategy Overview
A passive allocation strategy using a 3:1 ratio of SPY to XLU (Utilities ETF). Self-explanatory core holding strategy.

### Position Specifications
- **Primary Holding:** SPY (80% of equity allocation)
- **Defensive Holding:** XLU (20% of equity allocation)
- **Rebalance Frequency:** Quarterly or as needed
- **Holding Period:** Long-term (months to years)

---

## 3. Inchworm Strategy

**Status:** Requires manual order management and active monitoring

### Strategy Concept
A "legging" strategy that systematically profits from mean reversion by rolling option spreads incrementally wider as profits accumulate. Works best on high-IV, expensive stocks (e.g., TSLA, MSTR in the $300+ range).

### Initial Screening
1. Navigate to Fidelity Options Screener
2. Identify stocks in a premium price range (currently $300+)
3. Filter for exceptionally high implied volatility (≥150% IV)
4. Verify bullish technicals: Look for cumulative call volume ≥50M contracts (very bullish signal)

### Position Construction
- **Call Debit Spread:** 60 DTE, $10 wide
- **Put Debit Spread:** 60 DTE, $10 wide
- **Entry:** Buy one of each on high-IV opportunities
- **Expiration:** 60 days to expiration

### Rolling/Legging Logic

#### Phase 1: First Roll (Short Leg at 50% Profit)
- **Trigger:** Total profit on short option reaches +50%
- **Action:** Roll short option to 15 DTE or 15 dollar wide (closes at debit)
- **Expected Outcome:** Profitable exit on short leg

#### Phase 2: Second Roll (Long Leg at 50% Profit)
- **Trigger:** Total profit on long option reaches +50%
- **Action:** Roll long option to 15 DTE or 15 dollar wide (closes at credit)
- **Expected Outcome:** Profitable exit on long leg

#### Ongoing Management
- **Objective:** "Inchworm" between 10-wide and 15-wide spreads
- **Execution:** Leg in/out on directional moves (up days vs. down days)
- **Profit Taking:** Systematically harvest profits as spreads widen

### Key Variables
- **Time to Expiration:** 60 DTE (initial entry), 30+ DTE (rolls)
- **Spread Width:** $10 initial, $15 target
- **Stock Requirements:** High IV (150%+), premium price ($300+)
- **Market Condition:** Works best in elevated-volatility environments

---

## 4. Poor Man's Covered Call (Call Spread Variant)

**Status:** Fully tradeable on QuantConnect

### Strategy Overview
A capital-efficient alternative to covered calls that uses a call spread to generate income against a longer-dated call purchase. The goal is to ensure the credit from selling the short call exceeds the debit paid for the long call.

### Position Construction
- **Long Leg:** Buy a 90 DTE call
- **Short Leg:** Sell a 30 DTE call against the long call (call spread)
- **Strike Selection:** Adjust deltas for 99% probability of profit (POP) at entry
  - Reference your trading platform's option screener/pre-order analysis tools

### Risk Management
- **Delta Optimization:** Size both legs to achieve 99% POP
- **Profit Requirement:** Credit received > Debit paid
  - If debit cost = $X, incoming credit must exceed $X for immediate profit

### Roll/Adjustment Strategy
- **Short Leg Expiration:** 30 days
- **Long Leg Expiration:** 90 days
- **Adjustment Trigger:** As short call approaches expiration (20-25 DTE)
- **Repeat:** Sell new 30 DTE call against the still-long 90 DTE call for additional credit

### Capital Efficiency
- **Advantage over Traditional Covered Calls:** Lower capital requirement (call spread vs. 100 shares)
- **Leverage:** Use buying power more efficiently while maintaining defined risk
- **Repeatable:** Reset every 30 days by selling new short call

---

## Summary Comparison

| Strategy | Complexity | Capital | Automation | Returns | Sharpe | Automation Difficulty |
|----------|-----------|---------|-----------|---------|--------|----------------------|
| VIX Put Spreads | High | High | Not yet | 108.8% | 4.43 ⭐ | Hard (VIX indexing) |
| Buy & Hold (SPY:XLU) | Very Low | Medium | Easy ✓ | ~12-15% | ~0.85 | Easy |
| Inchworm | Very High | Medium | No | High | Unknown | Very Hard |
| Poor Man's CC | Medium | Low | Partial | Moderate | Unknown | Medium |

---

## Implementation Notes

### Automation Status
- **VIX Strategies:** Requires direct Interactive Brokers API or Fidelity integration (not yet implemented on QuantConnect due to missing VIX index)
- **Equity Strategies (Inchworm, Poor Man's CC):** Can be partially automated; requires careful order management
- **Buy & Hold:** Fully automated and backtestable on QuantConnect

### Risk Considerations
- **VIX Put Spreads:** Tail risk during sudden VIX spikes; max drawdown of -19.4% observed
- **Inchworm:** Requires active management; significant slippage risk if not executed carefully
- **Poor Man's CC:** Gamma risk on short leg; monitor closely as expiration approaches

---

## References & Further Reading

For VIX-specific strategies:
- Monitor VIX Term Structure for entry signals
- Use Fidelity or thinkorswim for VIX options execution
- Track historical VIX levels and mean-reversion patterns

For equity strategies:
- Implied volatility should be elevated (>75th percentile) for optimal spreads
- Use open interest as a liquidity filter
- Consider industry/sector correlation before entering multiple positions

