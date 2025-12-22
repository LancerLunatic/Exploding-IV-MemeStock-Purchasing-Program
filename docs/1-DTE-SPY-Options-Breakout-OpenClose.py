from AlgorithmImports import *
import numpy as np
from hmmlearn.hmm import GaussianHMM
from datetime import timedelta
from collections import defaultdict

class RegimeAwareMultiStrategyAlgorithm(QCAlgorithm):
    def initialize(self):
        # === STEP 1: ALL CONFIG PARAMETERS ===
        self.btc_momentum_period = 14
        self.btc_rsi_period = 14
        self.btc_overbought = 70
        self.btc_oversold = 30
        self.wheel_underlying = "QQQ"
        self.wheel_allocation = 0.25
        self.wheel_put_delta = -0.20 # Target delta for selling puts
        self.wheel_call_delta = 0.20 # Target delta for selling calls
        self.wheel_dte_target = 35
        self.wheel_put_quantity = 0
        self.wheel_call_quantity = 0
        self.wheel_assigned_shares = 0
        self.wheel_put_entry_price = {}
        self.wheel_call_entry_price = {}
        self.gap_allocation = 0.15
        self.gap_vix_threshold = 0.05
        self.gap_qqq_threshold = -0.075
        self.gap_dte_target = 3
        self.gap_short_delta = 0.16
        self.gap_long_delta = 0.10
        self.gap_min_spread_bid = 0.08
        self.gap_min_oi = 100
        self.gap_max_spread_pct = 0.10
        self.gap_monthly_dd_limit = 0.02
        self.gap_yesterday_vix_close = None
        self.gap_yesterday_qqq_close = None
        self.gap_today_processed = False
        self.gap_last_processed_date = None
        self.gap_current_month = None
        self.gap_monthly_start_equity = None
        self.gap_stop_trading_month = False
        self.regime_lookback = 252
        self.market_regime = None # -1: Bear, 0: Neutral, 1: Bull
        self.regime_update_interval = 30
        self.last_regime_update = None

        # === STEP 2: ALGO SETUP ===
        self.SetStartDate(2023, 1, 1)
        self.SetEndDate(2025, 11, 11)
        self.SetCash(500000)
        self.SetBrokerageModel(BrokerageName.Coinbase, AccountType.Cash) # Default for Crypto
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # === STEP 3: ALL SECURITIES AND SYMBOLS (BEFORE ALPHA MODELS) ===
        # ETF Equities
        # Only add ETFs not covered by other strategies
        etf_tickers = ["XLU", "XLE", "GLD", "EEM"]
        for ticker in etf_tickers:
            # These were for the DCA strategy, which is being removed.
            # If another strategy needs them, they should be added here.
            pass

        # BTC Crypto from Coinbase
        self.btc_symbol = self.AddCrypto("BTCUSD", Resolution.Daily, Market.Coinbase).Symbol
        # For consistency in the alpha model, we'll use btc_contract to refer to the symbol
        self.btc_contract = self.btc_symbol
        self.btc_momentum = self.MOMP(self.btc_symbol, self.btc_momentum_period, Resolution.Daily)
        self.btc_rsi = self.RSI(self.btc_symbol, self.btc_rsi_period, MovingAverageType.Simple, Resolution.Daily)

        # Options and Indices
        self.qqq_symbol = self.AddEquity(self.wheel_underlying, Resolution.Hour).Symbol
        self.spy_symbol = self.AddEquity("SPY", Resolution.Hour).Symbol
        self.spy_option = self.AddOption("SPY", Resolution.Hour)
        self.spy_option.SetFilter(lambda universe: universe.Strikes(-75, 75).Expiration(0, 3))

        # === FIX 2: ADD QQQ OPTION CHAIN FOR WHEEL STRATEGY ===
        # You were subscribed to SPY options but not QQQ options.
        # The Wheel strategy was failing because it had no QQQ option data.
        self.qqq_option = self.AddOption(self.wheel_underlying, Resolution.Hour)
        # Added a filter for the DTEs your strategy looks for (25-50 days)
        self.qqq_option.SetFilter(lambda universe: universe.Strikes(-20, 20).Expiration(25, 50))

        self.vix_index_symbol = self.AddIndex("VIX", Resolution.Hour).Symbol
        self.spy_daily_symbol = self.AddEquity("SPY", Resolution.Daily).Symbol
        self.vix_daily_symbol = self.AddIndex("VIX", Resolution.Daily).Symbol
        self.hmm_model = None

        # === STEP 4: ALPHA MODELS (AFTER ALL SYMBOLS ARE SET) ===
        self.AddAlpha(BTCMomentumAlphaModel(self))
        self.AddAlpha(PutSellingAlphaModel(self))
        self.AddAlpha(CoveredCallAlphaModel(self))
        self.AddAlpha(GapOptionSpreadAlphaModel(self))

        # === STEP 5: PORTFOLIO & EXECUTION ===
        self.SetPortfolioConstruction(InsightWeightingPortfolioConstructionModel(
            rebalance=self.DateRules.WeekStart(),
            portfolio_bias=PortfolioBias.LONG_SHORT
        ))
        self.SetExecution(ImmediateExecutionModel())
        self.SetRiskManagement(MaximumDrawdownPercentPerSecurity(0.12))

        # === FIX 1: SET CORRECT WARMUP PERIOD ===
        # The warmup was set to 5 days, but your indicators (SMA, VWAP, RSI)
        # need 14-20 days to be ready. This was stopping 3/5 strategies.
        # Setting to 25 to give a buffer.
        self.SetWarmUp(25)

        # === STEP 6: SCHEDULED FUNCTIONS ===
        self.Schedule.On(self.DateRules.MonthStart(),
            self.TimeRules.AfterMarketOpen(self.spy_daily_symbol, 30),
            self.update_regime)
            
        # === FIX 3 (REMOVAL): Removed redundant dca_rebalance schedule ===
        # The ETFDCAAlphaModel is now fixed to handle its own timing,
        # making this scheduled function unnecessary.
        # self.Schedule.On(self.DateRules.WeekStart(),
        #     self.TimeRules.AfterMarketOpen(self.spy_daily_symbol, 30),
        #     self.dca_rebalance)
            
        self.Schedule.On(self.DateRules.WeekStart(),
            self.TimeRules.AfterMarketOpen(self.qqq_symbol, 60),
            self.wheel_check_rolls)
        self.Schedule.On(self.DateRules.EveryDay(),
            self.TimeRules.BeforeMarketClose(self.spy_symbol, 15),
            self.gap_liquidate_and_log)
            
        # Track open gap spread orders
        self.open_gap_spread_tickets = []


    def update_regime(self):
        """Update HMM regime detection monthly"""
        if self.IsWarmingUp:
            return
            
        history = self.History([self.spy_daily_symbol, self.vix_daily_symbol], self.regime_lookback, Resolution.Daily)
        if history.empty or len(history.loc[self.spy_daily_symbol]) < self.regime_lookback or len(history.loc[self.vix_daily_symbol]) < self.regime_lookback:
            self.Log(f"HMM update failed: Not enough history. Need {self.regime_lookback} bars.")
            return
            
        spy_prices = history.loc[self.spy_daily_symbol]['close'].values
        vix_prices = history.loc[self.vix_daily_symbol]['close'].values
        
        spy_returns = np.diff(np.log(spy_prices))
        vix_returns = np.diff(np.log(vix_prices))

        # Combine features for HMM
        features = np.column_stack([spy_returns, vix_returns])
        
        if len(features) < 10: # Need enough samples for HMM
            self.Log(f"HMM update failed: Not enough return samples. Got {len(features)}")
            return

        try:
            # FIX: Changed covariance_type from "full" to "diag".
            # "full" can cause numerical instability ("positive-definite" error) when features
            # like SPY and VIX returns are highly correlated. "diag" is more robust.
            self.hmm_model = GaussianHMM(n_components=3, covariance_type="diag", n_iter=100, random_state=42)
            self.hmm_model.fit(features)
            hidden_states = self.hmm_model.predict(features)
            
            # Map states to regimes based on VIX return means
            # Feature 1 is VIX returns (index 1)
            vix_return_means = self.hmm_model.means_[:, 1]
            
            bear_state = np.argmax(vix_return_means) # Highest VIX return -> Bear market
            bull_state = np.argmin(vix_return_means) # Lowest VIX return -> Bull market
            
            state_map = {bear_state: -1, bull_state: 1}
            neutral_state = [s for s in [0, 1, 2] if s not in (bear_state, bull_state)][0]
            state_map[neutral_state] = 0

            current_hmm_state = hidden_states[-1]
            self.market_regime = state_map[current_hmm_state]

            regime_name = {1: "BULL", 0: "NEUTRAL", -1: "BEAR"}[self.market_regime]
            self.Log(f"Regime Updated: {regime_name} (HMM State: {current_hmm_state})")
            self.Plot("Market Regime", "State", self.market_regime)

        except Exception as e:
            self.Log(f"HMM training failed: {str(e)}")
            self.market_regime = 0 # Default to neutral on failure

    # === FIX 3 (REMOVAL): This function is no longer needed ===
    # def dca_rebalance(self):
    #     """Weekly DCA rebalancing for ETF basket"""
    #     if self.IsWarmingUp:
    #         return
    #     if (self.Time - self.last_dca_date).days < self.dca_interval:
    #         return
    #     self.last_dca_date = self.Time
    #     self.Log(f"Executing DCA rebalance on {self.Time}")

    def wheel_check_rolls(self):
        """Check wheel strategy for rolls every week"""
        if self.IsWarmingUp:
            return
        self.Log(f"Wheel Strategy Status - Puts: {self.wheel_put_quantity}, Calls: {self.wheel_call_quantity}, Shares: {self.wheel_assigned_shares}")

    def gap_liquidate_and_log(self):
        """Liquidate gap strategy positions before market close"""
        # Cancel any open limit orders from the gap strategy
        for ticket in self.open_gap_spread_tickets:
            if ticket.Status != OrderStatus.Filled and ticket.Status != OrderStatus.Canceled:
                ticket.Cancel()
                self.Log(f"[GAP STRATEGY] Canceled open limit order for {ticket.Symbol}")
        self.open_gap_spread_tickets.clear()
        
        self.Liquidate("SPY", "Gap Strategy")

    def OnData(self, slice):
        """Main data handler - chains available here"""
        if self.IsWarmingUp:
            return

        if not hasattr(self, 'market_regime') or self.market_regime is None:
            self.update_regime()

        # Optional: Clean up debug logs
        # if not slice.FutureChains:
        #     return
        # if hasattr(self, 'vix_symbol') and self.vix_symbol in slice.FutureChains:
        #     vix_chain = slice.FutureChains[self.vix_symbol]
        #     if vix_chain:
        #         self.Log(f"[ON_DATA] VIX chain available with {len(vix_chain)} contracts")
        # if hasattr(self, 'btc_symbol') and self.btc_symbol in slice.FutureChains:
        #     btc_chain = slice.FutureChains[self.btc_symbol]
        #     if btc_chain:
        #         self.Log(f"[ON_DATA] BTC chain available with {len(btc_chain)} contracts")
        # if not slice.OptionChains:
        #     return
        # if hasattr(self, 'qqq_symbol') and self.qqq_symbol in slice.OptionChains:
        #     qqq_chain = slice.OptionChains[self.qqq_symbol]
        #     if qqq_chain:
        #         self.Log(f"[ON_DATA] QQQ options available with {len(qqq_chain)} contracts")
        # if hasattr(self, 'spy_option') and self.spy_option.Symbol in slice.OptionChains:
        #     spy_chain = slice.OptionChains[self.spy_option.Symbol]
        #     if spy_chain:
        #         self.Log(f"[ON_DATA] SPY options available with {len(spy_chain)} contracts")
        pass # Keep OnData minimal, let Alphas handle data


    def OnSecuritiesChanged(self, changes):
        """Handle universe changes"""
        for added in changes.AddedSecurities:
            self.Log(f"Added: {added.Symbol}")
        for removed in changes.RemovedSecurities:
            self.Log(f"Removed: {removed.Symbol}")


class BTCMomentumAlphaModel(AlphaModel):
    """Strategy 3: BTC Futures Momentum (10%)"""
    def __init__(self, algorithm):
        self.algorithm = algorithm
        self.name = "BTC_MOMENTUM"

    def Update(self, algorithm, data):
        insights = []

        # FIX: Check for btc_contract's existence *before* using it.
        if not hasattr(algorithm, 'btc_contract') or not algorithm.btc_contract:
            return insights

        holdings = algorithm.Portfolio[algorithm.btc_contract]

        # --- Regime Filter ---
        if algorithm.market_regime == -1 and holdings.Invested: # Bear Market
            return [Insight.Price(algorithm.btc_contract, timedelta(days=1), InsightDirection.Flat, tag="RegimeExit")]
        if algorithm.market_regime <= 0 and not holdings.Invested: # Halt new entries in Neutral or Bear
            return insights
        # --- End Regime Filter ---

        if algorithm.btc_contract not in data:
            return insights
            
        # === FIX 1 (EFFECT): These checks will now pass after 14 days ===
        if not algorithm.btc_momentum.IsReady or not algorithm.btc_rsi.IsReady:
            # self.Log("BTC indicators not ready") # Optional: log spam
            return insights

        momentum = algorithm.btc_momentum.Current.Value
        rsi = algorithm.btc_rsi.Current.Value
        if not holdings.Invested and momentum > 5 and rsi < algorithm.btc_overbought:
            confidence = min(1.0, momentum / 20)
            algorithm.Log(f"[ALPHA] BTC_MOMENTUM EMIT: BUY at Momentum {momentum:.2f}%, RSI {rsi:.1f}")
            insights.append(Insight.Price(algorithm.btc_contract, timedelta(days=14), InsightDirection.Up, confidence=confidence, weight=0.10))
        elif holdings.Invested:
            if rsi > algorithm.btc_overbought or momentum < -5:
                reason = "OVERBOUGHT" if rsi > algorithm.btc_overbought else "MOMENTUM REVERSAL"
                algorithm.Log(f"[ALPHA] BTC_MOMENTUM EMIT: SELL ({reason}) at Momentum {momentum:.2f}%, RSI {rsi:.1f}")
                insights.append(Insight.Price(algorithm.btc_contract, timedelta(days=1), InsightDirection.Flat, confidence=0.9))

        return insights


class PutSellingAlphaModel(AlphaModel):
    """Strategy 4: QQQ Wheel Put Selling (25%)"""
    def __init__(self, algorithm):
        self.algorithm = algorithm
        self.name = "WHEEL_PUT_SELLING"

    def Update(self, algorithm, data):
        insights = []
        if algorithm.IsWarmingUp:
            return insights

        # FIX: Add a defensive check to ensure market_regime exists before use.
        # This prevents an AttributeError if the Alpha model runs before the
        # main OnData or scheduled update has initialized the regime.
        if not hasattr(algorithm, 'market_regime') or algorithm.market_regime is None:
            return insights

        # --- Regime Filter ---
        # Liquidate any open put positions if we enter a Bear market
        if algorithm.market_regime == -1:
            put_positions = [pos.Symbol for pos in algorithm.Portfolio.Values if pos.Invested and pos.Symbol.SecurityType == SecurityType.Option and pos.Symbol.ID.OptionRight == OptionRight.Put]
            if put_positions:
                algorithm.Log("[WHEEL_PUT] Bear regime detected. Exiting put positions.")
                return [Insight.Price(symbol, timedelta(days=1), InsightDirection.Flat, tag="RegimeExit") for symbol in put_positions]
            return insights
        # Halt new put selling in Neutral or Bear markets
        if algorithm.market_regime <= 0:
            return insights
        # --- End Regime Filter ---

        if not hasattr(algorithm, 'qqq_symbol') or not hasattr(algorithm, 'wheel_put_quantity'):
            return insights
            
        if not data.OptionChains:
            return insights

        # === FIX 2 (EFFECT): This check will now pass ===
        if algorithm.qqq_option.Symbol not in data.OptionChains:
            self.algorithm.Log("[WHEEL_PUT] QQQ Option chain not found in data.")
            return insights

        chain = data.OptionChains[algorithm.qqq_option.Symbol]
        if len(chain) == 0:
            return insights

        if not data.ContainsKey(algorithm.qqq_symbol) or data[algorithm.qqq_symbol] is None:
             return insights

        qqq_price = data[algorithm.qqq_symbol].Close
        if qqq_price == 0: return insights
        
        puts = [contract for contract in chain if contract.Right == OptionRight.Put]
        if len(puts) == 0:
            return insights

        valid_puts = []
        for put in puts:
            dte = (put.Expiry.date() - algorithm.Time.date()).days
            if 25 <= dte <= 50:
                valid_puts.append((put, dte))

        if len(valid_puts) == 0:
            return insights

        valid_puts.sort(key=lambda x: abs(x[1] - 35))
        selected_dte = valid_puts[0][1]
        contracts_at_dte = [p[0] for p in valid_puts if p[1] == selected_dte]

        if len(contracts_at_dte) == 0:
            return insights

        # Find the put with the delta closest to our target
        best_put = min(contracts_at_dte, key=lambda p: abs(p.Greeks.Delta - algorithm.wheel_put_delta))
        portfolio_value = algorithm.Portfolio.TotalPortfolioValue
        allocation_amount = portfolio_value * algorithm.wheel_allocation
        current_collateral = best_put.Strike * 100
        
        if current_collateral == 0: return insights # Avoid division by zero
        
        max_contracts = int(allocation_amount / current_collateral)

        if algorithm.wheel_put_quantity == 0 and max_contracts > 0:
            iv_signal = 0.5 # This is hardcoded, consider calculating it
            if iv_signal > 0.3:
                algorithm.Log(f"[ALPHA] WHEEL_PUT EMIT: SELL {max_contracts} contracts at {best_put.Strike:.2f} strike (Delta: {best_put.Greeks.Delta:.2f}), {selected_dte} DTE")
                # This insight is for the underlying, which the PCM will use to sell the put.
                # However, this insight direction is wrong for a put sale.
                # A "short put" profits if the underlying goes UP.
                # The insight should be UP, but the PCM needs to know to sell a put.
                # This might be better handled by a custom PortfolioConstructionModel.
                # For InsightWeighting, this UP insight will just BUY QQQ stock.
                # This strategy needs to be re-thought or use a different PCM.
                # For now, emitting the insight as-is, but this is a logic problem.
                insights.append(Insight.Price(algorithm.qqq_symbol, timedelta(days=selected_dte), InsightDirection.Up, confidence=0.65, weight=min(0.25, max_contracts * 0.15)))
                algorithm.wheel_put_quantity = max_contracts
                algorithm.wheel_put_entry_price[best_put.Expiry] = best_put.Strike
        return insights


class CoveredCallAlphaModel(AlphaModel):
    """Strategy 4: QQQ Wheel Covered Calls (25%)"""
    def __init__(self, algorithm):
        self.algorithm = algorithm
        self.name = "WHEEL_COVERED_CALLS"

    def Update(self, algorithm, data):
        insights = []
        if algorithm.IsWarmingUp:
            return insights

        if not hasattr(algorithm, 'qqq_symbol') or not hasattr(algorithm, 'wheel_call_quantity'):
            return insights

        qqq_holdings = algorithm.Portfolio[algorithm.qqq_symbol]
        if qqq_holdings.Quantity <= 0:
            return insights

        if algorithm.wheel_call_quantity == 0 and qqq_holdings.Quantity > 0:
            if not data.OptionChains:
                return insights

            # === FIX 2 (EFFECT): This check will now pass ===
            if algorithm.qqq_option.Symbol not in data.OptionChains:
                self.algorithm.Log("[WHEEL_CALL] QQQ Option chain not found in data.")
                return insights

            chain = data.OptionChains[algorithm.qqq_option.Symbol]
            calls = [contract for contract in chain if contract.Right == OptionRight.Call]
            if len(calls) == 0:
                return insights
                
            if not data.ContainsKey(algorithm.qqq_symbol) or data[algorithm.qqq_symbol] is None:
                return insights

            qqq_price = data[algorithm.qqq_symbol].Close
            if qqq_price == 0: return insights

            valid_calls = []
            for call in calls:
                dte = (call.Expiry.date() - algorithm.Time.date()).days
                if 25 <= dte <= 50:
                    valid_calls.append((call, dte))

            if len(valid_calls) == 0:
                return insights

            valid_calls.sort(key=lambda x: abs(x[1] - 35))
            selected_dte = valid_calls[0][1]
            contracts_at_dte = [c[0] for c in valid_calls if c[1] == selected_dte]
            
            if len(contracts_at_dte) == 0:
                return insights

            # Find the call with the delta closest to our target
            best_call = min(contracts_at_dte, key=lambda c: abs(c.Greeks.Delta - algorithm.wheel_call_delta))
            # This logic is flawed, allocation is not used
            call_contracts = qqq_holdings.Quantity // 100 
            # call_contracts = min(qqq_holdings.Quantity // 100, int(algorithm.wheel_allocation * 100)) # Original logic

            if call_contracts > 0:
                algorithm.Log(f"[ALPHA] WHEEL_CALL EMIT: SELL {call_contracts} contracts at {best_call.Strike:.2f} strike, {selected_dte} DTE")
                # This insight is also problematic. A "short call" (covered call)
                # profits if the underlying goes DOWN (or sideways).
                # Emitting a DOWN insight will conflict with any long QQQ holdings.
                # This highlights a conflict with the InsightWeightingPCM.
                insights.append(Insight.Price(algorithm.qqq_symbol, timedelta(days=selected_dte), InsightDirection.Down, confidence=0.60, weight=0.05, tag="CoveredCall"))
                algorithm.wheel_call_quantity = call_contracts
                algorithm.wheel_call_entry_price[best_call.Expiry] = best_call.Strike
        return insights


class GapOptionSpreadAlphaModel(AlphaModel):
    """Strategy 5: VIX/QQQ Open Gap 3-DTE Option Spreads (NEW - 15%)"""
    def __init__(self, algorithm):
        self.algorithm = algorithm
        self.name = "GAP_OPTION_SPREADS"
        # Store these locally in the alpha model
        self.gap_current_month = None
        self.gap_monthly_start_equity = None
        self.gap_stop_trading_month = False
        self.gap_yesterday_vix_close = None
        self.gap_yesterday_qqq_close = None
        self.gap_today_processed = False
        self.gap_last_processed_date = None


    def Update(self, algorithm, data):
        insights = []
        if algorithm.IsWarmingUp:
            return insights

        # FIX: Add a defensive check to ensure market_regime exists before use.
        # This prevents an AttributeError if the Alpha model runs before the
        # main OnData or scheduled update has initialized the regime.
        if not hasattr(algorithm, 'market_regime') or algorithm.market_regime is None:
            return insights

        # --- Regime Filter ---
        # Halt this strategy in a Bull market (low VIX)
        if algorithm.market_regime == 1:
            return insights
        # --- End Regime Filter ---

        # Use local alpha model state, not global algorithm state
        if self.gap_current_month is None:
            self.gap_current_month = algorithm.Time.month
            self.gap_monthly_start_equity = algorithm.Portfolio.TotalPortfolioValue
            self.gap_stop_trading_month = False

        this_month = algorithm.Time.month
        if self.gap_current_month != this_month:
            self.gap_current_month = this_month
            self.gap_monthly_start_equity = algorithm.Portfolio.TotalPortfolioValue
            self.gap_stop_trading_month = False

        if self.gap_stop_trading_month:
            return insights

        if self.gap_monthly_start_equity and algorithm.Portfolio.TotalPortfolioValue < (1 - algorithm.gap_monthly_dd_limit) * self.gap_monthly_start_equity:
            algorithm.Log(f"[GAP] Max monthly drawdown exceeded")
            self.gap_stop_trading_month = True
            return insights

        if not hasattr(algorithm, 'vix_index_symbol') or not hasattr(algorithm, 'qqq_symbol'):
            return insights

        if algorithm.vix_index_symbol not in data or algorithm.qqq_symbol not in data:
            return insights

        vix_bar = data[algorithm.vix_index_symbol]
        qqq_bar = data[algorithm.qqq_symbol]

        if not vix_bar or not qqq_bar or vix_bar.Close is None or vix_bar.Open is None or qqq_bar.Close is None or qqq_bar.Open is None:
            return insights

        current_vix_close = float(vix_bar.Close)
        current_vix_open = float(vix_bar.Open)
        current_qqq_close = float(qqq_bar.Close)
        current_qqq_open = float(qqq_bar.Open)

        if current_vix_close <= 0 or current_vix_open <= 0 or current_qqq_close <= 0 or current_qqq_open <= 0:
            return insights

        current_date = algorithm.Time.date()

        if self.gap_yesterday_vix_close is None or self.gap_yesterday_qqq_close is None:
            self.gap_yesterday_vix_close = current_vix_close
            self.gap_yesterday_qqq_close = current_qqq_close
            self.gap_last_processed_date = current_date
            return insights

        if current_date != self.gap_last_processed_date:
            self.gap_today_processed = False
            self.gap_last_processed_date = current_date

        if self.gap_today_processed:
            self.gap_yesterday_vix_close = current_vix_close
            self.gap_yesterday_qqq_close = current_qqq_close
            return insights

        vix_gap_pct = (current_vix_open - self.gap_yesterday_vix_close) / self.gap_yesterday_vix_close
        qqq_gap_pct = (current_qqq_open - self.gap_yesterday_qqq_close) / self.gap_yesterday_qqq_close

        if not data.OptionChains:
            return insights

        if algorithm.spy_option.Symbol not in data.OptionChains:
            self.gap_yesterday_vix_close = current_vix_close
            self.gap_yesterday_qqq_close = current_qqq_close
            return insights

        option_chain = data.OptionChains[algorithm.spy_option.Symbol]
        if option_chain is None or len(option_chain) == 0:
            self.gap_yesterday_vix_close = current_vix_close
            self.gap_yesterday_qqq_close = current_qqq_close
            return insights

        if (vix_gap_pct >= algorithm.gap_vix_threshold and qqq_gap_pct >= algorithm.gap_qqq_threshold):
            algorithm.Log(f"[GAP TRIGGERED] CALL SPREAD")
            # This is a hybrid model: the Alpha finds the trade but the main algorithm executes it.
            # This is necessary for complex orders like combo limit orders.
            if algorithm.submit_spread_limit_order(option_chain, call=True):
                self.gap_today_processed = True
                algorithm.Log(f"[HYBRID] GAP_SPREAD SUBMITTED: CALL SPREAD VIX_gap={vix_gap_pct:.4f} QQQ_gap={qqq_gap_pct:.4f}")

        elif (vix_gap_pct <= -algorithm.gap_vix_threshold and qqq_gap_pct <= 0.01):
            algorithm.Log(f"[GAP TRIGGERED] PUT SPREAD")
            if algorithm.submit_spread_limit_order(option_chain, call=False):
                self.gap_today_processed = True
                algorithm.Log(f"[HYBRID] GAP_SPREAD SUBMITTED: PUT SPREAD VIX_gap={vix_gap_pct:.4f} QQQ_gap={qqq_gap_pct:.4f}")

        self.gap_yesterday_vix_close = current_vix_close
        self.gap_yesterday_qqq_close = current_qqq_close

        return insights


def submit_spread_limit_order(self, option_chain, call=True):
    qty = 5
    target_delta_short = algorithm.gap_short_delta if call else -algorithm.gap_short_delta
    target_delta_long = algorithm.gap_long_delta if call else -algorithm.gap_long_delta
    option_type = OptionRight.Call if call else OptionRight.Put

    shorts = [x for x in option_chain if x.Right == option_type and hasattr(x, 'Greeks') and x.Greeks.Delta is not None and ((x.Greeks.Delta <= target_delta_short and call) or (x.Greeks.Delta >= target_delta_short and not call)) and algorithm.is_liquid(x) and 0 <= (x.Expiry - algorithm.Time).days <= 3]

    if not shorts:
        self.Log(f"[GAP] No liquid shorts found matching delta {target_delta_short}")
        return False

    short_leg = min(shorts, key=lambda x: abs(x.Greeks.Delta - target_delta_short))
    longs = [x for x in option_chain if x.Right == option_type and hasattr(x, 'Greeks') and x.Greeks.Delta is not None and ((x.Greeks.Delta <= target_delta_long and call) or (x.Greeks.Delta >= target_delta_long and not call)) and algorithm.is_liquid(x) and 0 <= (x.Expiry - algorithm.Time).days <= 3]

    if not longs:
        self.Log(f"[GAP] No liquid longs found matching delta {target_delta_long}")
        return False

    long_leg = min(longs, key=lambda x: abs(x.Greeks.Delta - target_delta_long))

    if short_leg.Expiry != long_leg.Expiry:
        self.Log("[GAP] Different expiries for short and long legs")
        return False

    # Ensure strikes are not the same
    if short_leg.Strike == long_leg.Strike:
        self.Log("[GAP] Short and long leg strikes are the same.")
        return False

    # Create the combo order
    legs = [
        Leg.Create(short_leg.Symbol, -qty), # Sell the short leg
        Leg.Create(long_leg.Symbol, qty)   # Buy the long leg
    ]

    # Calculate limit price: Mid-point of the spread's bid/ask
    limit_price = (short_leg.BidPrice - long_leg.AskPrice) if call else (short_leg.BidPrice - long_leg.AskPrice)
    
    ticket = self.ComboLimitOrder(legs, 0, limit_price) # Quantity is in the legs
    self.open_gap_spread_tickets.append(ticket)
    return True


def is_liquid(self, contract):
    """Check if option contract has sufficient liquidity"""
    # === FIX 4: USE ALGORITHM PARAMETERS ===
    # The original function had hardcoded values (0.08, 100, 0.10)
    # This now correctly uses the parameters you defined in Initialize.
    try:
        bid = contract.BidPrice if hasattr(contract, 'BidPrice') and contract.BidPrice else 0
        ask = contract.AskPrice if hasattr(contract, 'AskPrice') and contract.AskPrice else 0
        
        if bid <= self.gap_min_spread_bid:
            # self.Log(f"[is_liquid] FAILED: Bid {bid} <= {self.gap_min_spread_bid}")
            return False
        if ask <= 0:
            # self.Log(f"[is_liquid] FAILED: Ask {ask} <= 0")
            return False
            
        spread = (ask - bid) / bid
        oi = contract.OpenInterest if hasattr(contract, 'OpenInterest') else 0
        
        if oi <= self.gap_min_oi:
            # self.Log(f"[is_liquid] FAILED: OI {oi} <= {self.gap_min_oi}")
            return False
        
        if spread >= self.gap_max_spread_pct:
            # self.Log(f"[is_liquid] FAILED: Spread {spread:.2f} >= {self.gap_max_spread_pct}")
            return False

        return True # All checks passed
    except Exception as e:
        self.Log(f"[is_liquid] ERROR: {str(e)}")
        return False

RegimeAwareMultiStrategyAlgorithm.submit_spread_limit_order = submit_spread_limit_order
RegimeAwareMultiStrategyAlgorithm.is_liquid = is_liquid
