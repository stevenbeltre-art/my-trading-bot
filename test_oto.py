import os
import time
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TrailingStopOrderRequest, LimitOrderRequest, TakeProfitRequest
from alpaca.trading.enums import OrderSide, TimeInForce

load_dotenv()
api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

client = TradingClient(api_key, secret_key, paper=True)

try:
    print("Testing OCO (One-Cancels-Other) directly using alpaca-py")
    # Actually, can we just do a bracket order with Trailing? Let's trace back to Bracket Order logic:
    # market_order_data = MarketOrderRequest(
    #    ...
    #    take_profit=TakeProfitRequest(limit_price=...),
    #    stop_loss=StopLossRequest(stop_price=...)  # But this only accepts static stops
    # )
    #
    # Wait, can we submit an OCO manually?
    # No, OCO requires limit or stop order as the entry.
except Exception as e:
    print(e)
