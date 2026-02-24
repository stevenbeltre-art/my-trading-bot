import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TrailingStopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

load_dotenv()
print(TrailingStopOrderRequest.model_fields.keys())
