import pandas as pd
import ta
import google.generativeai as genai
import feedparser
from typing import Dict, Any

class StrategyEngine:
    def __init__(self, gemini_api_key: str):
        self.gemini_api_key = gemini_api_key
        # Configure Gemini 
        genai.configure(api_key=self.gemini_api_key)
        # Using the specified Gemini 1.5 Flash model
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        
        # State to share with the UI, mapping symbol -> metrics dict
        self.metrics = {}

    def analyze_technicals(self, ohlcv: list, symbol: str) -> Dict[str, Any]:
        """
        Calculates RSI and MACD using the 'ta' package.
        Expected OHLCV format from ccxt: [timestamp, open, high, low, close, volume]
        """
        # Convert to DataFrame
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)

        # Calculate Indicators
        df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
        macd_indicator = ta.trend.MACD(close=df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['macd'] = macd_indicator.macd()
        df['macd_signal'] = macd_indicator.macd_signal()
        
        # Determine signals based on the last closed candle
        if len(df) < 2:
            return {"rsi": None, "macd": None, "signal": "NEUTRAL"}
            
        latest = df.iloc[-1]
        
        rsi_val = latest.get('rsi', 50)
        macd_val = latest.get('macd', 0)
        macd_signal = latest.get('macd_signal', 0)

        # Basic signal logic: Oversold RSI + MACD crossover
        tech_signal = "NEUTRAL"
        if rsi_val < 35 and macd_val > macd_signal: # Oversold and MACD positive momentum
            tech_signal = "BULLISH"
        elif rsi_val > 65 and macd_val < macd_signal: # Overbought and MACD negative momentum
            tech_signal = "BEARISH"

        if symbol not in self.metrics:
            self.metrics[symbol] = {}
        self.metrics[symbol]['rsi'] = rsi_val
        self.metrics[symbol]['macd'] = macd_val
        self.metrics[symbol]['tech_signal'] = tech_signal

        return {
            "rsi": rsi_val,
            "macd": macd_val,
            "macd_signal": macd_signal,
            "signal": tech_signal
        }

    def fetch_recent_news(self) -> str:
        """
        Fetches the 5 most recent headlines from CoinDesk RSS feed.
        """
        # Using a reliable RSS feed per requirements
        feed_url = "https://www.coindesk.com/arc/outboundfeeds/rss/"
        feed = feedparser.parse(feed_url)
        
        headlines = []
        for entry in feed.entries[:5]: # Get top 5
            headlines.append(entry.title)
            
        if not headlines:
            return "No recent news found."
            
        return "\n".join(headlines)

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

    def determine_trade_action(self, ohlcv: list, symbol: str) -> str:
        """
        The "Edge": Requires BOTH technicals and sentiment to agree.
        """
        tech_analysis = self.analyze_technicals(ohlcv, symbol)
        tech_signal = tech_analysis.get('signal', 'NEUTRAL')
        
        if symbol not in self.metrics:
            self.metrics[symbol] = {}
            
        if tech_signal == "BULLISH":
            headlines = self.fetch_recent_news()
            sentiment_signal = self.analyze_sentiment(headlines)
            self.metrics[symbol]['sentiment'] = sentiment_signal
            
            # Rule: Only execute BUY if BOTH agree
            if sentiment_signal == "BULLISH":
                return "BUY"
        else:
            # If technicals aren't bullish, we don't query the API to save money, just mark it WAITING
            self.metrics[symbol]['sentiment'] = "WAITING ON MATH"
            
        return "HOLD"
