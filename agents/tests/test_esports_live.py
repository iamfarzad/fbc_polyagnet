
import sys
import os
import json
import logging
import requests

# Add agents directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestEsports")

from agents.application.esports_trader import EsportsTrader, EsportsDataAggregator, PolymarketEsports

def test_pipeline():
    print("\n" + "="*60)
    print("🎮 DIAGNOSTIC MODE: Esports Trader Pipeline")
    print("="*60)
    
    # 1. Test Aggregator / PandaScore
    print("\n📡 Step 1: Testing Data Aggregator (PandaScore)...")
    try:
        agg = EsportsDataAggregator()
        matches = agg.get_all_live_matches()
        print(f"   Success! Found {len(matches)} live matches.")
        for m in matches:
            print(f"   - [{m.get('game_type')}] {m.get('status')}: {json.dumps(m.get('opponents', []), default=str)[:100]}...")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        matches = []

    # 2. Test Polymarket Fetch
    print("\n🛒 Step 2: Testing Polymarket Fetch...")
    try:
        # Manually fetch to debug filtering
        url = "https://gamma-api.polymarket.com/markets"
        params = {
            "limit": 50,
            "active": "true",
            "closed": "false",
            "order": "volume24hr", # Changed to volume to see popular ones
            "ascending": "false",
        }
        resp = requests.get(url, params=params).json()
        print(f"   Raw API returned {len(resp)} markets (sorted by volume).")
        
        esports_slug_prefixes = ("cs2-", "csgo-", "lol-", "dota-", "valorant-")
        found_esports = []
        
        print("\n   --- Top 10 Markets Checked ---")
        for i, m in enumerate(resp[:10]):
            slug = m.get("slug", "")
            is_esport = slug.startswith(esports_slug_prefixes)
            prefix = "✅" if is_esport else "❌"
            print(f"   {prefix} [{slug[:30]}...] {m.get('question')[:50]}...")
            if is_esport:
                found_esports.append(m)

        print(f"\n   Total Esports Markets found in top 50: {len(found_esports)}")
        markets = found_esports  # Assign for step 3 usage
        
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        markets = []

    # 3. Test Matching Logic
    print("\n🔗 Step 3: Testing Matching Logic...")
    trader = EsportsTrader(dry_run=True)
    
    if not matches:
        print("   ⚠️ No live matches to match against.")
    elif not markets:
        print("   ⚠️ No markets to match against.")
    else:
        matched_count = 0
        for market in markets:
            match = trader.match_market_to_live_game(market, matches)
            if match:
                matched_count += 1
                print(f"   ✅ MATCH FOUND: {market.question}")
                print(f"      Mapped to: {match.get('id')}")
        
        if matched_count == 0:
            print("   ⚠️ 0 matches found between Polymarket (Markets) and PandaScore (Live Games).")
            print("      Possible reasons: Team name mismatch, game not live, or API lag.")

if __name__ == "__main__":
    test_pipeline()
