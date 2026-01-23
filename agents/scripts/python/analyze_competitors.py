
import os
import sys
import time
import requests
import statistics
from datetime import datetime

# Path setup
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.insert(0, PROJECT_ROOT)

from agents.polymarket.polymarket import Polymarket
from agents.polymarket.gamma import GammaMarketClient

def analyze_competitors():
    pm = Polymarket()
    gamma = GammaMarketClient()
    
    # 1. assets to check
    assets = ["solana", "ethereum", "xrp", "bitcoin"]
    
    print("\n🕵️‍♂️ COMPETITOR FORENSICS REPORT 🕵️‍♂️")
    print("="*60)
    
    for asset in assets:
        print(f"\n🔍 ANALYZING {asset.upper()} CLOB...")

        # Use the robust discovery method from Gamma client
        # This finds the exact 15-min markets active right now
        if not hasattr(analyze_competitors, "cached_markets"):
            print("   📡 Fetching fresh market list from Gamma...")
            analyze_competitors.cached_markets = gamma.discover_15min_crypto_markets()
        
        # Filter for the specific asset
        target_market = None
        for m in analyze_competitors.cached_markets:
            # Check title or 'asset' field if available
            # discover_15min_crypto_markets returns dict with 'asset' key (e.g. 'bitcoin', 'solana')
            if m.get('asset') == asset:
                 target_market = m
                 break
        
        if not target_market:
            print(f"   ❌ No active 15-min market found for {asset}")
            continue
            
        print(f"   Market: {target_market['question']}")
        
        # Get Up and Down Tokens
        up_token = target_market.get("clobTokenIds", [])[0] if target_market.get("clobTokenIds") else target_market.get("up_token")
        down_token = target_market.get("clobTokenIds", [])[1] if target_market.get("clobTokenIds") and len(target_market.get("clobTokenIds")) > 1 else target_market.get("down_token")
        
        # Analyze Both Sides
        tokens = {"UP": up_token, "DOWN": down_token}
        
        for side, tid in tokens.items():
            if not tid: continue
            
            print(f"   👉 {side} Token ({tid[:10]}...):")
            
            # A. Order Book Structure
            book = pm.get_orderbook(tid)
            best_bid = float(book.bids[0].price) if book.bids else 0.0
            best_ask = float(book.asks[0].price) if book.asks else 0.0
            spread = best_ask - best_bid
            print(f"      Spread: ${spread:.3f} (${best_bid:.3f} - ${best_ask:.3f})")
            
            # Walls
            bid_wall = sum(float(b.size) for b in book.bids[:3]) if book.bids else 0
            ask_wall = sum(float(a.size) for a in book.asks[:3]) if book.asks else 0
            print(f"      Top 3 Liquidity: Bids ${bid_wall:,.0f} | Asks ${ask_wall:,.0f}")
            
            # B. Trade Velocity (The "Speed" Check)
            # Fetch recent trades
            try:
                # Using standard CLOB endpoint structure guess or pm client
                # PM client doesn't have public trade history exposed easily, trying logic
                trades = pm.client.get_trades(tid) 
                
                if not trades:
                    print("      ⚠️ No recent trades found.")
                    continue
                    
                # Sort by time desc
                # Trade object might be dict or object depending on wrapper
                # Let's assume list of dicts or objects
                recent_trades = trades[:20] 
                
                diffs = []
                last_time = None
                
                # Analyze timestamps
                timestamps = []
                for t in recent_trades:
                    # t might be object with timestamp attribute
                    ts = getattr(t, 'timestamp', 0)
                    if ts == 0: ts = t.get('timestamp', 0)
                    timestamps.append(ts)
                
                if len(timestamps) > 1:
                    for i in range(len(timestamps)-1):
                        diff = abs(timestamps[i] - timestamps[i+1])
                        diffs.append(diff)
                    
                    if diffs:
                        avg_diff = sum(diffs) / len(diffs)
                        # Trades usually in seconds?
                        print(f"      ⚡ Trade Speed: Avg {avg_diff:.2f}s between fills")
                        if avg_diff < 1.0:
                            print("      🚨 HIGH FREQUENCY BOTS DETECTED (Sub-second trading)")
                        elif avg_diff < 5.0:
                             print("      ⚠️ Active Scalpers Present")
                        else:
                             print("      💤 Low Activity")
            except Exception as e:
                print(f"      ❌ Could not fetch trades: {e}")

if __name__ == "__main__":
    analyze_competitors()
