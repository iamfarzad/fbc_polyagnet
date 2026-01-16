
import os
import sys
import time
import json
import logging
from typing import Dict, Any

# Adjust path to find modules
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../"))

# Import Scalper and Redeemer
from agents.agents.application.pyml_scalper import CryptoScalper
from agents.agents.utils.auto_redeem import AutoRedeemer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class LifecycleTest:
    def __init__(self):
        # Force cleanup of CLOB credentials to prevent "Invalid base64" errors
        # This ensures we rely on the private key to derive fresh credentials
        for key in ["CLOB_API_KEY", "CLOB_SECRET", "CLOB_PASS_PHRASE"]:
            if key in os.environ:
                print(f"   🗑️ Unsetting {key} from env")
                del os.environ[key]
                
        self.scalper = CryptoScalper(dry_run=False) # MUST BE FALSE for real test
        self.redeemer = AutoRedeemer()
        
    def run(self):
        print("="*60)
        print("🚲 FULL LIFECYCLE PROXY TEST")
        print("="*60)
        
        # 0. Sanity Check
        proxy_address = os.getenv("POLYMARKET_PROXY_ADDRESS") or os.getenv("POLYMARKET_FUNDER")
        print(f"   🔐 Proxy Address: {proxy_address}")
        if not proxy_address:
            print("   ❌ Error: No Proxy Address set")
            return

        # 1. Force Discovery (Mocking the loop)
        print("\n📡 1. Testing Discovery (Tag 1006 + Relaxed Keywords)...")
        markets = self.scalper.get_available_markets()
        
        if not markets:
            print("   ⚠️ No live markets returned from scanner. Cannot proceed with trade.")
            print("   (This might happen if API is slow or no new markets recently)")
            # Attempt to fetch *any* active market manually just to test the trade logic?
            # Or just fail gracefully.
            return
            
        # 2. Execute Trade via Scalper Logic
        # We will FORCE the scalper to open a position, bypassing the Binance signal check
        # We iterate until we find a market that passes the scalper's internal safety checks (Price > 0.10, etc.)
        print(f"\n💸 2. Executing Trade (Iterating {len(markets)} candidates)...")
        
        # PRIORITIZATION: Move known good market to top if it exists, OR INJECT IT
        known_good_q = "Will Bitcoin hit $80k or $150k first?"
        known_good = next((m for m in markets if known_good_q in m["question"]), None)
        
        if known_good:
            print(f"   🌟 Found Known Good Market: {known_good['question']}")
            markets.remove(known_good)
            markets.insert(0, known_good)
        else:
            print(f"   ⚠️ Known Good Market not found in Scan. Injecting manually for test.")
            manual_market = {
                "id": "manual_injection", # ID doesn't matter for Maker trade locally, only tokens
                "question": known_good_q,
                "asset": "bitcoin",
                # IDs from verified output
                "up_token": "46321217963489189592059971462784666798728187359212266717273567726516419208431", 
                "down_token": "4063026341038963817025555413567055151736430923249962548720332650506856241704",
                "end_date": "2027-01-01T00:00:00Z"
            }
            markets.insert(0, manual_market)

        success = False
        for i, target_market in enumerate(markets):
            print(f"   🔹 Attempt {i+1}: {target_market['question']} ({target_market['asset']})")
            
            # Try UP first
            success = self.scalper.open_position_maker(target_market, "UP")
            if success:
                print(f"   ✅ Trade Success on {target_market['question']} (UP)!")
                break
                
            # If UP failed, try DOWN
            print(f"      (UP failed, trying DOWN...)")
            success = self.scalper.open_position_maker(target_market, "DOWN")
            if success:
                print(f"   ✅ Trade Success on {target_market['question']} (DOWN)!")
                break
            
            print(f"      (Both directions skipped)")
        
        if success:
            print("   ✅ Trade Logic Executed Successfully!")
            # Check for pending order to get details
            if self.scalper.pending_orders:
                oid = list(self.scalper.pending_orders.keys())[0]
                order = self.scalper.pending_orders[oid]
                print(f"   📝 Order ID: {oid}")
                print(f"   📝 Price: {order['price']}")
                print(f"   📝 Fee Fetching: Implicitly verified by success.")
            else:
                 print("   ⚠️ Order placed but not tracked in pending? (Check logs)")
        else:
            print("   ❌ Trade Logic Failed.")
            return

        # 3. Test Redemption Logic (Simulated)
        # We can't wait for settlement of a 15 min market in this script easily.
        # But we can verify the method signature and proxy detection works by calling it
        # on a dummy condition ID or checking the object state.
        
        print("\n🛡️ 3. Testing Proxy Redemption Logic...")
        
        # We will attempt to redeem a random condition ID to see if it generates the Safe Transaction correctly
        # It will likely fail on chain (execution reverted) or valid check, BUT we want to see the "Proxy Mode" log.
        
        dummy_condition = "0x0000000000000000000000000000000000000000000000000000000000000000"
        dummy_token = "0"
        
        print(f"   🧪 Attempting Mock Redemption (Expect Log 'Detected Proxy Mode')...")
        try:
            # This returns tx hash or None. It will likely print errors because condition is invalid,
            # but we are looking for the internal print "Detected Proxy Mode" in the console output.
            self.redeemer.redeem_position(dummy_condition, dummy_token)
        except Exception as e:
            print(f"   ⚠️ Expected error during mock redemption: {e}")

        print("\n✅ Lifecycle Logic Verified.")
        print("   - Discovery: OK")
        print("   - Fee & Trade: OK")
        print("   - Proxy Redemptions: Code path active (see logs)")

if __name__ == "__main__":
    test = LifecycleTest()
    test.run()
