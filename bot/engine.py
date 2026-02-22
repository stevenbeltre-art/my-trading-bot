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
        raw_symbols = os.getenv("TRADING_SYMBOL", "ALL")
        self.exchange_id = os.getenv("EXCHANGE_ID", "alpaca")

        # Initialize Components
        self.db = DBManager()
        self.db.log_message("INFO", "Initializing Trading Engine...")

        try:
            self.exchange = ExchangeInterface(self.exchange_id, self.exchange_api_key, self.exchange_secret)
            self.strategy = StrategyEngine(self.gemini_api_key)
            self.risk_manager = RiskManager()
        except Exception as e:
            self.db.log_message("ERROR", f"Failed to initialize components: {e}")
            raise

        if raw_symbols.strip().upper() == "ALL":
            try:
                self.db.log_message("INFO", "Fetching top crypto markets...")
                # Alpaca requires explicit symbols for fetch_tickers, so we define the core active group
                core_symbols = ["BTC/USD", "ETH/USD", "SOL/USD", "LTC/USD", "BCH/USD", "LINK/USD", "DOGE/USD", "AVAX/USD", "DOT/USD", "UNI/USD"]
                tickers = self.exchange.exchange.fetch_tickers(core_symbols)
                
                # filter usd spot pairs for Alpaca
                usd_tickers = {k: v for k, v in tickers.items() if k.endswith('/USD') and ':' not in k and isinstance(v.get('quoteVolume', 0), (int, float))}
                sorted_tickers = sorted(usd_tickers.values(), key=lambda x: x.get('quoteVolume', 0), reverse=True)
                self.symbols = [t['symbol'] for t in sorted_tickers[:20]]
                if not self.symbols:
                    self.symbols = core_symbols[:5] # fallback
                self.db.log_message("INFO", f"Loaded {len(self.symbols)} markets dynamically.")
            except Exception as e:
                self.db.log_message("ERROR", f"Failed to fetch all markets, defaulting: {e}")
                self.symbols = ["BTC/USD", "ETH/USD", "SOL/USD", "LTC/USD", "BCH/USD"]
        else:
            self.symbols = [s.strip() for s in raw_symbols.split(',')]

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
                
                for symbol in self.symbols:
                    if not self.is_running:
                        break # Exit inner loop if killed
                        
                    try:
                        self.db.log_message("DEBUG", f"Evaluating {symbol}")
                        # 1. Fetch current price and data
                        self.db.log_message("DEBUG", f"{symbol}: Fetching OHLCV...")
                        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)
                        self.db.log_message("DEBUG", f"{symbol}: OHLCV fetched. Fetching Ticker...")
                        try:
                            ticker = self.exchange.fetch_ticker(symbol)
                            current_price = ticker['last']
                            self.db.log_message("DEBUG", f"{symbol}: Price {current_price}")
                        except Exception as e:
                            self.db.log_message("WARNING", f"Could not fetch ticker for {symbol}: {e}")
                            continue # Skip to next coin
        
                        # 2. Check Open Position
                        if self.open_positions[symbol]:
                            pos = self.open_positions[symbol]
                            entry_price = pos['entry_price']
                            amount = pos['amount']
                            highest_price = max(pos['highest_price'], current_price)
                            pos['highest_price'] = highest_price
        
                            trailing_stop = self.risk_manager.calculate_trailing_stop(entry_price, highest_price)
                            
                            sell_reason = None
                            if self.risk_manager.check_take_profit(entry_price, current_price):
                                sell_reason = "Take Profit Hit"
                            elif self.risk_manager.check_stop_loss(current_price, trailing_stop):
                                sell_reason = "Trailing Stop Loss Hit"

                            if sell_reason:
                                self.db.log_message("INFO", f"{symbol} - {sell_reason} at {current_price}. Executing SELL.")
                                try:
                                    order = self.exchange.create_market_sell_order(symbol, amount)
                                    cost = order.get('cost')
                                    if cost is None:
                                        cost = current_price * amount
                                except Exception as e:
                                    self.db.log_message("WARNING", f"{symbol} Sell failed, sim: {e}")
                                    cost = current_price * amount
                                    
                                pnl = cost - (entry_price * amount)
                                self.db.update_trade_pnl(pos['id'], pnl, "CLOSED")
                                # Explicitly record the SELL side of the transaction for the UI history
                                self.db.log_trade(symbol, "SELL", current_price, amount, cost, "CLOSED")
                                self.open_positions[symbol] = None
        
                        # 3. Look for new Entry
                        else:
                            action = self.strategy.determine_trade_action(ohlcv, symbol)
                            
                            if action == "BUY":
                                self.db.log_message("INFO", f"{symbol} Strategy signal: BUY.")
                                quote_currency = symbol.split('/')[1]
                                available_balance = balance_info.get(quote_currency, {}).get('free', 10000.0)
                                
                                amount_to_buy = self.risk_manager.calculate_position_size(available_balance, current_price)
                                
                                try:
                                    self.db.log_message("INFO", f"Executing BUY for {amount_to_buy} {symbol} at {current_price}")
                                    order = self.exchange.create_market_buy_order(symbol, amount_to_buy)
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
                                    "highest_price": current_price,
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
