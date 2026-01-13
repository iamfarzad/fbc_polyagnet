
import sys
import os
import json
import logging
import requests

# Add agents directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set up logging
logging.basicConfig(level=logging.INFO)

from agents.application.sports_trader import SportsTrader

def test_pipeline():
    print("\n" + "="*60)
    print("🏟️ DIAGNOSTIC MODE: Sports Trader Pipeline")
    print("="*60)
    
    trader = SportsTrader(dry_run=True)
    
    # 1. Test Odds API
    print("\n📊 Step 1: Testing The Odds API (NBA)...")
    try:
        games = trader.get_fair_odds("basketball_nba")
        print(f"   Success! Found {len(games)} NBA games.")
        
        if games:
            print("\n   --- Sample Game from Odds API ---")
            game = games[0]
            print(f"   Matchup: {game['matchup']}")
            print(f"   Start: {game['start_time']}")
            print(f"   Outcomes: {json.dumps(game['outcomes'], indent=2)}")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        games = []

    # 2. Test Polymarket Search by Team
    print("\n🛒 Step 2: Searching Polymarket for 'Phoenix Suns'...")
    try:
        # Search via 'q' param if supported, or filter client side
        # trying simple search endpoint if it exists, or just markets with query
        # Polymarket Gamma API doesn't document 'q' clearly, let's try 'question' filter or just fetching many
        
        # Try fetching events with a search query? 
        # Actually, let's try active markets and filter locally, but increase limit
        print("   Fetching 100 active markets to look for match...")
        url = "https://gamma-api.polymarket.com/markets"
        params = {
            "limit": 50, # Polymarket limit
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
        }
        resp = requests.get(url, params=params).json()
        
        found = []
        for m in resp:
            q_text = m.get("question", "").lower()
            if "suns" in q_text or "heat" in q_text:
                found.append(m)
                
        print(f"   Matches found in top 50 volume: {len(found)}")
        for m in found:
             print(f"   ✅ FOUND: {m.get('question')} (ID: {m.get('id')})")
        
        # If not found in volume, try text search endpoint if known... 
        # Let's try to query events instead, events usually have the game title
        print("\n   Searching EVENTS for 'Suns'...")
        url_events = "https://gamma-api.polymarket.com/events"
        params_evt = {
            "limit": 20,
            "active": "true",
            "closed": "false",
            "slug": "nba" # Try to filter by slug content? No, listing events is better
        }
        # Gamma API allows filtering by tag_id. NBA is likely a specific ID.
        # Let's try raw fetch of events and grep
        resp_ev = requests.get(url_events, params={"limit": 50, "active": "true"}).json()
        for e in resp_ev:
            title = e.get("title", "")
            if "Suns" in title or "Heat" in title:
                print(f"   ✅ EVENT FOUND: {title} (ID: {e.get('id')})")
                print(f"      Markets inside: {len(e.get('markets', []))}")
                if e.get('markets'):
                     print(f"      Sample Market: {e['markets'][0]['question']}")

    except Exception as e:
        print(f"   ❌ FAILED: {e}")

if __name__ == "__main__":
    test_pipeline()
