import time
import threading
from dotenv import load_dotenv
import os

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

        # High-Volume Universe
        self.symbols = [
            "BTC/USD", "ETH/USD", "SOL/USD", # Crypto
            "SPY", "QQQ", "AAPL", "TSLA", "MSFT", "NVDA" # Equities
        ]
        
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

    def _get_market_status(self) -> bool:
        """Determines if the US Equity Market is currently open."""
        try:
            clock = self.exchange.trading_client.get_clock()
            return clock.is_open
        except Exception:
            return False # Fail safe

    def _run_loop(self):
        """The core continuous trading loop, handling rate limits and sleeping."""
        print("[ENGINE DEBUG] _run_loop thread successfully started!", flush=True)
        self.db.log_message("INFO", "Engine loop successfully entered.")
        while self.is_running:
            try:
                # Pre-fetch balance once per main loop iteration
                self.db.log_message("DEBUG", "Fetching balance...")
                balance_info = self.exchange.fetch_balance()
                self.db.log_message("DEBUG", "Balance fetched.")
                
                market_is_open = self._get_market_status()
                
                for symbol in self.symbols:
                    if not self.is_running:
                         break # Exit inner loop if killed
                    
                    is_crypto = self.exchange._is_crypto(symbol)
                    
                    # 0. Market Hours Guard
                    if not is_crypto and not market_is_open:
                        self.db.log_message("DEBUG", f"{symbol}: Skipped. US Equity Market is Closed.")
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
                        base_currency = symbol.split('/')[0] if is_crypto else symbol
                        coin_balance = balance_info.get(base_currency, {}).get('total', 0.0)
                        
                        if self.open_positions[symbol]:
                            # If we marked it open, check if Alpaca natively closed it (hit SL/TP)
                            if coin_balance <= 0.00001:
                                self.db.log_message("INFO", f"{symbol} Position closed natively by Alpaca Bracket Order.")
                                # Assuming native close, update database. (Real PnL sync requires order query, marking 0 for simplicity here)
                                self.db.update_trade_pnl(self.open_positions[symbol]['id'], 0, "CLOSED_NATIVELY")
                                self.open_positions[symbol] = None
                            else:
                                pass # Still open, let Alpaca's robust OCO engine handle it on their servers.
                                
                        # 3. Look for new Entry
                        elif coin_balance <= 0.00001: 
                            action = self.strategy.determine_trade_action(ohlcv_15m, ohlcv_4h, symbol)
                            
                            if action == "BUY":
                                self.db.log_message("INFO", f"{symbol} Strategy signal: BUY.")
                                quote_currency = symbol.split('/')[1]
                                available_balance = balance_info.get(quote_currency, {}).get('free', 10000.0)
                                
                                params = self.risk_manager.calculate_trade_parameters(available_balance, current_price, ohlcv_15m)
                                amount_to_buy = params['amount']
                                sl_price = params['sl_price']
                                tp_price = params['tp_price']
                                
                                if amount_to_buy > 0:
                                    try:
                                        self.db.log_message("INFO", f"Executing BRACKET BUY for {amount_to_buy} {symbol} at {current_price} | SL: {sl_price} | TP: {tp_price}")
                                        order = self.exchange.create_bracket_buy_order(symbol, amount_to_buy, sl_price, tp_price)
                                        cost = order.get('cost')
                                        if cost is None:
                                            cost = current_price * amount_to_buy
                                    except Exception as e:
                                        self.db.log_message("WARNING", f"{symbol} Buy failed, sim: {e}")
                                        cost = current_price * amount_to_buy
                                        amount_to_buy = cost / current_price
                                        
                                    trade_id = self.db.log_trade(symbol, "BUY", current_price, amount_to_buy, cost, "OPEN")
                                    
                                    self.open_positions[symbol] = {
                                        "id": trade_id,
                                        "entry_price": current_price,
                                        "amount": amount_to_buy
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
