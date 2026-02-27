import pandas as pd
import ta
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from alpaca.data.historical import NewsClient
from alpaca.data.requests import NewsRequest
from typing import Dict, Any

class StrategyEngine:
    def __init__(self, gemini_api_key: str, alpaca_api_key: str, alpaca_secret_key: str):
        self.gemini_api_key = gemini_api_key
        
        # Initialize NLTK VADER
        try:
            self.sia = SentimentIntensityAnalyzer()
        except LookupError:
            nltk.download('vader_lexicon', quiet=True)
            self.sia = SentimentIntensityAnalyzer()
        
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
        
        # 20-period Volume SMA
        df_15m['volume_sma'] = df_15m['volume'].rolling(window=20).mean()
        
        # VWAP Calculation
        vwap_indicator = ta.volume.VolumeWeightedAveragePrice(
            high=df_15m['high'], low=df_15m['low'], close=df_15m['close'], volume=df_15m['volume'], window=14
        )
        df_15m['vwap'] = vwap_indicator.volume_weighted_average_price()
        
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
        vwap_val = latest_15m.get('vwap', 0)
        close_price = latest_15m.get('close', 0)
        volume_current = latest_15m.get('volume', 0)
        volume_sma = latest_15m.get('volume_sma', 0)
        macro_hist = latest_4h.get('macd_hist', 0)

        volume_spike = volume_current > (1.5 * volume_sma) if volume_sma > 0 else False

        # Macro Trend logic: Positive Histogram = Bullish Macro
        macro_trend = "BULLISH" if macro_hist > 0 else "BEARISH"

        # Signal logic: Momentum Gathering (RSI < 55) + MACD crossover + VWAP Confirmation
        tech_signal = "NEUTRAL"
        if rsi_val < 55 and macd_val > macd_signal and close_price > vwap_val: 
            tech_signal = "BULLISH"
        elif rsi_val > 65 and macd_val < macd_signal and close_price < vwap_val: 
            tech_signal = "BEARISH"

        if symbol not in self.metrics:
            self.metrics[symbol] = {}
        self.metrics[symbol]['rsi'] = rsi_val
        self.metrics[symbol]['macd'] = macd_val
        self.metrics[symbol]['vwap'] = vwap_val
        self.metrics[symbol]['tech_signal'] = tech_signal
        self.metrics[symbol]['macro_trend'] = macro_trend

        return {
            "rsi": rsi_val,
            "macd": macd_val,
            "vwap": vwap_val,
            "signal": tech_signal,
            "macro": macro_trend,
            "volume_spike": volume_spike
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
        Calculates mathematical sentiment using NLTK VADER on the aggregate headlines.
        """
        if "No recent news" in headlines:
            return "NEUTRAL"
            
        try:
            # We split the string block of headlines back into individual headlines for evaluation
            lines = headlines.split('\n')
            total_score = 0
            for line in lines:
                scores = self.sia.polarity_scores(line)
                total_score += scores['compound']
                
            avg_score = total_score / len(lines) if lines else 0
            
            # VADER compound score ranges from -1 (most negative) to 1 (most positive)
            if avg_score >= 0.2:
                return "BULLISH"
            elif avg_score <= -0.5: # We aggressively block extremely negative news
                return "BEARISH"
            else:
                return "NEUTRAL"
        except Exception as e:
            print(f"Error calculating NLTK sentiment: {e}")
            return "ERROR"

    def determine_trade_action(self, ohlcv_15m: list, ohlcv_4h: list, symbol: str) -> str:
        """
        The "Edge": Requires Technical signal to align with Macro Trend AND Sentiment.
        """
        tech_analysis = self.analyze_technicals(ohlcv_15m, ohlcv_4h, symbol)
        tech_signal = tech_analysis.get('signal', 'NEUTRAL')
        macro_trend = tech_analysis.get('macro', 'NEUTRAL')
        volume_spike = tech_analysis.get('volume_spike', False)
        
        if symbol not in self.metrics:
            self.metrics[symbol] = {}
            
        self.metrics[symbol]['rejection_reason'] = "Monitoring..."
            
        if tech_signal == "BULLISH":
            # 0. Smart Money Volume Filter
            if not volume_spike:
                self.metrics[symbol]['rejection_reason'] = "Blocked: Low Institutional Volume"
                return "HOLD"

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
            return "BUY"
        elif tech_signal == "BEARISH":
            # 0. Smart Money Volume Filter
            if not volume_spike:
                self.metrics[symbol]['rejection_reason'] = "Blocked: Low Institutional Volume"
                return "HOLD"
                
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
