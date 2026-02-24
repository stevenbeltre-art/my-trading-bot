import pandas as pd
import ta
from typing import Dict, Any

class RiskManager:
    def __init__(self, risk_per_trade_pct: float = 0.10, atr_sl_multiplier: float = 1.5, rr_ratio: float = 1.5):
        self.risk_per_trade_pct = risk_per_trade_pct
        self.atr_sl_multiplier = atr_sl_multiplier
        self.rr_ratio = rr_ratio

    def calculate_atr(self, df: pd.DataFrame, window: int = 14) -> float:
        """Calculates the Average True Range (ATR) to measure current market volatility."""
        if len(df) < window:
            return 0.0
        atr_indicator = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=window)
        return atr_indicator.average_true_range().iloc[-1]

    def calculate_trade_parameters(self, balance: float, current_price: float, ohlcv: list, direction: str = "BUY") -> Dict[str, float]:
        """
        Calculates position size and bracket logic based on ATR volatility.
        Ensures the portfolio only loses `risk_per_trade_pct` if the stop loss is hit.
        """
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        atr = self.calculate_atr(df)
        if atr == 0.0:
            return {"amount": 0.0, "sl_price": 0.0, "tp_price": 0.0}

        # 1. Calculate Distances based on volatility
        sl_distance = atr * self.atr_sl_multiplier
        tp_distance = sl_distance * self.rr_ratio
        
        # 2. Apply direction-specific logic
        if direction == "BUY":
            sl_price = current_price - sl_distance
            tp_price = current_price + tp_distance
        else: # "SELL" (Short)
            sl_price = current_price + sl_distance
            tp_price = current_price - tp_distance

        # 3. Calculate Volatility-Adjusted Position Size
        # If we hit SL, we lose strictly (balance * 0.10) dollars.
        risk_capital_dollars = balance * self.risk_per_trade_pct
        
        # How many units can we buy so that a drop of `sl_distance` equals `risk_capital_dollars`?
        amount_to_buy = risk_capital_dollars / sl_distance
        
        # Cap the position size so the total cost doesn't exceed our available purchasing power
        # (Using 95% of available balance to leave room for fees/slippage)
        max_notional = balance * 0.95 
        
        # Alpaca has a strict $200,000 notional limit per crypto order
        if max_notional > 195000:
            max_notional = 195000
            
        proposed_cost = amount_to_buy * current_price
        if proposed_cost > max_notional:
            amount_to_buy = max_notional / current_price

        return {
            "amount": round(amount_to_buy, 4),
            "sl_price": round(sl_price, 2),
            "tp_price": round(tp_price, 2),
            "trail_price": round(sl_distance, 2)
        }
