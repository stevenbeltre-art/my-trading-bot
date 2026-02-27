import time
import threading
from dotenv import load_dotenv
import os
import datetime
import pytz

from bot.exchange import ExchangeInterface
from bot.strategy import StrategyEngine
from bot.risk_manager import RiskManager
from database.db_manager import DBManager

class TradingEngine:
    def __init__(self):
        load_dotenv()
        
        # Keys
        self.exchange_api_key = os.getenv("ALPACA_API_KEY")
        self.exchange_secret = os.getenv("ALPACA_SECRET_KEY")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")

        # Initialize Components
        self.db = DBManager()
        self.db.log_message("INFO", "Initializing Trading Engine...")

        try:
            self.exchange = ExchangeInterface(self.exchange_api_key, self.exchange_secret)
            self.strategy = StrategyEngine(self.gemini_api_key, self.exchange_api_key, self.exchange_secret)
            self.risk_manager = RiskManager(atr_sl_multiplier=4.0) # Wider Stop Loss Parameter
        except Exception as e:
            self.db.log_message("ERROR", f"Failed to initialize components: {e}")
            raise

        # High-Volume Universe (Market Hours)
        self.market_hours_symbols = [
            "BTC/USD", "ETH/USD", "SOL/USD", # Core Crypto
            "SPY", "QQQ", "AAPL", "TSLA", "MSFT", "NVDA" # Equities
        ]
        
        # After-Hours Universe (Crypto Only)
        self.after_hours_symbols = [
            "BTC/USD", "ETH/USD", "SOL/USD", 
            "DOGE/USD", "AVAX/USD", "LINK/USD", "MATIC/USD"
        ]
        
        # Default start state
        self.symbols = self.market_hours_symbols
        
        self.db.log_message("INFO", f"High-Volume Universe Loaded: {len(self.symbols)} markets.")

        # State
        self.is_running = False
        self.thread = None
        # Track positions per symbol
        self.open_positions = {sym: None for sym in self.symbols} 

    def start(self):
        """Starts the main trading loop in a background thread for UI responsiveness."""
        if not self.is_running:
            self.is_running = True
            self.db.log_message("INFO", "Trading Bot started.")
            # Remove daemon=True. Streamlit will aggressively kill daemon threads immediately on script reload.
            self.thread = threading.Thread(target=self._run_loop)
            self.thread.start()

    def stop(self):
        """Stops the main trading loop."""
        if self.is_running:
            self.is_running = False
            self.db.log_message("INFO", "Kill Switch Activated. Stopping bot...")
            if self.thread:
                self.thread.join(timeout=5)

    def _fetch_ohlcv_with_backoff(self, symbol: str, timeframe: str, limit: int, max_retries: int = 5):
        """Fetches OHLCV data with exponential backoff to handle Alpaca 429 Rate Limits."""
        for attempt in range(max_retries):
            try:
                return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            except Exception as e:
                if "429" in str(e) or "Too Many Requests" in str(e):
                    sleep_time = 2 ** attempt
                    self.db.log_message("WARNING", f"Rate limit hit fetching {symbol}. Sleeping {sleep_time}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(sleep_time)
                else:
                    raise e
        self.db.log_message("ERROR", f"Failed to fetch OHLCV for {symbol} after {max_retries} attempts.")
        return []

    def _get_market_status(self):
        """Checks if the US Equity Market is currently open (9:30 AM to 4:00 PM EST, Mon-Fri)."""
        
        eastern = pytz.timezone('US/Eastern')
        now = datetime.datetime.now(eastern)
        
        # Check if it's a weekday (0=Monday, 6=Sunday)
        if now.weekday() >= 5:
            return False
            
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        
        return market_open <= now <= market_close

    def _run_loop(self):
        """The core continuous trading loop, handling rate limits and sleeping."""
        print("[ENGINE DEBUG] _run_loop thread successfully started!", flush=True)
        self.db.log_message("INFO", "Engine loop successfully entered.")
        
        last_market_state = None
        
        while self.is_running:
            try:
                # 0. Dynamic Asset Surveillance Routing
                market_is_open = self._get_market_status()
                
                # Check for Market State Transition (Open -> Close or Close -> Open)
                if last_market_state is None or market_is_open != last_market_state:
                    if market_is_open:
                        self.db.log_message("INFO", "Market Hours Detected (9:30 AM EST). Activating Full Equity Pipeline.")
                        self.symbols = self.market_hours_symbols
                    else:
                        self.db.log_message("INFO", "After-Hours Detected (4:00 PM EST). Routing all surveillance to Global Crypto Markets.")
                        self.symbols = self.after_hours_symbols
                        
                    # Rebuild the open positions tracking map to ensure no key errors
                    for sym in self.symbols:
                        if sym not in self.open_positions:
                            self.open_positions[sym] = None
                            
                    last_market_state = market_is_open
            
                # Pre-fetch balance once per main loop iteration
                self.db.log_message("DEBUG", "Fetching balance...")
                balance_info = self.exchange.fetch_balance()
                
                # Fetch active positions to correctly determine true holding status for Long/Short 
                active_positions_raw = self.exchange.fetch_positions()
                active_symbols = [p.symbol for p in active_positions_raw]
                
                self.db.log_message("DEBUG", "Balance and Positions fetched.")
                
                for symbol in self.symbols:
                    if not self.is_running:
                         break # Exit inner loop if killed
                    
                    is_crypto = self.exchange._is_crypto(symbol)
                    
                    # 1. Market Hours Guard
                    # (Though the universe swapped, we still hard-block stray non-crypto during closed hours as a safety net)
                    if not is_crypto and not market_is_open:
                        # self.db.log_message("DEBUG", f"{symbol}: Skipped. US Equity Market is Closed.")
                        continue
                        
                    try:
                        self.db.log_message("DEBUG", f"Evaluating {symbol}")
                        # 1. Fetch current price and dual-timeframe data
                        self.db.log_message("DEBUG", f"{symbol}: Fetching OHLCV...")
                        ohlcv_15m = self._fetch_ohlcv_with_backoff(symbol, timeframe='15m', limit=100)
                        ohlcv_4h = self._fetch_ohlcv_with_backoff(symbol, timeframe='4h', limit=100)
                        self.db.log_message("DEBUG", f"{symbol}: OHLCV fetched. Fetching Ticker...")
                        try:
                            ticker = self.exchange.fetch_ticker(symbol)
                            current_price = ticker['last']
                            self.db.log_message("DEBUG", f"{symbol}: Price {current_price}")
                            
                            # Update metrics for the UI to consume safely
                            if not hasattr(self.strategy, 'metrics'):
                                self.strategy.metrics = {}
                            if symbol not in self.strategy.metrics:
                                self.strategy.metrics[symbol] = {}
                            self.strategy.metrics[symbol]['last_price'] = current_price
                        except Exception as e:
                            self.db.log_message("WARNING", f"Could not fetch ticker for {symbol}: {e}")
                            continue # Skip to next coin
        
                        # 2. Check Open Position Status Natively
                        alpaca_symbol = symbol.replace('/', '')
                        is_held = alpaca_symbol in active_symbols
                        
                        if self.open_positions.get(symbol):
                            # If we marked it open locally, check if Alpaca natively closed it (hit Trailing Stop)
                            if not is_held:
                                self.db.log_message("INFO", f"{symbol} Position closed natively by Alpaca Bracket Order.")
                                self.db.update_trade_pnl(self.open_positions[symbol]['id'], 0, "CLOSED_NATIVELY")
                                self.open_positions[symbol] = None
                            else:
                                # Monitor for $5,000 Hard Take Profit
                                try:
                                    position_data = next((p for p in active_positions if p.symbol == alpaca_symbol), None)
                                    if position_data:
                                        unrealized_pl = float(position_data.unrealized_pl)
                                        # Update UI matrix with live PnL
                                        self.strategy.metrics[symbol]['live_pnl'] = unrealized_pl
                                        
                                        # Track Highest PnL for The Squeeze
                                        if 'highest_pnl' not in self.open_positions[symbol]:
                                            self.open_positions[symbol]['highest_pnl'] = unrealized_pl
                                        else:
                                            self.open_positions[symbol]['highest_pnl'] = max(self.open_positions[symbol]['highest_pnl'], unrealized_pl)
                                            
                                        highest_pnl = self.open_positions[symbol]['highest_pnl']
                                        
                                        if unrealized_pl >= 5000.0:
                                            self.db.log_message("SUCCESS", f"{symbol} hit $5,000 Profit Target! Liquidating position natively.")
                                            qty_to_close = float(position_data.qty)
                                            side_to_close = "sell" if position_data.side == "long" else "buy"
                                            # Close the position natively
                                            # Market Order is fastest guaranteed execution
                                            try:
                                                self.exchange.create_market_order(symbol, qty_to_close, side_to_close)
                                                self.db.update_trade_pnl(self.open_positions[symbol]['id'], unrealized_pl, "PROFIT_TAKEN")
                                                self.open_positions[symbol] = None
                                            except Exception as e:
                                                self.db.log_message("ERROR", f"Failed to liquidate {symbol} crossing $5k: {e}")
                                                
                                        elif highest_pnl >= 3000.0 and unrealized_pl <= highest_pnl - 500.0:
                                            self.db.log_message("SUCCESS", f"{symbol} hit The Squeeze at ${highest_pnl:.2f} peak! Liquidating instantly to protect $3k floor.")
                                            qty_to_close = float(position_data.qty)
                                            side_to_close = "sell" if position_data.side == "long" else "buy"
                                            # Close natively
                                            try:
                                                self.exchange.create_market_order(symbol, qty_to_close, side_to_close)
                                                self.db.update_trade_pnl(self.open_positions[symbol]['id'], unrealized_pl, "PROFIT_TAKEN_SQUEEZE")
                                                self.open_positions[symbol] = None
                                            except Exception as e:
                                                self.db.log_message("ERROR", f"Failed to liquidate Squeeze {symbol}: {e}")
                                                
                                except Exception as e:
                                    self.db.log_message("WARNING", f"Error monitoring PnL for {symbol}: {e}")
                                
                        # 3. Look for new Entry
                        elif not is_held: 
                            action = self.strategy.determine_trade_action(ohlcv_15m, ohlcv_4h, symbol)
                            
                            if action in ["BUY", "SELL"]:
                                # Available fiat cash to trade with (Alpaca handles everything in USD natively)
                                available_balance = balance_info.get('USD', {}).get('free', 10000.0)
                                
                                # Prevent making dust/micro trades if account is already fully deployed
                                if available_balance < 10.0:
                                    # Silently update the UI matrix instead of spamming warning logs
                                    self.strategy.metrics[symbol]['rejection_reason'] = "Blocked: Insufficient Cash"
                                    continue
                                    
                                self.db.log_message("INFO", f"{symbol} Strategy signal: {action}.")
                                
                                params = self.risk_manager.calculate_trade_parameters(available_balance, current_price, ohlcv_15m, direction=action)
                                amount = params['amount']
                                trail_price = params['trail_price']
                                hard_tp_price = params.get('hard_tp_price', current_price * 1.5) # Fallback if missing
                                
                                if amount > 0:
                                    try:
                                        self.db.log_message("INFO", f"Executing {action} for {amount} {symbol} at {current_price} | Trail: {trail_price} | Max TP: {hard_tp_price}")
                                        if action == "BUY":
                                            order = self.exchange.create_trailing_buy_order(symbol, amount, trail_price, hard_tp_price)
                                        else:
                                            order = self.exchange.create_trailing_sell_order(symbol, amount, trail_price, hard_tp_price)
                                        cost = order.get('cost')
                                        if cost is None:
                                            cost = current_price * amount
                                    except Exception as e:
                                        self.db.log_message("WARNING", f"{symbol} {action} failed, assuming simulated fill: {e}")
                                        cost = current_price * amount
                                        amount = cost / current_price
                                        
                                    trade_id = self.db.log_trade(symbol, action, current_price, amount, cost, "OPEN")
                                    
                                    self.open_positions[symbol] = {
                                        "id": trade_id,
                                        "entry_price": current_price,
                                        "amount": amount
                                    }
                                
                    except Exception as e:
                        self.db.log_message("ERROR", f"Error evaluating {symbol}: {e}")
                        
                    # Rate Limits between coins
                    time.sleep(2)

            except Exception as e:
                self.db.log_message("ERROR", f"Error in main trading logic: {e}")
            
            # Rate Limiting: Sleep between full loops over all coins
            for _ in range(30):
                if not self.is_running:
                    break
                time.sleep(1)
