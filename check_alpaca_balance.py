import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

load_dotenv()
trading_client = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)
acc = trading_client.get_account()
print(f"Equity: {acc.equity}")
print(f"Cash: {acc.cash}")
print(f"Buying Power: {acc.buying_power}")
print(f"Non-marginable Buying Power: {acc.non_marginable_buying_power}")
print(f"Daytrading Buying Power: {acc.daytrading_buying_power}")
