import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

load_dotenv()
api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

try:
    client = TradingClient(api_key, secret_key, paper=True)
    positions = client.get_all_positions()
    for p in positions:
        print(f"Liquidating {p.qty} of {p.symbol} -> Securing {p.unrealized_pl} Profit!")
        side = OrderSide.SELL if p.side == 'long' else OrderSide.BUY
        req = MarketOrderRequest(
            symbol=p.symbol,
            qty=abs(float(p.qty)),
            side=side,
            time_in_force=TimeInForce.GTC
        )
        client.submit_order(req)
        print(f"Liquidated {p.symbol}")
except Exception as e:
    print(f'Error: {e}')
