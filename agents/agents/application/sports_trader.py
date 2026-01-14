"""
Universal Sports Trader - Math + Intelligence 🏀⚽️
Uses The Odds API for Fair Price & Perplexity for Risk Management.
"""
import os
import sys
import time
import json
import requests
import datetime
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv

# Add parent paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.polymarket.polymarket import Polymarket
from agents.utils.validator import Validator, SharedConfig
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY
from agents.utils.context import get_context, Position, Trade

# Try to import auto-redeemer
try:
    from agents.utils.auto_redeem import AutoRedeemer
    HAS_REDEEMER = True
except ImportError:
    HAS_REDEEMER = False
    AutoRedeemer = None

# Import Supabase state manager
try:
    from agents.utils.supabase_client import get_supabase_state
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    get_supabase_state = None

load_dotenv()

# --- CONFIGURATION ---
MIN_BET_USD = 1.00
MAX_BET_USD = 50.00
BET_PERCENT = 0.15 # 15% of bankroll per bet
MIN_CONFIDENCE = 0.65  # LLM must be 65%+ confident to trade
SCAN_INTERVAL = 300    # 5 minutes between scans (was 1 hour!)

# Polymarket Sports Series IDs (for direct Gamma API)
SPORTS_SERIES = {
    "NBA": 10345,
    "NFL": 10346,
    "NHL": 10348,
    "Soccer": 10347,  # General soccer
    "Tennis": 10349,
}

# Tag ID for game-specific bets (not futures)
GAME_TAG_ID = 100639

# --- CONTRARIAN SYSTEM PROMPT ---
RISK_MANAGER_PROMPT = """You are a contrarian sports bettor and risk manager.
Your GOAL is to find reasons NOT to bet on the favorite.

For the requested matchup, perform these specific checks:
1. INJURY SEARCH: Search explicitly for "[Team Name] injury report today". If a Star Player is "Out" or "Questionable", DEDUCT 15% from their win probability immediately.
2. SCHEDULE SPOT: Check if the favorite is on a "back-to-back" or playing their 3rd game in 4 nights. If yes, this is a "Trap Game".
3. MOMENTUM CHECK: Search for "last 5 games record". If the Favorite has lost 3+ of last 5, they are "Cold".

OUTPUT "PASS" IF:
- A key player is injured for the favorite.
- The favorite is on a losing streak (3+ losses).
- The team is tired (Back-to-back).

Only recommend "BET" if the team is healthy, rested, and in form."""

class SportsTrader:
    AGENT_NAME = "sports_trader"

    def __init__(self, dry_run=True):
        self.dry_run = dry_run
        self.pm = Polymarket()
        self.validator = Validator(SharedConfig(), agent_name=self.AGENT_NAME)
        self.context = get_context()
        
        # State
        self.positions = {}
        self.trades_made = 0
        self.total_invested = 0.0
        
        # Balance
        try:
            self.balance = self.pm.get_usdc_balance()
        except:
            self.balance = 0
        
        # Auto-Redeemer
        self.redeemer = AutoRedeemer() if HAS_REDEEMER else None

        print(f"="*60)
        print(f"🏟️ SPORTS TRADER - Direct Polymarket Mode")
        print(f"="*60)
        print(f"Mode: {'DRY RUN' if dry_run else '🔴 LIVE'}")
        print(f"Data Source: Polymarket Gamma API (NO external API needed)")
        print(f"Scan Interval: {SCAN_INTERVAL}s ({SCAN_INTERVAL//60} mins)")
        print(f"Balance: ${self.balance:.2f}")

    def get_live_polymarket_sports(self, series_id: int = None) -> List[Dict]:
        """
        Fetch LIVE sports markets directly from Polymarket Gamma API.
        No external API needed - sees exactly what's on polymarket.com/sports/live
        """
        try:
            # Build URL with optional series filter
            base_url = "https://gamma-api.polymarket.com/events"
            params = {
                "active": "true",
                "closed": "false",
                "tag_id": GAME_TAG_ID,  # 100639 = game-specific bets
                "limit": 50,
            }
            if series_id:
                params["series_id"] = series_id
            
            resp = requests.get(base_url, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"   ⚠️ Gamma API Error: {resp.status_code}")
                return []
            
            events = resp.json()
            markets = []
            
            for event in events:
                # Get the markets within this event
                event_markets = event.get("markets", [])
                if not event_markets:
                    continue
                
                for m in event_markets:
                    # Parse token IDs
                    clob_ids = m.get("clobTokenIds", "[]")
                    try:
                        import ast
                        tokens = ast.literal_eval(clob_ids) if isinstance(clob_ids, str) else clob_ids
                        if len(tokens) < 2:
                            continue
                    except:
                        continue
                    
                    # Parse prices
                    outcomes = m.get("outcomePrices", "[0.5, 0.5]")
                    if isinstance(outcomes, str):
                        outcomes = ast.literal_eval(outcomes)
                    
                    yes_price = float(outcomes[0]) if outcomes else 0.5
                    no_price = float(outcomes[1]) if len(outcomes) > 1 else 1 - yes_price
                    
                    markets.append({
                        "id": m.get("id"),
                        "question": m.get("question", event.get("title", "")),
                        "event_title": event.get("title", ""),
                        "yes_token": tokens[0],
                        "no_token": tokens[1],
                        "yes_price": yes_price,
                        "no_price": no_price,
                        "volume": float(m.get("volume24hr", 0) or 0),
                        "liquidity": float(m.get("liquidity", 0) or 0),
                        "end_date": m.get("endDate", ""),
                        "slug": m.get("slug", ""),
                    })
            
            return markets
            
        except Exception as e:
            print(f"   Error fetching Polymarket sports: {e}")
            return []

    def find_polymarket_match(self, home_team: str, away_team: str, sport_config: dict) -> Optional[Dict]:
        """
        Finds the correct Polymarket Event ID using fuzzy matching (difflib).
        """
        import difflib
        
        # 1. Fetch active events from Polymarket Gamma API
        url = "https://gamma-api.polymarket.com/events?closed=false&limit=100&active=true" 
        try:
            # In a real production app, we should cache this response to avoid hitting rate limits
            response = requests.get(url, timeout=10).json()
        except Exception as e:
            print(f"      ⚠️ Error fetching Polymarket events: {e}")
            return None

        # 2. Filter for the right sport
        #    We look for keywords in the event title (e.g. "NBA", "Celtics")
        #    We can use the teams themselves as keywords
        relevant_events = []
        for e in response:
            title = e.get('title', '')
            # Check if either team name is in the title
            if home_team in title or away_team in title:
                relevant_events.append(e)
            # Or if the sport key is in the title (simplified)
            elif sport_config.get('key').split('_')[-1].upper() in title: 
                 relevant_events.append(e)

        if not relevant_events:
            return None

        # 3. Create a search string for our game
        #Standard Polymarket format is often "Team A vs Team B" or "Will Team A beat Team B?"
        my_game_str = f"{away_team} vs {home_team}"
        
        # 4. Fuzzy Match using difflib
        best_match = None
        best_score = 0.0
        
        for e in relevant_events:
            title = e.get('title', '')
            # Compare my_game_str to the title
            ratio = difflib.SequenceMatcher(None, my_game_str.lower(), title.lower()).ratio()
            
            # Also check reversed order just in case
            my_game_str_rev = f"{home_team} vs {away_team}"
            ratio_rev = difflib.SequenceMatcher(None, my_game_str_rev.lower(), title.lower()).ratio()
            
            score = max(ratio, ratio_rev)
            
            if score > best_score:
                best_score = score
                best_match = e
        
        if best_score > 0.6: # Confidence threshold (lower than 85 because titles vary wildy)
            print(f"      🔗 Linked: '{my_game_str}' ↔ '{best_match['title']}' (Score: {best_score:.2f})")
            # We need to find the specific Market ID for the "Moneyline" or "Winner" market within this event
            # This is tricky because an event has multiple markets. 
            # We look for the market Question that looks like "Winner?" or matches the teams.
            if 'markets' in best_match:
                # Try to find the main market
                return best_match['markets'][0] # MVP: Return the first market (usually the main one)
            
            return {"id": best_match['id'], "question": best_match['title']} # Fallback
            
        return None

    def execute_bet(self, market: Dict, side: str, size: float, price: float):
        """Execute trade on Polymarket with real CLOB integration."""
        question = market.get('question', 'Unknown Sports Market')
        market_id = market.get('id')
        
        # Identify token (assuming 'YES' for favorites based on your strategy)
        # Note: You'll need to ensure the market dict contains 'yes_token' or 'clobTokenIds'
        token_id = market.get('yes_token') or market.get('clobTokenIds', [None, None])[0]
        
        if not token_id:
            print(f"      ❌ Failed to execute: No Token ID found for {question}")
            return

        print(f"      💰 EXECUTING: {side} on '{question}' @ {price:.2f} (Amt: ${size:.2f})")
        
        if self.dry_run:
            print(f"      [DRY RUN] Trade logged.")
            self.trades_made += 1
            return

        try:
            order_args = OrderArgs(
                token_id=str(token_id),
                price=round(price + 0.01, 2), # Add 1c buffer for sports fills
                size=size / price,
                side=BUY
            )
            
            signed = self.pm.client.create_order(order_args)
            result = self.pm.client.post_order(signed)
            
            if result.get("success") or result.get("status") == "matched":
                print(f"      ✅ LIVE ORDER FILLED!")
                self.trades_made += 1
                self.total_invested += size
                
                # Record in Shared Context
                self.context.add_position(Position(
                    market_id=market_id,
                    market_question=question,
                    agent=self.AGENT_NAME,
                    outcome=side,
                    entry_price=price,
                    size_usd=size,
                    timestamp=datetime.datetime.now().isoformat(),
                    token_id=token_id
                ))
            else:
                print(f"      ⚠️ Order failed: {result.get('status')}")
                
        except Exception as e:
            print(f"      ❌ Execution Error: {e}")

    def scan_live_markets(self):
        """
        Scan live Polymarket sports directly using Gamma API.
        No external API needed - trades based on what's actually live.
        """
        print(f"\n🌍 SCANNING POLYMARKET LIVE SPORTS...")
        
        # Fetch all live sports markets
        markets = self.get_live_polymarket_sports()
        
        if not markets:
            print("   No live sports markets found.")
            return
        
        print(f"   📡 Found {len(markets)} live markets")
        
        for market in markets:
            question = market.get("question", "")
            yes_price = market.get("yes_price", 0.5)
            no_price = market.get("no_price", 0.5)
            
            # FILTER 1: Must have a clear favorite (>55% implied)
            if yes_price < 0.55 and no_price < 0.55:
                continue  # Too close to 50/50
            
            # Determine which side is favorite
            if yes_price >= no_price:
                favorite_side = "YES"
                favorite_price = yes_price
                token_id = market.get("yes_token")
            else:
                favorite_side = "NO"
                favorite_price = no_price
                token_id = market.get("no_token")
            
            # FILTER 2: Skip very high prices (>90c, low upside)
            if favorite_price > 0.90:
                continue
            
            print(f"\n   🔎 Analyzing: {question[:60]}...")
            print(f"      Market: {favorite_side} @ ${favorite_price:.2f}")
            
            # 3. LLM Validation (Perplexity/Gemini)
            try:
                is_valid, reason, conf = self.validator.validate(
                    market_question=question,
                    outcome=favorite_side,
                    price=favorite_price,
                    system_prompt=RISK_MANAGER_PROMPT
                )
            except Exception as e:
                print(f"      ⚠️ Validator Error: {e}")
                continue
            
            if is_valid and conf >= MIN_CONFIDENCE:
                print(f"      ✅ GREEN LIGHT: {reason} (conf: {conf*100:.0f}%)")
                
                # Calculate bet size
                bet_size = min(MAX_BET_USD, max(MIN_BET_USD, self.balance * BET_PERCENT))
                if self.balance < MIN_BET_USD:
                    print(f"      💸 Insufficient balance: ${self.balance:.2f}")
                    continue
                
                # Execute trade
                self.execute_bet(market, favorite_side, size=bet_size, price=favorite_price + 0.01)
            else:
                print(f"      🛑 PASS: {reason} (conf: {conf*100:.0f}%)")

    def save_state(self):
        """Save state to json."""
        try:
            state = {
                "sports_trader_last_activity": f"Trades: {self.trades_made}",
                "sports_trader_mode": "DRY RUN" if self.dry_run else "LIVE",
                "timestamp": datetime.datetime.now().isoformat()
            }
            with open("bot_state.json", "w") as f:
                json.dump(state, f)
        except: pass

    def run(self):
        print("🤖 SPORTS TRADER STARTED - Direct Polymarket Mode")
        while True:
            # 0. Sync State with Supabase
            if HAS_SUPABASE:
                try: 
                    supa = get_supabase_state()
                    if supa and not supa.is_agent_running("sport"):
                        print("Paused via Supabase.")
                        time.sleep(60)
                        continue
                except: pass

            # 1. Auto-Redeem winning positions
            if self.redeemer:
                try: self.redeemer.scan_and_redeem()
                except: pass
            
            # 2. Refresh balance
            try:
                self.balance = self.pm.get_usdc_balance()
            except: pass
            
            # 3. Scan live markets directly from Polymarket
            try:
                self.scan_live_markets()
            except Exception as e:
                print(f"Error scanning markets: {e}")
            
            self.save_state()
            print(f"\n⏳ Next scan in {SCAN_INTERVAL//60} minutes...")
            time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    is_live = "--live" in sys.argv
    bot = SportsTrader(dry_run=not is_live)
    bot.run()
