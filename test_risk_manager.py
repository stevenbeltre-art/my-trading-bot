from bot.risk_manager import RiskManager
rm = RiskManager(risk_per_trade_pct=0.10, atr_sl_multiplier=1.5, rr_ratio=1.5)

# Mock variables from log
balance = 99585.30
current_price = 1825.1
sl_distance = 42.81

risk_capital_dollars = balance * rm.risk_per_trade_pct
amount_to_buy = risk_capital_dollars / sl_distance
        
max_notional = balance * 0.95 
print("max_notional:", max_notional)
if max_notional > 195000:
    max_notional = 195000
    
proposed_cost = amount_to_buy * current_price
print("proposed_cost:", proposed_cost)
if proposed_cost > max_notional:
    print("limiting amount_to_buy")
    amount_to_buy = max_notional / current_price
    
print("amount_to_buy calculated:", amount_to_buy)
print("notional cost:", amount_to_buy * current_price)
