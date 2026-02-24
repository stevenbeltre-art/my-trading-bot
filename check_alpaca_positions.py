import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest

load_dotenv()
trading_client = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)
positions = trading_client.get_all_positions()
print(f"Number of open positions: {len(positions)}")
for p in positions:
    print(f"Symbol: {p.symbol}, Qty: {p.qty}, Market Value: {p.market_value}")
    
req = GetOrdersRequest(status="all", limit=5)
orders = trading_client.get_orders(filter=req)
print(f"Number of recent orders: {len(orders)}")
for o in orders:
    print(f"Order: {o.symbol} {o.side} {o.qty} {o.type} | Status: {o.status}")
