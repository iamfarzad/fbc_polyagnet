
import os
import sys
import ast
import json
import logging
import requests

# Ensure the agents module is in the python path
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../"))
from agents.polymarket.polymarket import Polymarket

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def main():
    print("="*60)
    print("🧪 GNOSIS SAFE PROXY TRADE VERIFICATION")
    print("="*60)

    # Force cleanup of CLOB credentials to avoid "Invalid base64" errors from potentially malformed .env values
    # We want to rely on the private key to derive credentials if possible, or ensuring we don't use bad static ones
    for key in ["CLOB_API_KEY", "CLOB_SECRET", "CLOB_PASS_PHRASE"]:
        if key in os.environ:
            print(f"   🗑️ Unsetting {key} to force fresh derivation/avoid format errors")
            del os.environ[key]

    # 1. Initialize Polymarket class
    try:
        poly = Polymarket()
        print(f"✅ Polymarket Class Initialized")
        
        # Verify Proxy Address
        proxy_address = poly.funder_address
        signature_type = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "2"))
        print(f"🔐 Configured Proxy Address (Maker): {proxy_address}")
        print(f"📝 Signature Type: {signature_type}")
        
        target_proxy = "0xdb1f88Ab5B531911326788C018D397d352B7265c"
        if proxy_address.lower() != target_proxy.lower():
            print(f"⚠️ WARNING: Configured proxy ({proxy_address}) does not match target ({target_proxy})!")
            sys.exit("Aborted: Proxy Mismatch.")
        
        if signature_type != 2:
            print(f"⚠️ WARNING: Signature Type is {signature_type}, expected 2 (Gnosis Safe)!")
            sys.exit("Aborted: Invalid Signature Type.")

    except Exception as e:
        print(f"❌ Failed to initialize Polymarket: {e}")
        return

    # 2. Deep Discovery
    print("\n📡 Deep Discovery: Querying Tag 1006 (15-Min Crypto)...")
    selected_market = None
    
    # Strategy A: Tag Scan
    try:
        # tag_id 1006 is for 15-Min Crypto
        markets = poly.get_all_markets(limit=50, active=True, closed=False, tag_id=1006)
        print(f"   Received {len(markets)} markets from Tag 1006.")
        
        for market in markets:
            if not market.accepting_orders:
                continue
                
            question = market.question
            print(f"   Checking: {question}")
            
            # For tag 1006, usually all markest are crypto. We just want one that is accepting orders.
            # But let's bias towards 'Bitcoin' or 'Ethereum' just in case
            if "Bitcoin" in question or "Ethereum" in question:
                print(f"   🎯 FOUND MATCH (Tag Strategy): {question}")
                selected_market = market
                break
                
    except Exception as e:
        print(f"⚠️ Tag Search Failed: {e}")

    # Strategy B: Fallback String Search
    if not selected_market:
        print("\n📡 Fallback: Active Search for 'Bitcoin'/'Ethereum' + 'price'...")
        offset = 0
        limit = 100
        max_search = 1000
        
        while offset < max_search:
            try:
                markets = poly.get_all_markets(limit=limit, offset=offset, active=True, closed=False)
                if not markets:
                    break
                    
                for market in markets:
                    if not market.accepting_orders:
                        continue
                    
                    q = market.question
                    # Relaxed logic: Bitcoin OR Ethereum OR price
                    if "Bitcoin" in q or "Ethereum" in q or "price" in q.lower():
                        print(f"   🎯 FOUND MATCH (Fallback Strategy): {q}")
                        selected_market = market
                        break
                
                if selected_market:
                    break
                offset += limit
            except:
                break

    if not selected_market:
        print("❌ No matching market found.")
        return

    # 4. Print Verification
    print(f"\n✅ MATCH CONFIRMED")
    print(f"   Question:      {selected_market.question}")
    print(f"   End Date:      {selected_market.end}")
    print(f"   CLOB TokenIDs: {selected_market.clob_token_ids}")
    
    # 5. Get Fee Rate
    # Parse token IDs to get 'Yes' token (Outcome 0)
    try:
        token_ids = ast.literal_eval(selected_market.clob_token_ids)
        yes_token_id = token_ids[0]
        print(f"   Target Token:  {yes_token_id} (YES Outcome)")
    except Exception as e:
        print(f"❌ Failed to parse token IDs: {e}")
        return

    print(f"\n💰 Fetching Fee Rate for {yes_token_id}...")
    fee_rate_bps = 0
    try:
        fee_url = f"https://clob.polymarket.com/fee-rate?token_id={yes_token_id}"
        fee_resp = requests.get(fee_url).json()
        fee_rate_bps = int(fee_resp.get("feeRateBps", 0))
        print(f"   Fee Rate: {fee_rate_bps} bps")
    except Exception as e:
        print(f"⚠️ Failed to fetch fee rate (defaulting to 0): {e}")

    # 6. Execute Trade
    price = 0.99
    size = 1.1 # 1.1 Shares to ensure > $1 value
    side = "BUY"
    
    print(f"\n💸 EXECUTING TRADE")
    print(f"   Order: BUY {size} Shares @ {price} (Cost: ${price * size:.2f})")
    print(f"   Maker: {proxy_address}")
    print(f"   Fee:   {fee_rate_bps} bps")
    
    try:
        resp = poly.place_limit_order(
            token_id=yes_token_id,
            price=price,
            size=size,
            side=side,
            fee_rate_bps=fee_rate_bps
        )
        
        print("\n📝 RAW JSON RESPONSE:")
        print(json.dumps(resp, indent=2))
        
        # Check for success indicators
        if isinstance(resp, dict):
            status = resp.get("status")
            error = resp.get("error")
            
            if status == "LIVE" or status == "OK" or (resp.get("orderID") and not error):
                print(f"\n✅ SUCCESS: Order placed successfully! 'Platform Bug' disproven.")
            else:
                print(f"\n❌ FAILURE: Order did not return success status.")
        else:
             print(f"\n❌ FAILURE: Unexpected response type.")

    except Exception as e:
        print(f"\n❌ EXCEPTION DURING TRADE: {e}")

if __name__ == "__main__":
    main()
