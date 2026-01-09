
import os
import sys
import time
import json
import requests
from tabulate import tabulate

# Add the agents directory to path (script is inside agents/)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Imports now relative to agents/ directory
from agents.polymarket.polymarket import Polymarket
from agents.utils.risk_engine import calculate_ev, kelly_size
from agents.utils.validator import Validator, SharedConfig

def audit_market(pm, validator, market):
    """
    Analyzes a single market and returns a unified audit dict.
    """
    question = market.get('question', 'Unknown')
    outcomes_raw = market.get('outcomes', '[]')
    prices_raw = market.get('outcomePrices', '[]')
    
    outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
    outcome_prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
    
    # We only analyze Binary for now (YES/NO)
    if len(outcomes) != 2 or len(outcome_prices) != 2:
        return None
        
    # Analyze "YES" side
    yes_idx = 0 if outcomes[0] == "Yes" else 1
    yes_price = float(outcome_prices[yes_idx])
    
    print(f"\\n🔍 Auditing: {question[:50]} (Price: {yes_price:.2f})")
    
    # 1. Perplexity Validation
    # We ask Perplexity: "What is the true probability?"
    valid, reason, confidence = validator.validate(question, "Yes", yes_price)
    
    # 2. Risk Engine
    potential_profit = 1.0 - yes_price
    ev = calculate_ev(yes_price, confidence, potential_profit, fees=0.02)
    
    # 3. Decision
    # Kelly Size (assume $100 bankroll for standardization)
    bankroll = 100.0
    rec_size = kelly_size(bankroll, ev, yes_price) if ev > 0.05 else 0.0
    
    decision = "✅ BET YES" if (ev > 0.05 and rec_size > 0) else "⏸ PASS"
    if valid and ev <= 0.05: decision = "⏸ PASS (Low EV)"
    if not valid: decision = "🛑 REJECT (Low Conf)"

    return {
        "Question": question[:40] + "...",
        "Mkt Price": f"{yes_price:.2f}",
        "Agent Est": f"{confidence:.2f}",
        "Delta": f"{confidence - yes_price:+.2f}",
        "EV": f"{ev:.3f}",
        "Decision": decision,
        "Rec Size ($100)": f"${rec_size:.2f}",
        "Reason": reason[:100] + "..." # Truncate for table
    }

def run_audit():
    print("🚀 Starting Logic Audit...")
    
    pm = Polymarket()
    config = SharedConfig()
    validator = Validator(config)
    
    # Fetch active markets
    print("Fetching top active markets...")
    
    # Use simpler API call without unsupported params
    url = "https://gamma-api.polymarket.com/markets?limit=5&closed=false"
    
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        markets = resp.json()
        
        # Handle error response from API
        if isinstance(markets, dict) and 'error' in markets:
            print(f"API Error: {markets['error']}")
            return
            
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return

    results = []
    
    for m in markets:
        try:
            # Skip non-binary for this simple audit
            outcomes_raw = m.get('outcomes', '[]')
            outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
            if len(outcomes) != 2:
                continue
                
            res = audit_market(pm, validator, m)
            if res:
                results.append(res)
                
            # Rate limit for Perplexity
            time.sleep(2) 
        except Exception as e:
            print(f"Skipping market due to error: {e}")
            continue

    print("\n\n📊 AUDIT RESULTS 📊")
    print(tabulate(results, headers="keys", tablefmt="github"))
    
    # Summary
    bets = [r for r in results if "BET" in r['Decision']]
    print(f"\nAudit Complete. Found {len(bets)} trade opportunities out of {len(results)} scanned.")
    if bets:
        print("💡 The agent found value! This indicates the strategy is aggressive/opportunistic.")
    else:
        print("🛡 The agent found NO value. This indicates the strategy is disciplined/safe.")

if __name__ == "__main__":
    run_audit()
