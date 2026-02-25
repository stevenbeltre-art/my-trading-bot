import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

load_dotenv()
api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

try:
    client = TradingClient(api_key, secret_key, paper=True)
    account = client.get_account()
    print(f'Equity: ${float(account.equity):.2f}')
    print(f'Buying Power: ${float(account.buying_power):.2f}')
    
    positions = client.get_all_positions()
    print('\n--- Open Positions ---')
    for p in positions:
        print(f'{p.symbol}: Qty {p.qty}, Unrealized PnL ${float(p.unrealized_pl):.2f}, Market Value ${float(p.market_value):.2f}')
except Exception as e:
    print(f'Error: {e}')
