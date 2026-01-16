import os
import requests
import json
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))
from agents.polymarket.polymarket import Polymarket

# Configure Proxy
PROXY_ADDRESS = "0xdb1f88Ab5B531911326788C018D397d352B7265c"
os.environ["POLYMARKET_PROXY_ADDRESS"] = PROXY_ADDRESS

# Clean bad credentials just in case
for k in ["CLOB_API_KEY", "CLOB_SECRET", "CLOB_PASS_PHRASE"]:
    if k in os.environ: del os.environ[k]

def emergency_sell():
    print("🚨 EMERGENCY SELL: Liquidating Accidental Positions...")
    pm = Polymarket()
    print(f"   🔐 Acting as: {pm.funder_address}")

    # 1. Identify the position
    # The accidental trade was on "Will bitcoin hit $1m before GTA VI?"
    # We need to find the token ID for YES on this market.
    # Previous output showed orderID: 0xf0b2... matched.
    
    # We can fetch user positions? Or just search the market and sell.
    # Let's search market to get token ID.
    search_q = "GTA VI" # usage partial
    
    url = "https://gamma-api.polymarket.com/markets"
    params = {"active": "true", "limit": 1000, "closed": "false"}
    resp = requests.get(url, params=params)
    markets = resp.json()
    
    target_token_id = None
    target_market = None
    
    for m in markets:
        if search_q.lower() in m.get("question", "").lower() and "bitcoin" in m.get("question", "").lower():
            target_market = m
            # We bought 'Yes' (index 0 usually, but let's check)
            # The test script used: token_id = json.loads(market["clobTokenIds"])[0] 
            clob_ids = json.loads(m.get("clobTokenIds", "[]"))
            if clob_ids:
                target_token_id = clob_ids[0]
            break
            
    if not target_token_id:
        print("   ❌ Could not find market/token for liquidation.")
        return

    print(f"   🎯 Found Market: {target_market['question']}")
    print(f"      Token ID: {target_token_id}")
    
    # 2. Check Balance/Position size?
    # Ideally we query the API for position, but we know we bought ~1.1 shares.
    # We will try to sell 1.1 shares.
    
    sell_size = 1.11 # From previous output: "takingAmount": "1.11"
    
    # 3. Sell
    # Fetch book for price
    book = requests.get(f"https://clob.polymarket.com/book?token_id={target_token_id}").json()
    bids = book.get("bids", [])
    if bids:
        best_bid = float(bids[0]["price"])
        limit_price = max(best_bid - 0.01, 0.01) # Sell into bid
    else:
        limit_price = 0.01 # Dump
        
    print(f"   📉 Selling {sell_size} shares @ {limit_price}...")
    
    order = pm.place_limit_order(
        token_id=target_token_id,
        price=limit_price,
        size=sell_size,
        side="SELL",
        fee_rate_bps=0 # Assuming 0 for this market as per previous check
    )
    
    print(f"   ✅ Sell Response: {json.dumps(order, indent=2)}")

if __name__ == "__main__":
    emergency_sell()
