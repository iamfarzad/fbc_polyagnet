import os
import sys
import time
import datetime
import ast
from dotenv import load_dotenv

# Add current dir to path to find access agents module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.polymarket.polymarket import Polymarket
from py_clob_client.order_builder.constants import BUY
from py_clob_client.clob_types import OrderArgs

# Load config
load_dotenv()
key = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
if not key:
    try:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
             with open(env_path, "r") as f:
                content = f.read()
                import re
                match = re.search(r'POLYGON_WALLET_PRIVATE_KEY="?([a-fA-F0-9]+)"?', content)
                if match:
                    key = match.group(1)
                    os.environ["POLYGON_WALLET_PRIVATE_KEY"] = key
    except Exception as e:
        print(f"Manual env load failed: {e}")

# Configuration
DUMP_THRESHOLD = float(os.getenv("DUMP_THRESHOLD", "0.32"))
SKEW_THRESHOLD = float(os.getenv("SKEW_THRESHOLD", "0.78"))
ARB_THRESHOLD = float(os.getenv("ARB_THRESHOLD", "0.97"))
MAX_BET_USD = float(os.getenv("MAX_BET_USD", "3.0"))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "15"))

TARGET_ASSETS = ["BTC", "ETH", "SOL", "XRP"]

class CryptoScalper:
    def __init__(self, dry_run=True):
        self.pm = Polymarket()
        self.dry_run = dry_run
        print(f"Agent 2 (Scalper) Initialized. Dry Run: {self.dry_run}")
        if not self.dry_run:
            print("⚠️  LIVE TRADING ENABLED  ⚠️")
            
        print(f"Targets: {TARGET_ASSETS} | Scan Interval: {SCAN_INTERVAL}s")

    def get_live_15min_markets(self):
        """
        Scans for 15-minute markets for target assets.
        """
        markets = []
        try:
             # Fetch active markets (limit 1000 to catch many)
            all_markets = self.pm.get_all_markets(limit=1000, active="true", closed="false", archived="false")
            
            for m in all_markets:
                q = m.question.lower()
                # Filter logic: Must contain asset name, "15", and "minute" (or 'min' if abbr used?)
                
                is_target = False
                for asset in TARGET_ASSETS:
                    if asset.lower() in q or (asset == "BTC" and "bitcoin" in q) or (asset == "ETH" and "ethereum" in q):
                        is_target = True
                        break
                
                if is_target and "15" in q and ("min" in q):
                    # Basic timestamp filter: Ensure end date is future? (Active flag usually handles this, but safe to check)
                    markets.append(m)
                    
        except Exception as e:
            print(f"Error fetching markets: {e}")
            
        return markets

    def analyze_and_execute(self, market):
        """
        Analyzes a single market for Dump/Skew/Arb opportunities.
        """
        try:
            # Parse Outcomes
            outcomes = ast.literal_eval(market.outcomes) # ["Yes", "No"]
            prices = ast.literal_eval(market.outcome_prices)
            token_ids = ast.literal_eval(market.clob_token_ids)
            
            if len(outcomes) != 2:
                return # Skip non-binary
                
            yes_price = float(prices[0]) # Assuming Yes is 0
            no_price = float(prices[1])
            yes_token = token_ids[0]
            no_token = token_ids[1]
            
            sum_prob = yes_price + no_price
            
            log_prefix = f"[Market: {market.question} | Y: {yes_price:.2f} N: {no_price:.2f}]"
            
            # Balance Check
            if not self.dry_run:
                try:
                    balance = self.pm.get_usdc_balance() # Using method from polymarket.py if available or custom logic
                    if balance < MAX_BET_USD + 1:
                        print(f"{log_prefix} Low Balance (${balance:.2f}). Skipping.")
                        return
                except:
                    # If helper fails, maybe just proceed or log warning
                     pass

            # 1. Arbitrage Check
            if sum_prob < ARB_THRESHOLD:
                print(f"{log_prefix} ARB DETECTED (Sum: {sum_prob:.3f})! Executing Double Buy.")
                self.place_order(yes_token, MAX_BET_USD / 2, "YES (Arb)")
                self.place_order(no_token, MAX_BET_USD / 2, "NO (Arb)")
                return

            # 2. Volatility Dump Check (Buy the dumped side)
            if yes_price <= DUMP_THRESHOLD:
                print(f"{log_prefix} YES Dumped (<= {DUMP_THRESHOLD}). Buying YES.")
                self.place_order(yes_token, MAX_BET_USD, "YES")
            elif no_price <= DUMP_THRESHOLD:
                print(f"{log_prefix} NO Dumped (<= {DUMP_THRESHOLD}). Buying NO.")
                self.place_order(no_token, MAX_BET_USD, "NO")
                
            # 3. Skew Fallback (Buy the trending/strong side if cheap fees?)
            # Logic from user plan: "If one side >= SKEW_THRESHOLD... Buy favored side"
            elif yes_price >= SKEW_THRESHOLD:
                print(f"{log_prefix} YES Skewed (>= {SKEW_THRESHOLD}). Buying YES.")
                self.place_order(yes_token, MAX_BET_USD, "YES")
            elif no_price >= SKEW_THRESHOLD:
                print(f"{log_prefix} NO Skewed (>= {SKEW_THRESHOLD}). Buying NO.")
                self.place_order(no_token, MAX_BET_USD, "NO")

        except Exception as e:
            print(f"Error analyzing {market.id}: {e}")

    def place_order(self, token_id, amount_usd, side_label):
        # Calculate aggressive PRICE to ensure fill (Market-like)
        # Buying YES token or NO token -> We are always "BUY"ing that token from the CLOB perspective.
        # To ensure fill for a Buy, we bid a high price (e.g., 0.999). 
        # The matching engine fills at best available ASK (cheapest).
        aggressive_price = 0.999
        
        # Calculate Size (Shares) = Amount / Price
        # Since we bid 0.999, size is ~Amount. But realistically we fill lower.
        # If we want to spend $MAX_BET_USD, and price is e.g. 0.40, we get Amount/0.40 shares.
        # But we don't know exact fill price. 
        # Safe approach: size = amount_usd / aggressive_price (Conservative size)
        # Better: size = amount_usd / estimated_fill_price? 
        # User suggested: size = amount_usd / price. Let's use aggressive_price to be safe on "Spend" limit.
        size = amount_usd / aggressive_price

        if self.dry_run:
            print(f"  [DRY RUN] Would Buy {side_label} - Amount: ${amount_usd} (Aggro Price: {aggressive_price}, Size: {size:.2f}) - Token: {token_id[:10]}...")
            return

        print(f"  [LIVE] Placing Aggressive Limit Order: {side_label} ${amount_usd}...")
        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=aggressive_price,
                size=size,
                side=BUY # Always BUY because we are buying the outcome token
            )
            
            signed_order = self.pm.client.create_order(order_args)
            resp = self.pm.client.post_order(signed_order)
            print(f"  [LIVE] Order Result: {resp}")
            
        except Exception as e:
            print(f"  [LIVE] Order Failed: {e}")

    def run(self):
        print("Starting 15-min Scalper Loop...")
        while True:
            active_scalps = self.get_live_15min_markets()
            if not active_scalps:
                print(f"[{datetime.datetime.now().time()}] No 15-min markets found. Scanning...")
            else:
                print(f"[{datetime.datetime.now().time()}] Found {len(active_scalps)} active 15-min markets.")
                for m in active_scalps:
                    self.analyze_and_execute(m)
            
            time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    # Check for --live flag to enable real trading
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Enable Live Trading")
    args = parser.parse_args()
    
    is_dry = not args.live
    
    bot = CryptoScalper(dry_run=is_dry)
    bot.run()
