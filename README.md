# High IV Momentum Trading Strategy
I created this to showcase my capabilities as a full cycle quantitative developer and trader. I am open to quant trader/quant dev/quant analyst roles with hybrid in-office style in Washington, DC, NYC and surrounding areas. I have been trading manually all asset classes starting with stocks in 2011.
I like they concept of algorithmic trading because I know my trade plan/rules will always be followed where as a human can deviate due to ego.

About me ([linkedin](https://www.linkedin.com/in/marylandman/) vquantconnec](https://www.quantconnect.com/u/apollos_hill)

[LinkedIn](https://www.linkedin.com/in/YOUR-PROFILE-HERE) | [QuantConnect](https://www.quantconnect.com/u/apollos_hill)

Technical Stack:
- Full cycle trade developer
- Live Equity/Index/Future option chains
- DTE/volume filtering + sentiment analysis
- VIX regime detection + position sizing
- QuantConnect LEAN engine integration

 ## Key Metrics
**Entry Signal**: ATM calls with 7-39 DTE, IV increase > 1.5%

**Filters**: 0.5M+ daily volume, Call/Put ratio ≥ 1.10 (sentiment filter)

**Backtest Period**: Dec 2022 to Dec 2025

**Trades**: 50+ positions initiated

**Allocation Growth**: From 99% → 160% across testing period

**Total Return**: +88.5% (from $100K to $193K initial assessment, ending at $186.6K)

**Annualized Return**: ~28% (highly volatile)

**Maximum Drawdown**: -10.4% (multiple occurrences: Dec 2022, Mar 2025)

**Best Monthly Return**: +12.48% (Nov 2023)

**Worst Monthly Return**: -10.23% (Mar 2025)

## Technical Implementation
- **Language**: Python | **Framework**: QuantConnect LEAN
- **IV Extraction**: Real-time option chain parsing
- **Risk Management**: Position sizing, regime detection (VIX-based)
- **Schedule**: Monday IV screening + daily momentum detection

## 2026 Future Enhancements
- [ ] Put/call spread implementation
- [ ] Greeks-based hedge sizing
- [ ] ML classifier for false signal reduction


## Overview
1. **Universe Selection (Daily)**  
Every day, the algorithm filters the entire US Equity market to select a "Universe" of 30 stocks to monitor.

- **Price Filter:** Stocks must be priced between $2.50 and $350.00.  
- **Volume Filter:** Stocks must have a daily Dollar Volume greater than $6,700,000.  
- **Ranking:** It sorts the passing stocks by Dollar Volume and keeps the top 30.

2. **Data Collection & IV Caching (Real-Time)**  
Once the universe is selected, the algorithm subscribes to the Option Chains for these 30 stocks.

- **Option Filter:** It looks for "Front Month" contracts within +/- 10 strikes of the current price.  
- **IV Extraction:** On every data tick, it scans the option chains to find a specific contract:  
  - **Type:** Call Option.  
  - **Liquidity:** Must have Volume or Open Interest > 0.  
  - **Expiration:** Between 7 and 39 days out (with a fallback logic to find contracts near 23 days if none exist).  
  - **Strike:** At-The-Money (closest to current stock price).  
- **Caching:** It extracts the Implied Volatility (IV) from this specific contract and saves it to `self.iv_cache`.

3. **Scheduled Screening (Weekly)**  
The actual decision to trade happens once a week, scheduled for Mondays at 10:00 AM.

A. **Market Regime Check**  
Before looking at specific stocks, it checks the overall market health using the VIX (Volatility Index).

- If VIX > 20.50, the market is deemed "BEAR". The algorithm halts and does not open new trades.  
- If VIX ≤ 20.50, it proceeds as a "BULL" market.

B. **Candidate Filtering**  
It takes the 30 stocks from the universe and filters them based on Volatility behavior:

- **Initial Run:** It considers all stocks in the cache.  
- **Subsequent Runs:** It compares the current IV to the previous week's IV. It only keeps stocks where the IV has increased.

C. **Sentiment Filter (Call/Put Ratio)**  
For the remaining candidates, it calculates a sentiment score using the option chain:

- It sums the total Volume of Calls and Puts.  
- It calculates the Call/Put Ratio.  
- **Condition:** The stock is only selected if the Ratio ≥ 1.10 (indicating bullish sentiment).

D. **Ranking**  
The passing stocks are ranked by their IV metric (highest absolute IV on the first run, or highest IV increase on subsequent runs).  
The algorithm selects the Top 15 stocks from this ranked list.

4. **Execution**  
The algorithm iterates through the Top 15 selected stocks.

- **Asset Class:** Despite “LEAPs” (options) being mentioned in the strategy name, the code executes `self.SetHoldings(symbol, ...)`, which buys the underlying stock (Equity).  
- **Sizing:** It allocates 2% of the portfolio to each position.  
- **Constraints:** It stops buying if the total equity allocation exceeds the maximum portfolio limit (set to 1.6, or 160% leverage, though individual position sizing limits this naturally).

5. **Position Management (Real-Time)**  
Once a trade is open, it is managed continuously in `OnData`:

- **Stop Loss:** Liquidates if the position loses 15% (-0.15).  
- **Take Profit:** Liquidates if the position gains 33% (0.33).  
- **Daily Loss Limit:** If the entire portfolio drops by 5% in a single day, it liquidates all positions and halts trading for the day.

**Status**: ✅ Live [Paper] trading December 2025 | Almost ready for production | Major Issue : IV data not received by definition for trading
