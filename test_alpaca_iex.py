import os
from dotenv import load_dotenv
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from datetime import datetime, timedelta

load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
secret = os.getenv("ALPACA_SECRET_KEY")

client = StockHistoricalDataClient(api_key, secret)

req = StockBarsRequest(
    symbol_or_symbols="AAPL",
    timeframe=TimeFrame.Minute,
    start=datetime.utcnow() - timedelta(days=2),
    end=datetime.utcnow() - timedelta(minutes=16),
    feed=DataFeed.IEX
)

try:
    bars = client.get_stock_bars(req)
    print("SUCCESS! IEX Feed worked.")
    print(bars.df.head(2))
except Exception as e:
    print(f"FAILED: {e}")
