
import os
import sys
import json
import logging
from datetime import datetime

# Add parent path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.utils.TradeRecorder import get_recent_trades
from agents.polymarket.polymarket import Polymarket

BOLD = "\033[1m"
RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"

def main():
    print(f"{BOLD}📊 PAPER TRADING PERFORMANCE ANALYZER{RESET}")
    print("---------------------------------------")
    
    # Init Polymarket
    try:
        pm = Polymarket()
        print("✅ Polymarket API Connected")
    except Exception as e:
        print(f"❌ Failed to connect to Polymarket: {e}")
        return

    trades = get_recent_trades(limit=100)
    if not trades:
        print("No trades found in bot_state.json")
        return

    print(f"Found {len(trades)} recent trades. Analyzing...\n")
    
    total_invested = 0.0
    total_current_value = 0.0
    wins = 0
    losses = 0
    pending = 0
    
    print(f"{'AGENT':<15} {'MARKET':<40} {'SIDE':<10} {'ENTRY':<8} {'CURR':<8} {'PnL':<10}")
    print("-" * 100)

    for t in trades:
        agent = t.get("agent", "unknown")
        market = t.get("market", "Unknown")[:38]
        side = t.get("side", "?")
        entry_price = t.get("price", 0.0)
        amount = t.get("amount_usd", 0.0)
        token_id = t.get("token_id")
        
        # Skip if no token ID (can't track)
        if not token_id:
            continue
            
        total_invested += amount
        
        # Check current price
        curr_price = entry_price # Default to entry if lookup fails
        status = "OPEN"
        try:
            # 1. Check if resolved
            m = pm.get_market(token_id)
            if m and getattr(m, "closed", False):
                # Resolved
                # How to get winner? 
                # Simplified: Check if token index matches winner
                # This is complex without full market object, assume 0 or 100 for now based on 'winner' field if it exists
                status = "RESOLVED"
                # For now, let's just get the price. If resolved, price should be 0 or 1.
                # Polymarket 'price' usually reflects this.
            
            # Get latest price
            # We can use get_mid_price or fetch active markets
            price_data = pm.get_price(token_id)
            if price_data:
                curr_price = float(price_data)
                
        except Exception as e:
            pass # Keep entry price
            
        # Calculate PnL
        shares = amount / entry_price if entry_price > 0 else 0
        current_value = shares * curr_price
        pnl = current_value - amount
        pnl_pct = (pnl / amount) * 100 if amount > 0 else 0
        
        total_current_value += current_value
        
        color = GREEN if pnl >= 0 else RED
        print(f"{agent:<15} {market:<40} {side:<10} ${entry_price:<7.2f} ${curr_price:<7.2f} {color}${pnl:+.2f} ({pnl_pct:+.1f}%){RESET}")
        
    print("-" * 100)
    total_pnl = total_current_value - total_invested
    roi = (total_pnl / total_invested * 100) if total_invested > 0 else 0
    
    color = GREEN if total_pnl >= 0 else RED
    print(f"{BOLD}TOTAL PnL: {color}${total_pnl:+.2f} ({roi:+.2f}%){RESET}")
    print(f"Invested: ${total_invested:.2f} | Current Value: ${total_current_value:.2f}")

if __name__ == "__main__":
    main()
