#region imports
from AlgorithmImports import *
from collections import deque
#endregion

class MemeStocksStrategy(QCAlgorithm):
    """
    Strategy that screens for stocks based on volatility and options data,
    then purchases long-term call options (LEAPs) on them.
    12/4/2025 - minor tweaks to mx stock price, imp vol, stop loss and vix threshold to resemble the 2 year backtest that did 30%.
    also added ETFs. also rememeber that every 7 days is a weekend on screening and no trades will trigger.
    SPX- YTD up 12.5% as of 12/4/2025
    spx - 2024 perf - 24.01 SPX 2023 Annaul Perf - 24.73%
    so if im starting in 1//1/2023 i need to beat ...70% return and 20.5% drawdown in spring 2025... so i can hit 50% return and 10% drawdown or
    other combination.

    Developer Notes (12/08/2025):
    - Renamed class to MemeStocksStrategy.
    - Added slippage calculation logging for orders of 100+ shares to monitor execution costs.
    - Significantly reduced logging verbosity across the algorithm (screening, order events, exits) to lower memory usage and prevent crashes in a live environment.
    - Implemented a portfolio-wide daily loss limit (5%) to liquidate all positions and halt trading for the day as a major risk management feature.
   Developer Notes (12/09/2025): added logic to use last known price of vix and reduce checks of vix to one during screening by not using ondata
   Developer Notes (12/18/2025):
    - Refactored to use `AddOption` universe and directly extract `ImpliedVolatility` from `OptionContract` objects within `data.OptionChains`, replacing the manual `GetImpliedVolatility` function and the built-in `IV` indicator.
    - Implemented a `self.iv_cache` that is updated every tick from `data.OptionChains` to provide fresh IV values for screening.
    - Modified screening logic to use absolute IV for the initial run and the 14-day IV increase for subsequent runs.
    - Added a safety check for empty option chains before calculating the call/put ratio to prevent runtime errors.
    - **Debugging Lessons (IV Caching):** To fix empty IV data, we stripped down `CacheImpliedVolatility` to its simplest form. Logging at each step confirmed IV was being read but not stored. The fix was adding the single line to populate `self.iv_cache`.
    12-15-2025 - changed top 50 to top 30 and trades 15 instead of 25. fixed expiration filter mismatch and aligned IV calculation to those new 25-60 days  
    this will hopefully get some options chains to load correctly from live market. 
    """

    def Initialize(self):
        """Initialize the algorithm."""
        self.SetStartDate(2022, 11, 15)
        self.SetEndDate(2025, 12, 1)
        self.SetCash(100000)
        self.SetWarmup(timedelta(days=7))

        # Set commission for IB but comment it out as not ready for live money trading yet
        # self.SetBrokerageModel(BrokerageName.InteractiveBrokers, AccountType.Margin)
        # self.Log(f"Commission cost per trade: ~${len(self.Portfolio) * 0.10}")

        # === Strategy Parameters ===
        self.MIN_STOCK_PRICE = 2.50
        self.MAX_STOCK_PRICE = 350.00
        self.MIN_IMPLIED_VOLATILITY = 0.50   # 100%
        self.STOP_LOSS_PERCENT = -0.15  # Stop Loss at 15% loss
        self.TAKE_PROFIT_PERCENT = 0.33  # Take Profit at 300% gain
        self.POSITION_ALLOCATION = 0.02 # 2% per new position
        self.SPY_ALLOCATION = 0.80
        self.XLU_ALLOCATION = 0.20
        self.MAX_PORTFOLIO_ALLOCATION = 1.6 # Max 85% of portfolio in stocks but my PM always under 40%
        self.VIX_THRESHOLD = 20.50 # VIX level to define a BEAR market regime
        
        
        # === Internal State ===
        self.last_rebalance_date = None
        self.rebalance_frequency_days = 90  # Quarterly (every 90 days)
        self.trade_dates = {}
        self.previous_iv = {}  # To store the previous screening's IV for comparison
        self.iv_cache = {}     # To store the latest implied volatility for each underlying
        self.last_screening_date = None
        self.screening_frequency_days = 14  # Every 2 weeks (change to 21 for 3 weeks)
        self.vix = None # To hold the VIX symbol
        self.market_regime = 'BULL' # Start with a BULL assumption

        # === Daily Loss Limit ===
        self.daily_loss_limit = -0.05 # -5%
        self.portfolio_value_at_start_of_day = 0
        self.last_loss_limit_date = None

        # Set universe settings
        self.UniverseSettings.Asynchronous = True
        self.UniverseSettings.Resolution = Resolution.Hour
        # Set data normalization to RAW. CRITICAL for options - without this, Greeks and IV won't calculate correctly.
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Raw

        # Add the universe selection function. The timing of the screening is handled by a scheduled event.
        # This will select our base equities.
        universe = self.AddUniverse(self.UniverseSelectionFunction)

        # Chain an options universe to the equity universe, filtering for front-month contracts +/- 10 strikes
        self.AddUniverseOptions(universe, self.OptionFilterFunction)
        # The iv_cache will store the latest implied volatility for each symbol, populated from OptionChains.
        
        # Add VIX data to use as a market regime filter
        # TEMPLATE NOTE: VIX must be added as an Index, not an Equity, to ensure data is loaded correctly.
        self.vix = self.AddIndex("VIX", Resolution.Daily).Symbol
        self.spy = self.AddEquity("SPY", Resolution.Hour).Symbol
        self.xlu = self.AddEquity("XLU", Resolution.Hour).Symbol
        
       # === Slippage Tracking ===
        self.daily_slippage_dollars = 0.0  # Total $ slippage today
        self.daily_trades_count = 0         # Number of trades today
        self.last_slippage_reset_date = None

        #Email Notification
        self.last_email_date = None
        
        # === DEBUGGING ===
        self.last_diagnostic_time = None

        # === SCHEDULED EVENTS ===
        # Schedule the main screening and trading logic to run once per week.
        # This is the correct way to align data access for multiple securities.
        self.Schedule.On(self.DateRules.Every(DayOfWeek.Monday), 
                         self.TimeRules.At(10, 0), 
                         self.PerformWeeklyScreening)

    def OptionFilterFunction(self, option_filter_universe: OptionFilterUniverse) -> OptionFilterUniverse:
        """Option filter for selecting desired option contracts."""
        return option_filter_universe.Strikes(-10, +10).FrontMonth()

        # Note: In a longer-running algorithm, you might also want to handle `changes.RemovedSecurities` to clean up indicators.

    def UniverseSelectionFunction(self, coarse: List[CoarseFundamental]) -> List[Symbol]:
        
        price_filtered = [c for c in coarse 
                        if self.MIN_STOCK_PRICE < c.Price < self.MAX_STOCK_PRICE]
        self.Log(f"UNIVERSE: Passed price filter: {len(price_filtered)}")
        
        filtered = [c for c in coarse 
                    if self.MIN_STOCK_PRICE < c.Price < self.MAX_STOCK_PRICE 
                    and c.DollarVolume > 6700000]
        self.Log(f"UNIVERSE: Passed volume filter (>500k): {len(filtered)}")
        
        top_30 = sorted(filtered, key=lambda c: c.DollarVolume, reverse=True)[:30]
        self.Log(f"UNIVERSE: Final selection: {len(top_30)} stocks")
        
        return [c.Symbol for c in top_30]

    def OnSecuritiesChanged(self, changes: SecurityChanges):
        """
        Handles security changes in the algorithm.
        """
        pass

    def OnData(self, data):
        """Main trading logic - executed on data events."""
        # TEMPLATE NOTE: The main logic is called from OnData, not a scheduled event.
        # This is CRITICAL because it provides the 'data' slice, which is the only
        # way to access fresh OptionChains data for IV calculation.
        if self.IsWarmingUp:
            return

        # === Initial Rebalancing (after warmup) ===
        if self.last_rebalance_date is None:
            self.Log("Warmup finished. Performing initial ETF rebalancing.")
            self.SetHoldings(self.spy, self.SPY_ALLOCATION)
            self.SetHoldings(self.xlu, self.XLU_ALLOCATION)
            self.last_rebalance_date = self.Time.date()

        # Cache implied volatility from option chains every tick
        self.CacheImpliedVolatility(data)

        # === Weekly Screening Gate ===
        # The scheduled event now just sets a flag. The actual screening happens in OnData
        # to ensure we have access to the 'data' slice with fresh option chains.
        self.WeeklyScreeningAndTrading(data)

        # === DAILY SUMMARY LOG (triggered ~30 min after market close) ===
        # Market closes at 4 PM EST. This runs on first data after 4:30 PM.
        if self.Time.hour == 16 and self.Time.minute >= 30 and self.last_email_date != self.Time.date():
            portfolio_value = self.Portfolio.TotalPortfolioValue
            unrealized_pnl = self.Portfolio.TotalUnrealizedProfit
            invested_count = len([h for h in self.Portfolio.Values if h.Invested])
            active_count = len([s for s in self.ActiveSecurities.Values if s.Type == SecurityType.Equity])
            self.Log(f"UNIVERSE (9:31 AM): Active securities: {active_count}")

            # Calculate daily P&L
            daily_pnl_pct = None
            if self.portfolio_value_at_start_of_day > 0:
                daily_pnl_pct = ((portfolio_value - self.portfolio_value_at_start_of_day)
                                / self.portfolio_value_at_start_of_day) * 100
            daily_pnl_str = "N/A" if daily_pnl_pct is None else f"{daily_pnl_pct:.2f}%"

            # Calculate average slippage per trade
            avg_slippage_per_trade = self.daily_slippage_dollars / self.daily_trades_count if self.daily_trades_count > 0 else 0

            # --- Build and Send Daily Summary Email ---
            summary_subject = f"Daily Summary: {self.Time.date().strftime('%Y-%m-%d')}"
            summary_message = f"""
            === DAILY SUMMARY ===
            Date: {self.Time.date().strftime('%Y-%m-%d')}
            Portfolio: ${portfolio_value:,.2f}
            Daily P&L: {daily_pnl_str}
            Unrealized: ${unrealized_pnl:,.2f}
            Positions: {invested_count}
            Cash: ${self.Portfolio.Cash:,.2f}
            Trades: {self.daily_trades_count} | Slippage: ${self.daily_slippage_dollars:.2f} | Avg: ${avg_slippage_per_trade:.2f}
            Market Regime: {self.market_regime}
            ====================
            """
            # Log the summary to the console
            self.Log(summary_message)
            
            # Send the email notification
            # IMPORTANT: Replace with your actual email address
            self.Notify.Email("dca.llc.md@gmail.com", summary_subject, summary_message)

            self.last_email_date = self.Time.date()

        # Initialize start-of-day portfolio value on the first run
        if self.portfolio_value_at_start_of_day == 0:
            self.portfolio_value_at_start_of_day = self.Portfolio.TotalPortfolioValue

        # Reset daily anchor at the start of a new trading day
        if self.last_loss_limit_date is None or self.Time.date() > self.last_loss_limit_date:
            self.portfolio_value_at_start_of_day = self.Portfolio.TotalPortfolioValue
            self.last_loss_limit_date = self.Time.date()

        # === Daily Loss Limit Check ===
        if self.portfolio_value_at_start_of_day > 0:
            daily_pnl_pct = (
                self.Portfolio.TotalPortfolioValue - self.portfolio_value_at_start_of_day
            ) / self.portfolio_value_at_start_of_day

            if daily_pnl_pct < self.daily_loss_limit:
                self.Log(f"EMERGENCY EXIT: Daily loss {daily_pnl_pct:.2%} < limit {self.daily_loss_limit:.2%}. Liquidating and pausing.")
                self.Liquidate()
                # Halt further trading for the day by setting a high VIX regime
                self.market_regime = 'BEAR' 
                return
        
        # Manage existing positions with the current data slice
        self.ManagePositions(data)

    def PerformWeeklyScreening(self):
        """
        Scheduled event that simply sets the screening date.
        This acts as a trigger for the logic inside OnData.
        """
        self.last_screening_date = self.Time.date()

    def WeeklyScreeningAndTrading(self, data):
        # === Check if enough days have passed since last screening ===
        if self.last_screening_date != self.Time.date():
            return # Only run on the day the scheduled event fires
        
        if (self.Time.date() - self.last_rebalance_date).days >= self.rebalance_frequency_days:
            self.Log(f"Quarterly Rebalancing: Setting SPY to {self.SPY_ALLOCATION:.0%}, XLU to {self.XLU_ALLOCATION:.0%}")
            self.SetHoldings(self.spy, self.SPY_ALLOCATION)
            self.SetHoldings(self.xlu, self.XLU_ALLOCATION)
            self.last_rebalance_date = self.Time.date()
        vix_security = self.Securities[self.vix]
        
        if vix_security.HasData and vix_security.Price > 0:
            vix_price = vix_security.Price
            
            # Update regime only if we have fresh VIX data
            if vix_price > self.VIX_THRESHOLD:
                self.market_regime = 'BEAR'
            else:
                self.market_regime = 'BULL'
            
            self.Log(f"VIX={vix_price:.2f} | Regime: {self.market_regime}")
        else:
            # Use last known regime if VIX unavailable (don't skip screening!)
            self.Log(f"VIX unavailable, using last known regime: {self.market_regime}")
        
        if self.market_regime == 'BEAR':
            self.Log(f"Market regime is BEAR. Pausing new trades.")
            return  # Don't screen in bear market
        
        # --- Screening Logic using IV Cache ---
        # Use a copy of the cache to avoid issues if the cache is modified during screening
        current_iv_data = self.iv_cache.copy()

        # Ensure we only consider symbols that are currently in our universe
        # This cleans up any stale IV data for symbols that might have left the universe
        active_equity_symbols = {s.Symbol for s in self.ActiveSecurities.Values if s.Type == SecurityType.Equity and s.Symbol not in [self.spy, self.xlu]}
        current_iv_data = {s: iv for s, iv in current_iv_data.items() if s in active_equity_symbols}

        self.Log(f"SCREENING: Found {len(current_iv_data)} stocks with a ready IV indicator.")

        # Determine the pool of candidates for trading
        candidate_pool = {}
        is_initial_run = not self.previous_iv

        if is_initial_run:
            self.Log("Initial screening run: Selecting stocks based on highest absolute IV.")
            # On the first run, we use the absolute IV values
            candidate_pool = current_iv_data
        else:
            # On subsequent runs, calculate the increase in IV
            iv_increase_data = {}
            for symbol, current_iv in current_iv_data.items():
                if symbol in self.previous_iv:
                    previous_iv = self.previous_iv[symbol]
                    # Only consider stocks where IV has actually increased
                    iv_increase = current_iv - previous_iv
                    if iv_increase > 0:
                        iv_increase_data[symbol] = iv_increase
                        self.Log(f"IV_CHANGE: {symbol.Value}: Current IV {current_iv:.4f} - Previous IV {previous_iv:.4f} = Increase {iv_increase:.4f}")
            
            self.Log(f"SCREENING: Found {len(iv_increase_data)} stocks with an IV increase since last screening.")
            candidate_pool = iv_increase_data

        # --- Sentiment Analysis ---
        # We still use the call/put ratio as a secondary filter
        bullish_sentiment_pool = {}
        for symbol, value in candidate_pool.items():
            # Ensure the option chain exists and has contracts to avoid errors
            if not data.OptionChains.ContainsKey(symbol) or len(data.OptionChains[symbol]) == 0:
                continue

            chain = data.OptionChains[symbol]
            contracts = chain.Contracts.values()
            
            total_call_volume = sum(c.Volume for c in contracts if c.Right == OptionRight.Call)
            total_put_volume = sum(c.Volume for c in contracts if c.Right == OptionRight.Put)

            call_put_ratio = float('inf') if total_put_volume == 0 and total_call_volume > 0 else (total_call_volume / total_put_volume if total_put_volume > 0 else 0)

            if call_put_ratio >= 1.10:
                # The 'value' is either the absolute IV (first run) or the IV increase (subsequent runs)
                bullish_sentiment_pool[symbol] = value

        self.Log(f"SCREENING: {len(bullish_sentiment_pool)} stocks passed sentiment filter (Call/Put Ratio >= 1.10).")

        if not bullish_sentiment_pool:
            self.Log("No candidates passed all filters. Skipping this screening cycle.")
            return

        # Rank candidates by their value (either absolute IV or IV increase)
        self.Log(f"Ranking candidates by {'absolute IV' if is_initial_run else 'IV increase'}.")
        top_sorted = sorted(bullish_sentiment_pool.items(), key=lambda item: item[1], reverse=True)

        # Select the top 15 symbols to trade
        top_15_symbols = [symbol for symbol, _ in top_sorted[:15]]

        for symbol in top_15_symbols:
            current_stock_allocation = self.Portfolio.TotalHoldingsValue / self.Portfolio.TotalPortfolioValue
            if current_stock_allocation + self.POSITION_ALLOCATION > self.MAX_PORTFOLIO_ALLOCATION:
                break
            if self.Portfolio[symbol].Invested:
                continue
            self.Log(f"[BUY] {symbol.Value}: Current allocation {current_stock_allocation:.2%}. Adding new {self.POSITION_ALLOCATION:.0%} position.")
            self.SetHoldings(symbol, self.POSITION_ALLOCATION)
            self.trade_dates[symbol] = self.Time.date()
        
        # Save the current IV data to be used as 'previous' in the next screening cycle
        self.previous_iv = current_iv_data
                
    def CacheImpliedVolatility(self, data):
        """
        Caches the Implied Volatility (IV) for each underlying equity from the OptionChains.
        This method is called every tick from OnData to ensure the cache is fresh.
        """
        for chain in data.OptionChains.values():
            underlying_symbol = chain.Underlying.Symbol  # Use this like the working code
            
            # Validate the underlying has data
            if not self.Securities.ContainsKey(underlying_symbol) or not self.Securities[underlying_symbol].HasData:
                continue
            
            underlying_price = self.Securities[underlying_symbol].Price
            if underlying_price <= 0:
                continue
            
            try:  # Wrap filtering in try-catch to catch date calculation issues
                # Filter for liquid Call options in the desired DTE range (7-39 days)
                calls = [c for c in chain.Contracts.values()
                         if c.Right == OptionRight.Call and
                         (c.Volume > 0 or c.OpenInterest > 0) and
                         7 <= (c.Expiry.date() - self.Time.date()).days <= 39]
                
                if not calls:
                    # Fallback: if no calls in primary DTE range, try closest to 23 days
                    all_calls_with_liquidity = [c for c in chain.Contracts.values()
                                                if c.Right == OptionRight.Call and
                                                (c.Volume > 0 or c.OpenInterest > 0)]
                    if all_calls_with_liquidity:
                        calls = sorted(all_calls_with_liquidity, 
                                       key=lambda c: abs((c.Expiry.date() - self.Time.date()).days - 23))[:5]
                    if not calls:
                        continue  # No suitable calls found
                
                # Select the ATM contract
                atm_contract = min(calls, key=lambda c: abs(c.Strike - underlying_price))
                
                # Store the IV
                if atm_contract.ImpliedVolatility is not None and atm_contract.ImpliedVolatility > 0:
                    if self.iv_cache.get(underlying_symbol) != atm_contract.ImpliedVolatility:
                        self.iv_cache[underlying_symbol] = atm_contract.ImpliedVolatility
                        
            except Exception as e:
                self.Log(f"[IV_ERROR] Failed to cache IV for {underlying_symbol.Value}: {str(e)}")
                continue


    def ManagePositions(self, data):
        """Scheduled function to manage open positions."""
        # This function is called from OnData and is responsible for managing
        # existing positions based on price updates (stop loss, take profit).
        # It needs the `data` slice to check for stop-loss conditions based on IV, if re-enabled.
    
        # Timeout protection - timezone safe
        for order_ticket in self.Transactions.GetOpenOrderTickets():
            try:
                # Safe subtraction using datetime utilities
                time_open = (self.Time - order_ticket.Time).total_seconds()
                if time_open > 125:
                    self.Log(f"⚠️ Order timeout {order_ticket.Symbol} (ID:{order_ticket.OrderId}). Canceling.")
                    order_ticket.Cancel()
            except TypeError as e:
                # Skip if timezone issue (rare but safe)
                self.Log(f"⚠️ Skipping timeout check for order {order_ticket.OrderId}: {str(e)[:50]}")
                continue

        for holding in self.Portfolio.Values:
            
            if not holding.Invested or holding.Type != SecurityType.Equity or holding.Symbol in [self.spy, self.xlu]:
                continue

            symbol = holding.Symbol
            unrealized_profit_percent = holding.UnrealizedProfitPercent
            '''
            # 3. IV Stop Loss: Exit if the reason for entry (high IV) is gone
            # To re-enable this, you would use self.iv_cache[symbol] to get the latest IV
            # current_iv = self.iv_cache.get(symbol, 0.0) # Get from cache, default to 0 if not found
            # if 0 < current_iv < self.MIN_IMPLIED_VOLATILITY: # Assuming MIN_IMPLIED_VOLATILITY is the threshold for exit
            #     self.Log(f"IV STOP LOSS for {symbol.Value}. Current IV {current_iv:.2%} < Threshold {self.MIN_IMPLIED_VOLATILITY:.2%}. Liquidating.")
                self.Liquidate(symbol)
                if symbol in self.trade_dates: del self.trade_dates[symbol]
                continue # Move to next holding
            '''        
            # 1. Stop Loss
            if unrealized_profit_percent <= self.STOP_LOSS_PERCENT:
                self.Liquidate(symbol)
                if symbol in self.trade_dates: del self.trade_dates[symbol]
                continue # Move to next holding

            # 2. Take Profit
            if unrealized_profit_percent >= self.TAKE_PROFIT_PERCENT:
                self.Liquidate(symbol)
                if symbol in self.trade_dates: del self.trade_dates[symbol]
                continue # Move to next holding\

    def OnOrderEvent(self, orderEvent: OrderEvent):
        """Handle order events for logging."""
        if orderEvent.Status != OrderStatus.Filled:
            return

        order = self.Transactions.GetOrderById(orderEvent.OrderId)
        
        # Reset daily slippage at start of new trading day
        if self.last_slippage_reset_date is None or self.Time.date() > self.last_slippage_reset_date:
            self.daily_slippage_dollars = 0.0
            self.daily_trades_count = 0
            self.last_slippage_reset_date = self.Time.date()
        
        # Log large trades (>100 shares) for visibility
        if order.AbsoluteQuantity >= 100:
            self.Log(f"FILLED {order.Symbol.Value} {order.Quantity} @ ${orderEvent.FillPrice:.2f}")
        
        # === Calculate and accumulate slippage ===
        market_price = self.Securities[order.Symbol].Price
        
        if market_price > 0:
            filled_price = orderEvent.FillPrice
            
            # Calculate slippage in dollars (absolute impact per share)
            if order.Direction == OrderDirection.Buy:
                slippage_per_share = filled_price - market_price  # Negative = good (bought cheaper)
            else:  # Sell
                slippage_per_share = market_price - filled_price  # Negative = good (sold more)
            
            # Total slippage for this trade in dollars
            trade_slippage_dollars = slippage_per_share * order.AbsoluteQuantity
            
            # Accumulate daily slippage
            self.daily_slippage_dollars += trade_slippage_dollars
            self.daily_trades_count += 1
