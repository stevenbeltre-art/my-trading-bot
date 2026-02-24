import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest, TrailingStopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

load_dotenv()
api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

client = TradingClient(api_key, secret_key, paper=True)

try:
    req = MarketOrderRequest(
        symbol="SPY",
        qty=1,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.GTC,
        order_class="bracket",
        take_profit=TakeProfitRequest(limit_price=600.0),
        stop_loss=StopLossRequest(stop_price=400.0) # We want to know if we can pass trail_percent here!
    )
    # Wait, StopLossRequest only has stop_price and limit_price?
    print(StopLossRequest.model_fields.keys())
except Exception as e:
    print(e)
