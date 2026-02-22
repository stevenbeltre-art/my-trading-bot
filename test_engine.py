from bot.engine import TradingEngine
import time, threading

print('Starting engine...')
engine = TradingEngine()
engine.is_running = True

def run_loop_trace(self):
    print('[TRACE] Thread started')
    while self.is_running:
        try:
            print('[TRACE] Fetching balance...')
            balance_info = self.exchange.fetch_balance()
            print('[TRACE] Balance fetched')
            for symbol in self.symbols:
                print(f'[TRACE] Processing {symbol}...')
                if not self.is_running: break
                
                print(f'[TRACE] Calling fetch_ohlcv for {symbol}...')
                # Adding timeout to ccxt call in case it's hanging natively inside requests
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
                print(f'[TRACE] OHLCV fetched for {symbol}')
                
                print(f'[TRACE] Calling fetch_ticker for {symbol}...')
                ticker = self.exchange.fetch_ticker(symbol)
                print(f'[TRACE] Ticker fetched for {symbol}')
                
                from bot.strategy import StrategyEngine
                import os
                print(f'[TRACE] Initializing StrategyEngine...')
                s = StrategyEngine(os.getenv('GEMINI_API_KEY'))
                
                print(f'[TRACE] Calling determine_trade_action...')
                action = s.determine_trade_action(ohlcv, symbol)
                print(f'[TRACE] Action for {symbol}: {action}')
                time.sleep(1)
        except Exception as e:
            print(f'[TRACE ERROR] {e}')
        print('[TRACE] Full loop complete, sleeping...')
        break # just test one loop
    print('[TRACE] Thread finished')
    
engine._run_loop = run_loop_trace.__get__(engine, TradingEngine)

thread = threading.Thread(target=engine._run_loop)
thread.start()
thread.join(timeout=20)
print('Main execution finished.')
