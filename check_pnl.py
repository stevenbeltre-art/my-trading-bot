import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

load_dotenv()
api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

client = TradingClient(api_key, secret_key, paper=True)

try:
    account = client.get_account()
    print(f"Equity: ${account.equity}")
    print(f"Buying Power: ${account.buying_power}")
    print(f"Initial Margin: ${account.initial_margin}")
    print(f"Cash: ${account.cash}")
    
    positions = client.get_all_positions()
    print("\n--- Open Positions ---")
    for p in positions:
        print(f"{p.symbol}: Qty {p.qty}, Unrealized PnL ${p.unrealized_pl}, Market Value ${p.market_value}")
        
except Exception as e:
    print(e)
