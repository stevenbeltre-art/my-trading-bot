import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

# Load credentials
load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

# Initialize Alpaca Client
trading_client = TradingClient(api_key, secret_key, paper=True)

print("Attempting to liquidate all open positions and cancel associated bracket orders...")
try:
    # This Alpaca method cancels all open orders (SL/TP) and market-sells all held assets natively
    cancel_statuses = trading_client.close_all_positions(cancel_orders=True)
    
    for status in cancel_statuses:
        print(f"Liquidated: {status.symbol} | Status: {status.status}")
        
    print("\nAccount successfully reset! You should see your Available Balance return to ~$100k.")
    
except Exception as e:
    print(f"Failed to liquidate: {e}")
