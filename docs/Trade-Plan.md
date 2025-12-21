This is a collection of option trading plans I have used over the years. Some have worked for a couple weeks to a couple months.

Strategies ranked in order of profitability + longevity[time spent being profitable in live markets]

1. Sell VIX Put Spreads: I have not been able to automate this on quantconnect because they don't offer VIX index. I haven't taken the time to create a hosting env to run a script directly on
interactive brokers to trade vix. Its easier to trade on fidelity.
Sell Put spreads whenever the vix gets down to the $16 or below mark. This is generally where its beeen basing out for the last several years. I've noticed selling monthly $1 wide
works very well. i Look to get 2:3 risk reward ratio.
Comprehensive Performance Analysis
Based on my detailed analysis of selling 25 lots of 0.25 delta VIX puts while buying 25 lots of 0.2 delta VIX puts, executed every other Friday with 45-day expiration, here are the comprehensive performance metrics:
Strategy Specifications
Position Structure:
Sell: 25 lots of 0.25 delta VIX puts (45 DTE)
Buy: 25 lots of 0.2 delta VIX puts (45 DTE)
Frequency: Every other Friday (26 entries per year)
Overlapping Positions: 4 concurrent positions typically active
Maximum Exposure: 100 spreads simultaneously
VIX delta put spread strategy performance showing excellent risk-adjusted returns with 100.9% cash-on-cash return, 4.43 Sharpe ratio, and minimal drawdowns
Key Performance Metrics
Cash on Cash Return: 100.9%
Required Capital: $13,920 (maximum concurrent risk)
Annual Expected P&L: $14,040
Credit per Entry: $907 (25 spreads)
Max Loss per Entry: $3,480 (25 spreads)
Sharpe Ratio: 4.43
Annualized Return: 108.8%
Annualized Volatility: 23.7%
Risk-Free Rate: 4.0% (3-month Treasury)
Excess Return: 104.8%
This Sharpe ratio of 4.43 is exceptional, indicating outstanding risk-adjusted performance. For context:
S&P 500 typical Sharpe: ~0.85
Hedge fund average: ~1.12
Strategy outperforms by +3.58 vs S&P 500
MAR Ratio: 5.62
Annualized Return: 108.8%
Maximum Drawdown: -19.4%
MAR = Return / |Max Drawdown|: 5.62
The MAR ratio of 5.62 indicates excellent drawdown-adjusted returns, significantly outperforming typical benchmarks:
S&P 500 MAR: ~0.45
Hedge fund average MAR: ~0.78
Strategy advantage: +4.84 vs hedge funds

3. Buy and hold : SPY:XLU (3:1) - self explanitory

4. Inch worm 
  1. Search google for fidelity options screener, click that link. 
2Look for stock thats very expensive . at the time of this righting that is in the $300 range (TSLA and MSTR)
3Also make sure the stock is really high IV…like 150% IV. you will need option screener for this. 
4Find the cumulative call have to be huge like 50million ver ybullish. 
5Buy 1 call debit spread and 1 put debit spread 60 DTE, 10$ wide spreads only.
6When total profit hits 50% on the short option, roll it to 15 dollars wide. This should close for a debit. profitable.
7When total profit hits 50% on the long option roll it to 15 dollars wide, this should close for a credit. profitable
8The goal is to inchworm between 10 and 15 dollar spreads, “legging”up and down on up days and down days of the stock. 


5. Poor Mans Covered Call - Call Spread
   Buy a 90 day expiration call and sell a 30 day expiration call spread agaisnt it, adjust delta so that probability of profit is 99% in your trading platform preorder screen of choice.
   the credit received should be greater than the debit to purchase the naked long call at 90 day expiration.
