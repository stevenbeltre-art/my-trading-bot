import pandas as pd
import ta
import google.generativeai as genai
from alpaca.data.historical import NewsClient
from alpaca.data.requests import NewsRequest
from typing import Dict, Any

class StrategyEngine:
    def __init__(self, gemini_api_key: str, alpaca_api_key: str, alpaca_secret_key: str):
        self.gemini_api_key = gemini_api_key
        # Configure Gemini 
        genai.configure(api_key=self.gemini_api_key)
        # Using the specified Gemini 1.5 Flash model
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Alpaca News Client for Multi-Asset tracking
        self.news_client = NewsClient(alpaca_api_key, alpaca_secret_key)
        
        # State to share with the UI, mapping symbol -> metrics dict
        self.metrics = {}

    def analyze_technicals(self, ohlcv_15m: list, ohlcv_4h: list, symbol: str) -> Dict[str, Any]:
        """
        Calculates RSI and MACD on 15m for entry, and MACD on 4H for Macro Trend.
        """
        # 15m DataFrame
        df_15m = pd.DataFrame(ohlcv_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_15m['rsi'] = ta.momentum.RSIIndicator(close=df_15m['close'], window=14).rsi()
        macd_15m = ta.trend.MACD(close=df_15m['close'], window_slow=26, window_fast=12, window_sign=9)
        df_15m['macd'] = macd_15m.macd()
        df_15m['macd_signal'] = macd_15m.macd_signal()
        
        # 4H DataFrame for Macro Trend Filter
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        macd_4h = ta.trend.MACD(close=df_4h['close'], window_slow=26, window_fast=12, window_sign=9)
        df_4h['macd_hist'] = macd_4h.macd_diff() # Histogram represents momentum
        
        if len(df_15m) < 2 or len(df_4h) < 2:
            return {"rsi": None, "macd": None, "signal": "NEUTRAL", "macro": "NEUTRAL"}
            
        latest_15m = df_15m.iloc[-1]
        latest_4h = df_4h.iloc[-1]
        
        rsi_val = latest_15m.get('rsi', 50)
        macd_val = latest_15m.get('macd', 0)
        macd_signal = latest_15m.get('macd_signal', 0)
        macro_hist = latest_4h.get('macd_hist', 0)

        # Macro Trend logic: Positive Histogram = Bullish Macro
        macro_trend = "BULLISH" if macro_hist > 0 else "BEARISH"

        # Signal logic: Momentum Gathering (RSI < 55) + MACD crossover
        tech_signal = "NEUTRAL"
        if rsi_val < 55 and macd_val > macd_signal: 
            tech_signal = "BULLISH"
        elif rsi_val > 65 and macd_val < macd_signal: 
            tech_signal = "BEARISH"

        if symbol not in self.metrics:
            self.metrics[symbol] = {}
        self.metrics[symbol]['rsi'] = rsi_val
        self.metrics[symbol]['macd'] = macd_val
        self.metrics[symbol]['tech_signal'] = tech_signal
        self.metrics[symbol]['macro_trend'] = macro_trend

        return {
            "rsi": rsi_val,
            "macd": macd_val,
            "signal": tech_signal,
            "macro": macro_trend
        }

    def fetch_recent_news(self, symbol: str) -> str:
        """
        Fetches the 5 most recent headlines using Alpaca NewsClient.
        """
        try:
            # Alpaca expects the base symbol, e.g. "BTC" or "AAPL"
            query_symbol = symbol.split('/')[0] if "/" in symbol else symbol
            
            request_params = NewsRequest(
                symbols=query_symbol,
                limit=5
            )
            news = self.news_client.get_news(request_params)
            
            headlines = [article.headline for article in news.news]
            
            if not headlines:
                return f"No recent news found for {query_symbol}."
                
            return "\n".join(headlines)
        except Exception as e:
            print(f"Error fetching news for {symbol}: {e}")
            return "No recent news found."

    def analyze_sentiment(self, headlines: str) -> str:
        """
        Queries Gemini Flash with a strict prompt to analyze news sentiment.
        """
        if "No recent news" in headlines:
            return "NEUTRAL"
            
        prompt = f"""
        You are a highly advanced Wall Street quantitative trading AI.
        Analyze the following top 5 recent news headlines for cryptocurrency.
        Determine the overall sentiment as it relates to the crypto market.
        
        Follow these strict instructions:
        Respond with exactly ONE WORD from the following list:
        BULLISH
        BEARISH
        NEUTRAL
        
        Headlines:
        {headlines}
        """
        try:
            response = self.model.generate_content(prompt)
            # Clean the output to ensure it's just the single word
            result = response.text.strip().upper()
            
            # Fallback if Gemini is too verbose
            if "BULLISH" in result:
                return "BULLISH"
            elif "BEARISH" in result:
                return "BEARISH"
            return "NEUTRAL"
        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            return "ERROR"

    def determine_trade_action(self, ohlcv_15m: list, ohlcv_4h: list, symbol: str) -> str:
        """
        The "Edge": Requires Technical signal to align with Macro Trend AND Sentiment.
        """
        tech_analysis = self.analyze_technicals(ohlcv_15m, ohlcv_4h, symbol)
        tech_signal = tech_analysis.get('signal', 'NEUTRAL')
        macro_trend = tech_analysis.get('macro', 'NEUTRAL')
        
        if symbol not in self.metrics:
            self.metrics[symbol] = {}
            
        self.metrics[symbol]['rejection_reason'] = "Monitoring..."
            
        if tech_signal == "BULLISH":
            # 2. Sentiment Directional Filter
            headlines = self.fetch_recent_news(symbol)
            sentiment_signal = self.analyze_sentiment(headlines)
            self.metrics[symbol]['sentiment'] = sentiment_signal
            
            # 1. Aggressive Macro Filter (Only block if BOTH Macro AND Sentiment are Bearish)
            if macro_trend == "BEARISH" and sentiment_signal == "BEARISH":
                self.metrics[symbol]['rejection_reason'] = "Blocked: 4H Macro & News Bearish"
                return "HOLD"
                
            # If we pass all filters
            self.metrics[symbol]['rejection_reason'] = "Signal Approved"
        elif tech_signal == "BEARISH":
            # 2. Sentiment Directional Filter
            headlines = self.fetch_recent_news(symbol)
            sentiment_signal = self.analyze_sentiment(headlines)
            self.metrics[symbol]['sentiment'] = sentiment_signal
            
            # 1. Aggressive Macro Filter for Shorts (Only block if BOTH Macro AND Sentiment are Bullish)
            if macro_trend == "BULLISH" and sentiment_signal == "BULLISH":
                self.metrics[symbol]['rejection_reason'] = "Blocked: 4H Macro & News Bullish"
                return "HOLD"
                
            # If we pass filters, execute Short/Sell
            self.metrics[symbol]['rejection_reason'] = "Signal Approved (SHORT)"
            return "SELL"
            
        else:
            self.metrics[symbol]['sentiment'] = "WAITING ON MATH"
            
        return "HOLD"
