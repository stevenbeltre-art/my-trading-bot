from typing import Dict, Any

class RiskManager:
    def __init__(self, trailing_sl_pct: float = 0.04, tp_pct: float = 0.08, max_risk_pct: float = 0.05):
        self.trailing_sl_pct = trailing_sl_pct
        self.tp_pct = tp_pct
        self.max_risk_pct = max_risk_pct

    def calculate_position_size(self, balance: float, current_price: float) -> float:
        """
        Calculates position size never risking more than max_risk_pct of total account.
        """
        # Simplified position sizing based on available balance and max risk
        risk_capital = balance * self.max_risk_pct
        # Assuming we can buy fractional amounts
        amount_to_buy = risk_capital / current_price
        return amount_to_buy

    def check_take_profit(self, entry_price: float, current_price: float) -> bool:
        """
        Checks if the current price hit the 5% take-profit target.
        """
        target_price = entry_price * (1 + self.tp_pct)
        return current_price >= target_price

    def calculate_trailing_stop(self, entry_price: float, highest_price: float) -> float:
        """
        Calculates the 2% trailing stop-loss price.
        """
        # The stop loss moves up with the highest price reached
        # If highest price is still entry price, then SL is 2% below entry
        return highest_price * (1 - self.trailing_sl_pct)

    def check_stop_loss(self, current_price: float, trailing_stop_price: float) -> bool:
        """
        Checks if current price hit the trailing stop-loss.
        """
        return current_price <= trailing_stop_price
