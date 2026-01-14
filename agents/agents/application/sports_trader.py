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
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
MIN_BET_USD = 1.00
MAX_BET_USD = 50.00
BET_PERCENT = 0.15 # 15% of bankroll per bet (aggressive but moderated by Kelly/Edge if needed)

# Sports Config Mapping (Readable -> API Key)
SPORTS_CONFIG = {
    "NBA": {"key": "basketball_nba", "market_type": "h2h"},
    "NFL": {"key": "americanfootball_nfl", "market_type": "h2h"},
    "NHL": {"key": "icehockey_nhl", "market_type": "h2h"},
    "EPL": {"key": "soccer_epl", "market_type": "h2h"},
    "La Liga": {"key": "soccer_spain_la_liga", "market_type": "h2h"},
    "MLS": {"key": "soccer_usa_mls", "market_type": "h2h"},
    "Tennis": {"key": "tennis_atp_aus_open_singles", "market_type": "h2h"}
}

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
        print(f"🏟️ UNIVERSAL SPORTS TRADER - Math + Contrarian Check")
        print(f"="*60)
        print(f"Mode: {'DRY RUN' if dry_run else '🔴 LIVE'}")
        print(f"Odds API Key: {'✅ Found' if ODDS_API_KEY else '❌ Missing'}")
        if ODDS_API_KEY:
            print(f"   Key format: {ODDS_API_KEY[:4]}...{ODDS_API_KEY[-4:]} (len={len(ODDS_API_KEY)})")
        print(f"Balance: ${self.balance:.2f}")

    def get_fair_odds(self, sport_code: str, region="us") -> List[Dict]:
        """Fetch odds from The Odds API and calculate no-vig probability."""
        if not ODDS_API_KEY:
            return []
            
        url = f"https://api.the-odds-api.com/v4/sports/{sport_code}/odds/?apiKey={ODDS_API_KEY}&regions={region}&markets=h2h&oddsFormat=american"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                print(f"   ⚠️ Odds API Error: {resp.status_code}")
                try:
                    print(f"   Response: {resp.text[:200]}")
                except: pass
                return []
            
            games_data = resp.json()
            analyzed_games = []

            for game in games_data:
                # Use DraftKings, FanDuel, or Pinnacle as sharp anchors
                bookie = next((b for b in game['bookmakers'] if b['key'] in ['draftkings', 'fanduel', 'pinnacle']), None)
                if not bookie and game['bookmakers']:
                    bookie = game['bookmakers'][0] # Fallback
                
                if not bookie: continue

                outcomes = bookie['markets'][0]['outcomes']
                
                # Calculate Implied Probabilities (with Vig)
                probs = []
                for outcome in outcomes:
                    price = outcome['price'] # American Odds
                    if price < 0: prob = abs(price) / (abs(price) + 100)
                    else: prob = 100 / (price + 100)
                    probs.append({"name": outcome['name'], "prob": prob, "price_american": price})
                
                # Remove Vig (Normalize to 100%)
                total_implied = sum(p['prob'] for p in probs)
                for p in probs:
                    p['fair_prob'] = p['prob'] / total_implied
                    p['fair_price'] = p['fair_prob'] # 0.0-1.0
                
                analyzed_games.append({
                    "matchup": f"{game['away_team']} vs {game['home_team']}",
                    "start_time": game['commence_time'],
                    "outcomes": probs
                })
            return analyzed_games
            
        except Exception as e:
            print(f"   Error fetching odds: {e}")
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

    def run_universal_bot(self, sport_name: str):
        config = SPORTS_CONFIG.get(sport_name)
        if not config: return

        print(f"\n🌍 SCANNING: {sport_name}...")
        
        # 1. Fetch Mathematical Fair Price
        games = self.get_fair_odds(config['key'])
        if not games:
            print("   No games found.")
            return

        for game in games:
            # Identify Favorite
            favorite = max(game['outcomes'], key=lambda x: x['fair_prob'])
            
            # FILTER 1: Only bet on Favorites > 60% (Value plays)
            if favorite['fair_prob'] < 0.60: continue
            
            # FILTER 2: Check Edge (Is Polymarket Cheaper?)
            # We assume Polymarket is ~5 cents cheaper to make it worth checking injuries
            target_price = favorite['fair_prob'] - 0.05 
            
            print(f"   🔎 Potential: {favorite['name']} (True: {favorite['fair_prob']*100:.1f}%)")

            # 3. Contrarian Check (Perplexity)
            # Only pay for AI call if Math is good
            synthetic_q = f"Will {favorite['name']} win {game['matchup']}?"
            
            try:
                # Reduced timeout to prevents hanging on one game
                is_valid, reason, conf = self.validator.validate(
                    market_question=synthetic_q,
                    outcome="YES",
                    price=target_price, 
                    system_prompt=RISK_MANAGER_PROMPT
                )
            except Exception as e:
                print(f"      ⚠️ Validator Error/Timeout: {e}")
                continue # Skip this game and move to the next one
            
            if is_valid:
                print(f"      ✅ GREEN LIGHT: {reason}")
                # 4. Find Market & Execute
                # Extract clean team names from "Away vs Home" string
                try:
                    away, home = game['matchup'].split(' vs ')
                except:
                    continue # Skip if format is weird
                    
                market = self.find_polymarket_match(
                    home, 
                    away, 
                    config
                )
                if market:
                    self.execute_bet(market, "YES", size=10.0, price=target_price)
                else:
                    print(f"      ⚠️ No matching Polymarket found for {game['matchup']}")
            else:
                print(f"      🛑 PASS: {reason}")

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
        print("🤖 AUTO-TRADER STARTED")
        while True:
            # 0. Sync State
            if HAS_SUPABASE:
                try: 
                    supa = get_supabase_state()
                    if supa and not supa.is_agent_running("sport"): # Assuming 'sport' key
                        print("Paused via Supabase.")
                        time.sleep(60)
                        continue
                except: pass

            # 1. Auto-Redeem
            if self.redeemer:
                try: self.redeemer.scan_and_redeem()
                except: pass
            
            # 2. Loop Sports
            for sport in SPORTS_CONFIG.keys():
                try:
                    self.run_universal_bot(sport)
                    time.sleep(2) # Be nice to API
                except Exception as e:
                    print(f"Error in {sport}: {e}")
            
            self.save_state()
            print("\n⏳ Sleeping 1 hour...")
            time.sleep(3600)

if __name__ == "__main__":
    is_live = "--live" in sys.argv
    bot = SportsTrader(dry_run=not is_live)
    bot.run()
