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

    def find_polymarket_match(self, game_matchup: str, sport: str) -> Optional[Dict]:
        """Fuzzy match TheOddsAPI game to a Polymarket market."""
        # This is complex because naming differs (Lakers vs Celtics vs Los Angeles Lakers vs Boston Celtics)
        # Simplified approach: Search for team names in Polymarket events
        # For now, we return None as a placeholder for the integration logic
        # In a real run, we would query `gamma-api.polymarket.com/events` with a search term
        
        # NOTE: For MVP, we will try to find markets by searching for the "Favorite's Name" 
        # inside the `Polymarket` class or via API search.
        return None 
        # TODO: Implement robust string matching or use an existing helper

    def execute_bet(self, market: Dict, side: str, size: float, price: float):
        """Execute trade on Polymarket."""
        if self.dry_run:
            print(f"   [DRY RUN] Buying ${size:.2f} of {side} @ {price:.2f}")
            self.trades_made += 1
            return
        
        # Real trade logic utilizing self.pm.client.create_order
        # (Simplified for snippet - assumes token_id is known)
        pass 

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
            
            # Filter: Only look at favorites > 60% win prob (Value betting on strong teams)
            if favorite['fair_prob'] < 0.60:
                continue

            print(f"   🔎 Analyzing: {game['matchup']}")
            print(f"      Favorite: {favorite['name']} (Fair Prob: {favorite['fair_prob']*100:.1f}%)")
            
            # 2. Contrarian Check (Perplexity)
            # We construct a synthetic 'market question' to pass to validator
            synthetic_question = f"Will {favorite['name']} win against {game['matchup'].replace(favorite['name'], '').replace('vs', '').strip()}?"
            
            # VALIDATE using RISK MANAGER PROMPT
            is_valid, reason, conf = self.validator.validate(
                market_question=synthetic_question,
                outcome="YES",
                price=favorite['fair_prob'] - 0.05, # Conservative buffer
                system_prompt=RISK_MANAGER_PROMPT,
                min_confidence=0.7 # High bar
            )
            
            if not is_valid:
                print(f"      🛑 PASS: Risk Manager says NO. ({reason})")
            else:
                print(f"      ✅ VALIDATED: {reason}")
                print(f"      🚀 ACTION: Look for Polymarket price < {favorite['fair_prob']*100:.1f}¢")
                
                # Here we would search for the actual Polymarket market ID and place the bet
                # For MVP, we log the signal.

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
