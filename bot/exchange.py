import ccxt
import time
import threading
from typing import Dict, Any, Optional
import os

class ExchangeInterface:
    def __init__(self, exchange_id: str, api_key: str, secret: str):
        self.exchange_id = exchange_id
        self.lock = threading.Lock()
        
        # Initialize the CCXT exchange class instance based on the string id
        exchange_class = getattr(ccxt, self.exchange_id)
        
        self.exchange = exchange_class({
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': False, # Disabled due to Alpaca/CCXT hanging bug. Engine uses time.sleep().
        })
        
        # EXPLICIT SANDBOX MODE: Guarantee it connects to the testnet/paper trading environment
        self.exchange.set_sandbox_mode(True)
        
    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker information."""
        with self.lock:
            return self.exchange.fetch_ticker(symbol)

    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 100) -> list:
        """Fetch OHLCV candlestick data."""
        with self.lock:
            return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    def fetch_balance(self) -> Dict[str, Any]:
        """Fetch account balance. Mocks it if using generic keys."""
        with self.lock:
            try:
                return self.exchange.fetch_balance()
            except Exception as e:
                # If the user hasn't set real API keys, provide a mock paper trading balance
                print(f"Auth error (using mock balance): {e}")
                return {'USD': {'free': 10000.0}}

    def create_market_buy_order(self, symbol: str, amount: float) -> Dict[str, Any]:
        """Execute a market buy order."""
        with self.lock:
            return self.exchange.create_market_buy_order(symbol, amount)

    def create_market_sell_order(self, symbol: str, amount: float) -> Dict[str, Any]:
        """Execute a market sell order."""
        with self.lock:
            return self.exchange.create_market_sell_order(symbol, amount)

