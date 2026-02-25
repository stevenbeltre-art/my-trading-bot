import os
import pandas as pd
import ta
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

load_dotenv()
api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

def fetch_historical_data(symbol, start_date, end_date):
    client = CryptoHistoricalDataClient(api_key, secret_key)
    request_params = CryptoBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        start=start_date,
        end=end_date
    )
    # Fetch 1-minute bars, then resample to 15m and 4H to mimic live bot if we wanted, 
    # but let's just fetch 15m directly for speed.
    from alpaca.data.timeframe import TimeFrameUnit
    request_params_15m = CryptoBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame(15, TimeFrameUnit.Minute),
        start=start_date,
        end=end_date
    )
    bars = client.get_crypto_bars(request_params_15m)
    df = bars.df
    # Alpaca returns multi-index (symbol, timestamp). Drop symbol level.
    if not df.empty:
        df = df.reset_index(level=0, drop=True)
    return df

def run_backtest(df):
    if df.empty:
        print("No data fetched.")
        return
        
    print(f"Data points: {len(df)}")
    
    # 1. Calculate Indicators
    df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
    macd_ind = ta.trend.MACD(close=df['close'], window_fast=12, window_slow=26, window_sign=9)
    df['macd'] = macd_ind.macd()
    df['macd_signal'] = macd_ind.macd_signal()
    
    # VWAP
    vwap_ind = ta.volume.VolumeWeightedAveragePrice(
        high=df['high'], low=df['low'], close=df['close'], volume=df['volume'], window=14
    )
    df['vwap'] = vwap_ind.volume_weighted_average_price()
    
    # ATR for Trailing Stop
    atr_ind = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['atr'] = atr_ind.average_true_range()
    
    df.dropna(inplace=True)
    
    # 2. Simulation State
    initial_capital = 100000.0
    capital = initial_capital
    position_qty = 0.0
    entry_price = 0.0
    trailing_stop_price = 0.0
    trades = []
    
    # Loop over the dataframe rows
    for i in range(len(df)):
        row = df.iloc[i]
        
        current_price = row['close']
        rsi_val = row['rsi']
        macd_val = row['macd']
        macd_sig = row['macd_signal']
        vwap_val = row['vwap']
        atr_val = row['atr']
        
        # Check Open Position
        if position_qty > 0:
            unrealized_pnl = position_qty * (current_price - entry_price)
            
            # Floor (Trailing Stop) Check - hit trailing stop if the low pierces it
            if row['low'] <= trailing_stop_price:
                # Execution at trailing stop price (approx)
                exit_price = trailing_stop_price
                realized_pnl = position_qty * (exit_price - entry_price)
                capital += (position_qty * exit_price) 
                trades.append({
                    'type': 'Trailing Stop',
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'pnl': realized_pnl,
                    'timestamp': df.index[i]
                })
                position_qty = 0.0
                
            # Ceiling (Hard TP $5,000) Check - use high to see if we breached 5000 profit
            elif position_qty * (row['high'] - entry_price) >= 5000.0:
                # Math: qty * (exit_price - entry_price) = 5000
                # exit_price = (5000 / qty) + entry_price
                exit_price = (5000.0 / position_qty) + entry_price
                
                # Cap exit_price at row['high'] if gap up (rare for 15m but precise)
                exit_price = min(exit_price, row['high'])
                realized_pnl = position_qty * (exit_price - entry_price)
                capital += (position_qty * exit_price)
                trades.append({
                    'type': 'Take Profit',
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'pnl': realized_pnl,
                    'timestamp': df.index[i]
                })
                position_qty = 0.0
                
            else:
                # Move Trailing Stop up
                new_trail = current_price - (1.5 * atr_val) # Phase 10 logic: 1.5 ATR trailing
                if new_trail > trailing_stop_price:
                    trailing_stop_price = new_trail

        # Look for Entry if not holding
        if position_qty == 0:
             # Strategy (from strategy.py): RSI < 55, MACD > Signal, Close > VWAP
             if rsi_val < 55 and macd_val > macd_sig and current_price > vwap_val:
                 # Risk Manager: Calculate Volatility-Adjusted Position Size
                 sl_distance = atr_val * 1.5
                 risk_capital_dollars = capital * 0.10
                 
                 amount_to_buy = risk_capital_dollars / sl_distance
                 
                 # Cap the position size so the total cost doesn't exceed available purchasing power
                 max_notional = capital * 0.95 
                 
                 proposed_cost = amount_to_buy * current_price
                 if proposed_cost > max_notional:
                     amount_to_buy = max_notional / current_price
                     
                 position_qty = amount_to_buy
                 capital -= (position_qty * current_price)
                 entry_price = current_price
                 trailing_stop_price = current_price - (1.5 * atr_val)
                 
    # Force close at end of data if still open
    if position_qty > 0:
        capital += position_qty * df.iloc[-1]['close']
        trades.append({
            'type': 'End of Data Close',
            'pnl': position_qty * (df.iloc[-1]['close'] - entry_price)
        })
        
    # Analyze Results
    print("\n=== Backtest Results ===")
    total_trades = len(trades)
    winning_trades = len([t for t in trades if t['pnl'] > 0])
    losing_trades = len([t for t in trades if t['pnl'] <= 0])
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    final_roi = ((capital - initial_capital) / initial_capital) * 100
    
    print(f"Initial Capital: ${initial_capital:,.2f}")
    print(f"Final Capital:   ${capital:,.2f}")
    print(f"Net ROI:         {final_roi:.2f}%")
    print(f"Total Trades:    {total_trades}")
    print(f"Win Rate:        {win_rate:.2f}%")
    print(f"Wins: {winning_trades} | Losses: {losing_trades}")
    
    profits = [t['pnl'] for t in trades]
    if profits:
        print(f"Max Win:  ${max(profits):,.2f}")
        print(f"Max Loss: ${min(profits):,.2f}")
        
if __name__ == "__main__":
    symbol = "ETH/USD"
    # Backtest over 3 months first to verify logic
    end_time = datetime.now()
    start_time = end_time - timedelta(days=90)
    
    print(f"Fetching Historical Data for {symbol} from {start_time.date()} to {end_time.date()}...")
    df = fetch_historical_data(symbol, start_time, end_time)
    print("Executing Backtest Simulation...")
    run_backtest(df)
