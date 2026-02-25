from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest, TrailingStopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest, StockTradesRequest, CryptoTradesRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

import time
import threading
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

class ExchangeInterface:
    def __init__(self, api_key: str, secret: str):
        self.lock = threading.Lock()
        
        # 1. Trading Client (Executes orders and fetches account balances)
        self.trading_client = TradingClient(api_key, secret, paper=True)
        
        # 2. Historical Data Clients (Fetches OHLCV and Tickers)
        self.stock_data_client = StockHistoricalDataClient(api_key, secret)
        self.crypto_data_client = CryptoHistoricalDataClient(api_key, secret)
        
    def _is_crypto(self, symbol: str) -> bool:
        """Helper to determine data client routing."""
        return "/" in symbol or "USD" in symbol

    def _get_timeframe_obj(self, timeframe_str: str) -> TimeFrame:
        if timeframe_str == '15m':
            return TimeFrame(15, TimeFrameUnit.Minute)
        elif timeframe_str == '4h':
            return TimeFrame(4, TimeFrameUnit.Hour)
        return TimeFrame(1, TimeFrameUnit.Hour)

    def fetch_ticker(self, symbol: str) -> Dict[str, float]:
        """Fetch latest trade price."""
        with self.lock:
            if self._is_crypto(symbol):
                # Using latest trades for crypto
                req = CryptoTradesRequest(symbol_or_symbols=symbol)
                latest = self.crypto_data_client.get_crypto_latest_trade(req)
                return {'last': latest[symbol].price}
            else:
                # Using latest trades for stock
                req = StockTradesRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
                latest = self.stock_data_client.get_stock_latest_trade(req)
                return {'last': latest[symbol].price}

    def fetch_ohlcv(self, symbol: str, timeframe: str = '15m', limit: int = 100) -> list:
        """Fetch OHLCV returning a standardized CCXT-like array for backward-compatibility."""
        with self.lock:
            end_dt = datetime.utcnow()
            
            # Calculate a generic start time that covers the limit requirements
            hours_offset = 24 * limit if timeframe == '4h' else (limit // 4) * 24 
            start_dt = end_dt - timedelta(hours=hours_offset)
            
            tf_obj = self._get_timeframe_obj(timeframe)
            
            if self._is_crypto(symbol):
                request_params = CryptoBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=tf_obj,
                    start=start_dt,
                    end=end_dt
                )
                bars = self.crypto_data_client.get_crypto_bars(request_params).df
            else:
                request_params = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=tf_obj,
                    start=start_dt,
                    end=end_dt,
                    feed=DataFeed.IEX
                )
                bars = self.stock_data_client.get_stock_bars(request_params).df

            # Ensure data isn't empty
            if bars.empty:
                return []

            # Clean the dataframe back to the CCXT array format [timestamp, O, H, L, C, V]
            # Alpaca multi-index dataframe needs resetting
            bars = bars.reset_index()
            # Standardize column naming just in case
            bars = bars[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            
            # Convert timestamp back to standard python epoch milliseconds
            bars['timestamp'] = bars['timestamp'].astype('int64') // 10**6 
            
            # Return as array of arrays (CCXT format style, slicing to specific limit)
            ohlcv_list = bars.values.tolist()
            return ohlcv_list[-limit:]

    def fetch_balance(self) -> Dict[str, Any]:
        """Fetch account balance natively from Alpaca."""
        with self.lock:
            try:
                account = self.trading_client.get_account()
                # Return standard dict format to avoid breaking engine.py logic
                return {'USD': {'free': float(account.cash), 'total': float(account.equity)}}
            except Exception as e:
                print(f"Auth error (using mock balance): {e}")
                return {'USD': {'free': 10000.0, 'total': 10000.0}}

    def fetch_positions(self) -> list:
        """Fetch active positions natively."""
        with self.lock:
            try:
                return self.trading_client.get_all_positions()
            except Exception:
                return []

    def create_market_order(self, symbol: str, amount: float, side: str) -> Dict[str, Any]:
        """Execute a raw market order (used for emergency liquidations and hard Take-Profits)."""
        with self.lock:
            try:
                alpaca_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
                market_order_data = MarketOrderRequest(
                    symbol=symbol,
                    qty=amount,
                    side=alpaca_side,
                    time_in_force=TimeInForce.GTC
                )
                order = self.trading_client.submit_order(order_data=market_order_data)
                return {
                    'id': str(order.id),
                    'cost': float(order.notional) if order.notional else (float(order.qty) * float(order.filled_avg_price) if order.filled_avg_price else None)
                }
            except Exception as e:
                raise Exception(f"Alpaca Market Order Failed: {e}")

    def create_trailing_buy_order(self, symbol: str, amount: float, trail_price: float, hard_tp_price: float = 0) -> Dict[str, Any]:
        """Execute a market buy order immediately followed by a Trailing Stop Sell via Alpaca-py."""
        with self.lock:
            try:
                # 1. Submit Market Entry
                market_order_data = MarketOrderRequest(
                    symbol=symbol,
                    qty=amount,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.GTC
                )
                entry_order = self.trading_client.submit_order(order_data=market_order_data)
                
                # 2. Prevent race conditions by giving Alpaca a moment to log the position filling
                time.sleep(1)
                
                # 3. Submit Trailing Stop Exit
                trailing_stop_data = TrailingStopOrderRequest(
                    symbol=symbol,
                    qty=amount,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC,
                    trail_price=round(trail_price, 2)
                )
                self.trading_client.submit_order(order_data=trailing_stop_data)
                
                return {
                    'id': str(entry_order.id),
                    'cost': float(entry_order.notional) if entry_order.notional else (float(entry_order.qty) * float(entry_order.filled_avg_price) if entry_order.filled_avg_price else None)
                }
            except Exception as e:
                raise Exception(f"Alpaca Trailing Buy Failed: {e}")

    def create_trailing_sell_order(self, symbol: str, amount: float, trail_price: float, hard_tp_price: float = 0) -> Dict[str, Any]:
        """Execute a market sell (short) order immediately followed by a Trailing Stop Buy via Alpaca-py."""
        with self.lock:
            try:
                # 1. Submit Market Entry
                market_order_data = MarketOrderRequest(
                    symbol=symbol,
                    qty=amount,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC
                )
                entry_order = self.trading_client.submit_order(order_data=market_order_data)
                
                time.sleep(1)
                
                # 2. Submit Trailing Stop Exit
                trailing_stop_data = TrailingStopOrderRequest(
                    symbol=symbol,
                    qty=amount,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.GTC,
                    trail_price=round(trail_price, 2)
                )
                self.trading_client.submit_order(order_data=trailing_stop_data)
                
                return {
                    'id': str(entry_order.id),
                    'cost': float(entry_order.notional) if entry_order.notional else (float(entry_order.qty) * float(entry_order.filled_avg_price) if entry_order.filled_avg_price else None)
                }
            except Exception as e:
                raise Exception(f"Alpaca Trailing Short Failed: {e}")

