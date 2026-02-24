import os
import time
import pandas as pd
import ta
from dotenv import load_dotenv
from bot.exchange import ExchangeInterface

load_dotenv()
exchange = ExchangeInterface(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))
ohlcv = exchange.fetch_ohlcv("ETH/USD", timeframe='15m', limit=100)
df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
print("Last OHLCV row:", df.tail(1))
window = 14
atr_indicator = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=window)
atr = atr_indicator.average_true_range().iloc[-1]
print("ATR is:", atr)

sl_distance = atr * 1.5
print("sl_distance:", sl_distance)

risk_capital = 99585.30 * 0.10
amount_to_buy = risk_capital / sl_distance
print("amount_to_buy natively calculated:", amount_to_buy)

max_notional = 99585.30 * 0.95
if max_notional > 195000: max_notional = 195000
    
proposed_cost = amount_to_buy * df['close'].iloc[-1]
if proposed_cost > max_notional:
    print("limiting amount_to_buy to max_notional")
    amount_to_buy = max_notional / df['close'].iloc[-1]
    
print("final amount_to_buy:", amount_to_buy)
print("final notional cost:", amount_to_buy * df['close'].iloc[-1])
