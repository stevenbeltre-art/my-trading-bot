import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

load_dotenv()
api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

try:
    client = TradingClient(api_key, secret_key, paper=True)
    account = client.get_account()
    print(f'Equity: ${account.equity}')
    print(f'Cash: ${account.cash}')
    print(f'Buying Power: ${account.buying_power}')
    positions = client.get_all_positions()
    print('Open Positions:')
    for p in positions:
        print(f'{p.symbol}: Qty {p.qty}, Unrealized PnL ${p.unrealized_pl}, Market Value ${p.market_value}')
except Exception as e:
    print(f'Error: {e}')
