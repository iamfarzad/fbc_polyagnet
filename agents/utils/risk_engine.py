from datetime import datetime

def calculate_ev(price: float, win_prob: float, potential_profit: float, fees: float = 0.01) -> float:
    """
    Calculates Expected Value (EV) of a trade.
    EV = (win_prob * profit) - (loss_prob * loss) - fees
    """
    if price <= 0 or price >= 1:
        return 0.0
    # profit = potential_profit (1-price), loss = price
    ev = (win_prob * potential_profit) - ((1.0 - win_prob) * price) - fees
    return max(ev, 0.0)

def kelly_size(balance: float, ev: float, price: float, max_risk_pct: float = 0.02) -> float:
    """
    Calculates trade size using Half-Kelly Criterion.
    """
    if ev <= 0 or price <= 0 or price >= 1 or balance <= 0:
        return 0.0
        
    kelly_f = ev / (1.0 - price)
    size_pct = kelly_f * 0.5 
    
    # PATCH: Ensure we never bet more than 10% of balance regardless of Kelly
    SAFE_CAP = 0.10 
    final_pct = min(size_pct, max_risk_pct, SAFE_CAP)
    
    size_usd = balance * final_pct
    
    # Safety: Absolute ceiling for the account size provided ($200)
    # Don't let a single bet exceed $20 until balance grows.
    size_usd = min(size_usd, 20.0)
    
    return max(size_usd, 0.50) if size_usd > 0.10 else 0.0

def check_drawdown(initial_balance: float, current_balance: float, drawdown_limit: float = 0.05) -> bool:
    """
    Checks if global drawdown limit has been hit.
    :return: True if SAFE to trade, False if drawdown limit hit.
    """
    if initial_balance <= 0: 
        return True # Edge case
        
    drawdown = (initial_balance - current_balance) / initial_balance
    if drawdown > drawdown_limit:
        return False
    return True
