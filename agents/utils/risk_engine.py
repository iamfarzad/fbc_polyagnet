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

def kelly_size(balance: float, ev: float, price: float, max_risk_pct: float = 0.10, 
               invisibility_cap: float = 50.0, risk_multiplier: float = 1.0) -> float:
    """
    Calculates trade size using Half-Kelly Criterion.
    
    Args:
        balance: Current USDC balance
        ev: Expected Value of the trade
        price: Entry price (probability)
        max_risk_pct: Max % of balance to risk (default 10%)
        invisibility_cap: Absolute max bet to stay invisible (default $50)
        risk_multiplier: Dynamic factor from HedgeFundAnalyst (0.0 - 1.5x)
    """
    if ev <= 0 or price <= 0 or price >= 1 or balance <= 0:
        return 0.0
        
    kelly_f = ev / (1.0 - price)
    size_pct = kelly_f * 0.5  # Half-Kelly for safety
    
    # Apply Dynamic Risk Adjustment (e.g. from LLM or Context)
    size_pct *= risk_multiplier
    
    # Cap at max_risk_pct of balance
    SAFE_CAP = 0.15  # Never more than 15% of balance
    final_pct = min(size_pct, max_risk_pct, SAFE_CAP)
    
    size_usd = balance * final_pct
    
    # Invisibility: Never exceed the cap to avoid moving market
    # Note: If multiplier is huge, we still respect the hard invisibility cap?
    # Actually, invisibility cap is usually a market structure limit.
    # We should probably respect it unless multiplier is explicit about "Force".
    # For now, safe default: Cap applies.
    size_usd = min(size_usd, invisibility_cap)
    
    # Minimum viable bet check
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
