import os
import time
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest, LimitOrderRequest, OrderClass
from alpaca.trading.enums import OrderSide, TimeInForce

load_dotenv()
api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

client = TradingClient(api_key, secret_key, paper=True)

try:
    print("Testing OCO again")
    # To place an OCO order, we need a parent order. But trailing stop is not supported in OCO inside Alpaca's current API directly for crypto. 
    # Actually, Trailing Stop is supported as an independent order, but not inside a bracket.
    # What if we just submit a Limit Order for the Take Profit, and if it fills, we cancel the Trailing Stop?
    # Or, submit Trailing Stop, and monitor price in engine? 
    # The safest way is to submit BOTH via OCO. Let's see if OCO supports Trailing.
    print(LimitOrderRequest.model_fields.keys())
except Exception as e:
    print(e)
