import os
import sys
import time
import requests
import json
import datetime
from dateutil import parser

# Add agent root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))

from agents.agents.application.pyml_scalper import CryptoScalper
from agents.agents.utils.auto_redeem import AutoRedeemer
from agents.polymarket.gamma import GammaMarketClient

# Configure Proxy
PROXY_ADDRESS = "0xdb1f88Ab5B531911326788C018D397d352B7265c"
os.environ["POLYMARKET_PROXY_ADDRESS"] = PROXY_ADDRESS

# Clean bad credentials just in case
for k in ["CLOB_API_KEY", "CLOB_SECRET", "CLOB_PASS_PHRASE"]:
    if k in os.environ: del os.environ[k]

def test_lifecycle():
    print("🧪 STARTING REAL LIFECYCLE TEST (Strict 15-Min Strategy)")
    
    # 1. Initialize Agents
    print("   🤖 Initializing Scalper & Redeemer...")
    scalper = CryptoScalper() # This should pick up the Proxy config
    redeemer = AutoRedeemer()
    
    # Verify Proxy Config via Scalper's Polymarket instance
    funder = scalper.pm.funder_address
    print(f"   🔐 Scalper Funder: {funder}")
    if funder.lower() != PROXY_ADDRESS.lower():
        print(f"   ❌ ERROR: Scalper not using Proxy! Got {funder}")
        return

    # 2. Discovery (Using Strict Logic)
    print("\n🔍 1. Running Discovery (get_available_markets)...")
    markets = scalper.get_available_markets()

    if not markets:
        print("   ⚠️ No 15-min markets found. INJECTING FALLBACK MARKET for verification...")
        # Fallback: Find ANY active crypto market
        found = False
        # Using gamma client directly for search
        gamma_client = GammaMarketClient()
        gamma_mkts = gamma_client.get_current_markets(limit=50) # Increase limit to find bitcoin
        print(f"   ℹ️ Fallback Scanned {len(gamma_mkts)} markets.")
        
        for i, m in enumerate(gamma_mkts):
             if i < 5: print(f"   Debug Msg: {m['question']}")
             # Look for a simple binary market, preferably crypto
             if "bitcoin" in m["question"].lower() and not m["closed"]:
                 clob_ids = json.loads(m["clobTokenIds"])
                 target_market = {
                    "id": m["id"],
                    "question": m["question"],
                    "asset": "bitcoin",
                    "up_token": clob_ids[0],
                    "down_token": clob_ids[1],
                    "end_date": m["endDate"],
                    "created_at": m["createdAt"]
                 }
                 markets = [target_market]
                 print(f"   💉 Injected Fallback: {m['question']}")
                 found = True
                 break
        
        if not found:
             print("   ❌ Could not find any fallback Bitcoin/Crypto market for verification.")
             return

    # Force LIVE MODE for the test
    scalper.dry_run = False
    print("   🔴 LIVE MODE ENABLED for Single Trade Verification")

    target_market = markets[0]
    print(f"   🎯 Target Selected: {target_market['question']}")
    
    # 3. Execute Trade (Force Entry via Scalper Logic)
    print("\n💸 2. Executing Trade (Buy UP)...")
    # We call open_position_maker directly. 
    # It checks balance, correlation, price, FEE, and places order.
    # It returns True/False.
    
    success = scalper.open_position_maker(target_market, "UP")
    
    if success:
        print("   ✅ Trade Logic Executed Successfully!")
        # We need to find the order ID / Hash to report? 
        # Scalper logs to self.pending_orders or output.
        print("   (Check console output for Order ID and Fee usage)")
    else:
        print("   ❌ Trade Logic Failed (Check Scalper logs above)")
        return

    # 4. Wait & Redeem
    print("\n⏳ 3. Redemption Check...")
    end_date_str = target_market["end_date"]
    end_date = parser.parse(end_date_str)
    if end_date.tzinfo is None: end_date = end_date.replace(tzinfo=datetime.timezone.utc)
    
    now = datetime.datetime.now(datetime.timezone.utc)
    wait_s = (end_date - now).total_seconds()
    
    if wait_s > 900: # 15 mins
        print(f"   ⚠️ Market ends in {wait_s/60:.1f} mins. Too long to wait script.")
    else:
        print(f"   WAITING {wait_s:.1f}s for market to resolve...")
        time.sleep(wait_s + 60) # Wait for resolution
        
        print("   🔓 Attempting Proxy Redemption...")
        # redeemer.redeem_positions() runs a loop. 
        # We can call it, it checks for unresolved positions.
        redeemer.redeem_positions() 
        # If successful, it prints tx hash.

if __name__ == "__main__":
    test_lifecycle()
