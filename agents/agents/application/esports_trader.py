"""
Esports Live Trading Bot - TeemuTeemuTeemu Style

Exploits the 30-40 second stream delay between:
1. Real-time game data (Riot API, etc.)
2. Polymarket odds (based on stream watchers)

Strategy:
- Monitor live esports matches via official APIs
- Calculate win probability from in-game state
- When game state changes (kill, objective), market hasn't adjusted yet
- Enter position at stale odds, exit when market catches up

Focus: League of Legends, CS2, Dota 2
Target: 0.5-2% profit per trade, hundreds of trades per match
"""

import os
import sys
import time
import json
import asyncio
import requests
import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv

# Add parent paths for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.polymarket.polymarket import Polymarket
from agents.utils.validator import Validator, SharedConfig
from agents.utils.context import get_context, Position, Trade

# --- ESPORTS CONTRARIAN SYSTEM PROMPT ---
ESPORTS_RISK_MANAGER_PROMPT = """You are a contrarian esports bettor and risk manager.
Your GOAL is to find reasons NOT to bet on the favorite.

For the requested matchup, perform these specific checks:
1. ROSTER CHECK: Search explicitly for "[Team Name] roster changes stand-in". If a stand-in is playing, DEDUCT 20% from win probability.
2. RECENT FORM: Search for "last 5 matches". If the favorite lost 3+ of last 5, they are "Cold".
3. PATCH NOTES: If a major patch (e.g. new LoL patch) just dropped, increased volatility -> CAUTION.

OUTPUT "PASS" IF:
- A stand-in is playing for the favorite.
- The favorite is on a losing streak.
- There is significant uncertainty about the roster.

Only recommend "BET" if the team is stable, full roster, and in form."""

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

# =============================================================================
# CONFIGURATION
# =============================================================================

# Trading parameters
MIN_EDGE_PERCENT = 3            # Need 3%+ edge to enter (tight for HFT)
MIN_BET_USD = 1.00              # Polymarket minimum
MAX_BET_USD = 20.00             # Keep positions small for quick exits
BET_PERCENT = 0.05              # 5% of bankroll per trade
MAX_CONCURRENT_POSITIONS = 3    # Max positions per match

# Timing - TURBO MODE
POLL_INTERVAL_LIVE = 1          # Poll every 1s during live match (TURBO)
POLL_INTERVAL_IDLE = 30         # Poll every 30s when no live match
EXIT_EDGE_THRESHOLD = 0.01      # Exit when edge drops below 1%

# API Keys (loaded dynamically)
# RIOT_API_KEY - for League of Legends
# PANDASCORE_API_KEY - for CS2/Dota2 (alternative)

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class GameState:
    """Represents current state of a live esports match."""
    game_type: str              # "lol", "cs2", "dota2"
    match_id: str
    team1: str
    team2: str
    team1_score: int = 0        # Kills for LoL/Dota, Rounds for CS2
    team2_score: int = 0
    team1_gold: int = 0         # Gold/Economy advantage
    team2_gold: int = 0
    game_time: int = 0          # Seconds into game
    team1_objectives: int = 0   # Towers/Rounds won
    team2_objectives: int = 0
    is_live: bool = False
    raw_data: dict = None
    
    def gold_diff(self) -> int:
        """Gold difference (positive = team1 ahead)."""
        return self.team1_gold - self.team2_gold
    
    def score_diff(self) -> int:
        """Score difference (positive = team1 ahead)."""
        return self.team1_score - self.team2_score


@dataclass 
class PolymarketMatch:
    """A Polymarket esports market."""
    market_id: str
    question: str
    team1: str
    team2: str
    yes_token: str              # Team1 wins token
    no_token: str               # Team2 wins token
    yes_price: float
    no_price: float
    volume: float
    end_date: str


# =============================================================================
# WIN PROBABILITY MODELS
# =============================================================================

class WinProbabilityModel:
    """
    Calculates win probability from game state.
    
    Based on historical data analysis:
    - Gold lead is the strongest predictor in LoL/Dota
    - Round score is the strongest predictor in CS2
    - Early leads are less predictive than late leads
    """
    
    @staticmethod
    def lol_win_probability(state: GameState) -> float:
        """
        League of Legends win probability for team1.
        
        Formula based on:
        - Gold difference (most important)
        - Kill difference
        - Tower difference
        - Game time (early vs late game)
        """
        # Base probability
        prob = 0.50
        
        # Gold factor (most predictive)
        gold_diff = state.gold_diff()
        # ~1% win prob per 1000 gold difference
        gold_factor = gold_diff / 1000 * 0.01
        
        # Scale by game time (late game gold matters more)
        time_multiplier = min(2.0, 0.5 + state.game_time / 1200)  # Max at 20 min
        gold_factor *= time_multiplier
        
        # Kill factor
        kill_diff = state.score_diff()
        kill_factor = kill_diff * 0.015  # ~1.5% per kill
        
        # Objective factor (towers/dragons)
        obj_diff = state.team1_objectives - state.team2_objectives
        obj_factor = obj_diff * 0.03  # ~3% per objective
        
        # Combine factors
        prob += gold_factor + kill_factor + obj_factor
        
        # Clamp to valid range
        return max(0.05, min(0.95, prob))
    
    @staticmethod
    def cs2_win_probability(state: GameState) -> float:
        """
        CS2 win probability for team1.
        
        Based on:
        - Round score (most important)
        - Map position (CT/T side)
        - Economy
        """
        rounds_to_win = 13  # Standard competitive
        
        team1_rounds = state.team1_score
        team2_rounds = state.team2_score
        
        if team1_rounds >= rounds_to_win:
            return 1.0
        if team2_rounds >= rounds_to_win:
            return 0.0
        
        # Simple model: remaining rounds needed
        team1_needs = rounds_to_win - team1_rounds
        team2_needs = rounds_to_win - team2_rounds
        
        # Base probability from round difference
        total_remaining = team1_needs + team2_needs
        if total_remaining == 0:
            return 0.5
        
        prob = team2_needs / total_remaining
        
        # Economy factor (if available)
        if state.team1_gold > 0 or state.team2_gold > 0:
            economy_ratio = state.team1_gold / max(1, state.team1_gold + state.team2_gold)
            economy_factor = (economy_ratio - 0.5) * 0.1  # ±5% from economy
            prob += economy_factor
        
        return max(0.05, min(0.95, prob))
    
    @staticmethod
    def dota2_win_probability(state: GameState) -> float:
        """
        Dota 2 win probability for team1.
        
        Similar to LoL but with Dota-specific adjustments:
        - Net worth difference
        - Tower status
        - Kill score
        - Game time (Dota games are longer)
        """
        prob = 0.50
        
        # Net worth factor
        gold_diff = state.gold_diff()
        # Dota has higher gold numbers, so ~0.5% per 1000 gold
        gold_factor = gold_diff / 1000 * 0.005
        
        # Scale by game time (max at ~30 min for Dota)
        time_multiplier = min(2.0, 0.5 + state.game_time / 1800)
        gold_factor *= time_multiplier
        
        # Kill factor
        kill_diff = state.score_diff()
        kill_factor = kill_diff * 0.02  # ~2% per kill
        
        # Tower factor
        obj_diff = state.team1_objectives - state.team2_objectives
        obj_factor = obj_diff * 0.04  # ~4% per tower
        
        prob += gold_factor + kill_factor + obj_factor
        
        return max(0.05, min(0.95, prob))
    
    @classmethod
    def calculate(cls, state: GameState) -> float:
        """Calculate win probability based on game type."""
        if state.game_type == "lol":
            return cls.lol_win_probability(state)
        elif state.game_type == "cs2":
            return cls.cs2_win_probability(state)
        elif state.game_type == "dota2":
            return cls.dota2_win_probability(state)
        else:
            return 0.5


# =============================================================================
# DATA PROVIDERS
# =============================================================================

class RiotAPIProvider:
    """
    Fetches live League of Legends match data from Riot API.
    
    Note: For production, you'd need:
    1. Riot API key (free at developer.riotgames.com)
    2. Tournament API access for pro matches
    
    This implementation uses PandaScore as fallback for pro matches.
    """
    
    def __init__(self):
        self.api_key = os.getenv("RIOT_API_KEY")
        self.pandascore_key = os.getenv("PANDASCORE_API_KEY")
        
    def get_live_matches(self) -> List[Dict]:
        """Get currently live LoL matches."""
        # Try PandaScore for pro matches (easier API)
        if self.pandascore_key:
            try:
                url = "https://api.pandascore.co/lol/matches/running"
                headers = {"Authorization": f"Bearer {self.pandascore_key}"}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return resp.json()
            except Exception as e:
                print(f"PandaScore error: {e}")
        
        return []
    
    def get_match_state(self, match_id: str) -> Optional[GameState]:
        """Get current state of a live LoL match."""
        if not self.pandascore_key:
            return None
            
        try:
            url = f"https://api.pandascore.co/lol/matches/{match_id}"
            headers = {"Authorization": f"Bearer {self.pandascore_key}"}
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code != 200:
                return None
                
            data = resp.json()
            
            # Parse match data
            opponents = data.get("opponents", [])
            if len(opponents) < 2:
                return None
                
            team1 = opponents[0].get("opponent", {}).get("name", "Team1")
            team2 = opponents[1].get("opponent", {}).get("name", "Team2")
            
            # Get current game stats (if available)
            games = data.get("games", [])
            current_game = None
            for game in games:
                if game.get("status") == "running":
                    current_game = game
                    break
            
            if not current_game:
                return GameState(
                    game_type="lol",
                    match_id=match_id,
                    team1=team1,
                    team2=team2,
                    is_live=data.get("status") == "running",
                    raw_data=data
                )
            
            # Parse detailed game state
            team1_data = current_game.get("teams", [{}])[0] if current_game.get("teams") else {}
            team2_data = current_game.get("teams", [{}])[1] if len(current_game.get("teams", [])) > 1 else {}
            
            return GameState(
                game_type="lol",
                match_id=match_id,
                team1=team1,
                team2=team2,
                team1_score=team1_data.get("kills", 0),
                team2_score=team2_data.get("kills", 0),
                team1_gold=team1_data.get("gold", 0),
                team2_gold=team2_data.get("gold", 0),
                team1_objectives=team1_data.get("tower_kills", 0),
                team2_objectives=team2_data.get("tower_kills", 0),
                game_time=current_game.get("length", 0),
                is_live=True,
                raw_data=current_game
            )
            
        except Exception as e:
            print(f"Error fetching match state: {e}")
            return None


class CS2DataProvider:
    """Fetches live CS2 match data."""
    
    def __init__(self):
        self.pandascore_key = os.getenv("PANDASCORE_API_KEY")
    
    def get_live_matches(self) -> List[Dict]:
        """Get currently live CS2 matches."""
        if self.pandascore_key:
            try:
                url = "https://api.pandascore.co/csgo/matches/running"
                headers = {"Authorization": f"Bearer {self.pandascore_key}"}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return resp.json()
            except Exception as e:
                print(f"PandaScore CS2 error: {e}")
        
        return []
    
    def get_match_state(self, match_id: str) -> Optional[GameState]:
        """Get current state of a live CS2 match."""
        if not self.pandascore_key:
            return None
            
        try:
            url = f"https://api.pandascore.co/csgo/matches/{match_id}"
            headers = {"Authorization": f"Bearer {self.pandascore_key}"}
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code != 200:
                return None
                
            data = resp.json()
            opponents = data.get("opponents", [])
            if len(opponents) < 2:
                return None
                
            team1 = opponents[0].get("opponent", {}).get("name", "Team1")
            team2 = opponents[1].get("opponent", {}).get("name", "Team2")
            
            # Get current game/map
            games = data.get("games", [])
            current_game = None
            for game in games:
                if game.get("status") == "running":
                    current_game = game
                    break
            
            team1_score = 0
            team2_score = 0
            
            if current_game:
                # Round scores from current map
                for result in data.get("results", []):
                    if result.get("team_id") == opponents[0].get("opponent", {}).get("id"):
                        team1_score = result.get("score", 0)
                    else:
                        team2_score = result.get("score", 0)
            
            return GameState(
                game_type="cs2",
                match_id=match_id,
                team1=team1,
                team2=team2,
                team1_score=team1_score,
                team2_score=team2_score,
                is_live=data.get("status") == "running",
                raw_data=data
            )
            
        except Exception as e:
            print(f"Error fetching CS2 match: {e}")
            return None


class EsportsDataAggregator:
    """Aggregates data from multiple esports APIs."""
    
    def __init__(self):
        self.lol_provider = RiotAPIProvider()
        self.cs2_provider = CS2DataProvider()
        
    def get_all_live_matches(self) -> List[Dict]:
        """Get all currently live matches across games."""
        matches = []
        
        # LoL matches
        for match in self.lol_provider.get_live_matches():
            match["game_type"] = "lol"
            matches.append(match)
        
        # CS2 matches
        for match in self.cs2_provider.get_live_matches():
            match["game_type"] = "cs2"
            matches.append(match)
        
        return matches
    
    def get_match_state(self, match_id: str, game_type: str) -> Optional[GameState]:
        """Get state for a specific match."""
        if game_type == "lol":
            return self.lol_provider.get_match_state(match_id)
        elif game_type == "cs2":
            return self.cs2_provider.get_match_state(match_id)
        return None


# =============================================================================
# POLYMARKET INTEGRATION
# =============================================================================

class PolymarketEsports:
    """Handles Polymarket esports market operations."""
    
    def __init__(self):
        self.pm = Polymarket()
        
    def get_esports_markets(self) -> List[PolymarketMatch]:
        """Get active esports markets from Polymarket using Series IDs."""
        try:
            limit = 50
            # Series IDs: LoL (10360), CS2 (10361)
            series_ids = [10360, 10361]
            all_markets = []

            for sid in series_ids:
                url = "https://gamma-api.polymarket.com/events"
                params = {
                    "closed": "false",
                    "active": "true",
                    "limit": limit,
                    "series_id": sid
                }
                
                try:
                    resp = requests.get(url, params=params, timeout=10)
                    if resp.status_code == 200:
                        events = resp.json()
                        for event in events:
                            markets = event.get("markets", [])
                            for m in markets:
                                # Inject event title into market question if clearer
                                if "question" not in m:
                                    m["question"] = event.get("title", "")
                                all_markets.append(m)
                except Exception as e:
                    print(f"Error fetching series {sid}: {e}")
            
            # Filter to esports markets (double check slugs just in case)
            esports_slug_prefixes = ("cs2-", "csgo-", "lol-", "dota-", "valorant-")
            filtered_markets = []
            
            for m in all_markets:
                # With Series ID, we can be more confident, but let's keep slug check lenient
                # Actually, trust Series ID mainly.
                filtered_markets.append(m)
            
            # Process filtered markets into PolymarketMatch objects
            result_markets = []
            
            for m in filtered_markets:
                # Parse tokens
                clob_ids = m.get("clobTokenIds")
                if not clob_ids or clob_ids == "[]":
                    continue
                
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
                
                # Extract team names from question
                # Format usually: "Will [Team1] beat [Team2]?" or "[Team1] vs [Team2]"
                team1, team2 = self._extract_teams(m.get("question", ""))
                
                result_markets.append(PolymarketMatch(
                    market_id=m.get("id"),
                    question=m.get("question", ""),
                    team1=team1,
                    team2=team2,
                    yes_token=tokens[0],
                    no_token=tokens[1],
                    yes_price=yes_price,
                    no_price=no_price,
                    volume=float(m.get("volume24hr", 0)),
                    end_date=m.get("endDate", "")
                ))
            
            return result_markets
            
        except Exception as e:
            print(f"Error fetching esports markets: {e}")
            return []
    
    def _extract_teams(self, question: str) -> Tuple[str, str]:
        """Extract team names from market question."""
        import re
        
        # Pattern: "Counter-Strike: Team1 vs Team2 (BO3)"
        # Or: "Counter-Strike: Team1 vs Team2 - Map X Winner"
        match = re.search(r"(?:counter-strike|lol|dota|valorant):\s*(.+?)\s+vs\s+(.+?)(?:\s*[\(\-]|$)", question, re.IGNORECASE)
        if match:
            team1 = match.group(1).strip()
            team2 = match.group(2).strip()
            # Clean up team names
            team2 = re.sub(r'\s*\(BO\d\).*', '', team2).strip()
            team2 = re.sub(r'\s*-\s*Map.*', '', team2).strip()
            return team1, team2
        
        # Try generic "X vs Y" pattern  
        match = re.search(r"(.+?)\s+vs\.?\s+(.+?)(?:\s*[\(\?\-]|$)", question, re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        
        # Try "X beat Y" pattern
        match = re.search(r"will\s+(.+?)\s+beat\s+(.+?)[\?\.]", question, re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        
        return "Team1", "Team2"
    
    def get_market_odds(self, market_id: str) -> Tuple[float, float]:
        """Get current odds for a market."""
        try:
            url = f"https://gamma-api.polymarket.com/markets/{market_id}"
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return 0.5, 0.5
            
            data = resp.json()
            outcomes = data.get("outcomePrices", "[0.5, 0.5]")
            if isinstance(outcomes, str):
                import ast
                outcomes = ast.literal_eval(outcomes)
            
            yes_price = float(outcomes[0]) if outcomes else 0.5
            no_price = float(outcomes[1]) if len(outcomes) > 1 else 1 - yes_price
            
            return yes_price, no_price
        except:
            return 0.5, 0.5
    
    def place_order(self, token_id: str, side: str, price: float, size: float) -> Dict:
        """Place an order on Polymarket."""
        try:
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import BUY, SELL
            
            order_side = BUY if side == "BUY" else SELL
            
            order_args = OrderArgs(
                token_id=str(token_id),
                price=price,
                size=size,
                side=order_side
            )
            
            signed = self.pm.client.create_order(order_args)
            result = self.pm.client.post_order(signed)
            
            return result
            
        except Exception as e:
            return {"error": str(e)}


# =============================================================================
# ESPORTS TRADER BOT
# =============================================================================

class EsportsTrader:
    """
    Main esports trading bot.
    
    Strategy:
    1. Find active esports markets on Polymarket
    2. Match them with live game data
    3. Calculate our win probability vs market odds
    4. If edge > threshold, enter position
    5. Exit when edge disappears or match ends
    """
    
    def __init__(self, dry_run=True):
        self.dry_run = dry_run
        self.pm_esports = PolymarketEsports()
        self.data_aggregator = EsportsDataAggregator()
        self.model = WinProbabilityModel()
        
        # Initialize Validator
        try:
            self.validator = Validator(SharedConfig(), "esports")
            print("✅ LLM Validator initialized")
        except Exception as e:
            print(f"⚠️ Validator init failed: {e}")
            self.validator = None
        
        # State
        self.positions = {}  # market_id -> position data
        self.session_trades = 0
        self.session_pnl = 0.0
        
        # Get balance
        try:
            self.balance = self.pm_esports.pm.get_usdc_balance()
        except:
            self.balance = 0
        
        print("=" * 60)
        print("🎮 ESPORTS LIVE TRADER - TeemuTeemuTeemu Style")
        print("=" * 60)
        print(f"Mode: {'DRY RUN' if dry_run else '🔴 LIVE TRADING'}")
        print(f"Balance: ${self.balance:.2f}")
        print(f"Min Edge: {MIN_EDGE_PERCENT}%")
        print(f"Bet Size: {BET_PERCENT*100:.0f}% (${MIN_BET_USD}-${MAX_BET_USD})")
        print(f"Strategy: Real-time game data → Mispriced odds → Quick trades")
        print("=" * 60)
        print()
        
        # Check API keys
        has_pandascore = bool(os.getenv("PANDASCORE_API_KEY"))
        has_riot = bool(os.getenv("RIOT_API_KEY"))
        print(f"📡 Data Sources:")
        print(f"   PandaScore API: {'✅' if has_pandascore else '❌ (get free key at pandascore.co)'}")
        print(f"   Riot API: {'✅' if has_riot else '⚠️ (optional, for direct LoL data)'}")
        print()
        
        # Initialize auto-redeemer for winning positions
        self.redeemer = None
        if HAS_REDEEMER:
            try:
                self.redeemer = AutoRedeemer()
                print(f"✅ Auto-redeemer initialized")
            except Exception as e:
                print(f"⚠️ Auto-redeemer not available: {e}")
    
    def match_market_to_live_game(self, market: PolymarketMatch, live_matches: List[Dict]) -> Optional[Dict]:
        """Try to match a Polymarket market to a live game."""
        market_team1 = market.team1.lower()
        market_team2 = market.team2.lower()
        
        for match in live_matches:
            opponents = match.get("opponents", [])
            if len(opponents) < 2:
                continue
            
            live_team1 = opponents[0].get("opponent", {}).get("name", "").lower()
            live_team2 = opponents[1].get("opponent", {}).get("name", "").lower()
            
            # Check if teams match (fuzzy)
            team1_match = market_team1 in live_team1 or live_team1 in market_team1
            team2_match = market_team2 in live_team2 or live_team2 in market_team2
            
            # Also check reversed order
            team1_match_rev = market_team1 in live_team2 or live_team2 in market_team1
            team2_match_rev = market_team2 in live_team1 or live_team1 in market_team2
            
            if (team1_match and team2_match) or (team1_match_rev and team2_match_rev):
                return match
        
        return None
    
    def calculate_bet_size(self) -> float:
        """Calculate bet size."""
        try:
            self.balance = self.pm_esports.pm.get_usdc_balance()
        except:
            pass
        
        bet_size = self.balance * BET_PERCENT
        bet_size = max(MIN_BET_USD, min(bet_size, MAX_BET_USD))
        
        if self.balance < MIN_BET_USD:
            return 0
        
        return bet_size
    
    def execute_trade(self, market: PolymarketMatch, side: str, our_prob: float, market_prob: float) -> bool:
        """Execute a trade."""
        bet_size = self.calculate_bet_size()
        if bet_size == 0:
            return False
        
        # Determine token and price
        if side == "YES":
            token_id = market.yes_token
            entry_price = min(0.95, market.yes_price + 0.01)
        else:
            token_id = market.no_token
            entry_price = min(0.95, market.no_price + 0.01)
        
        shares = bet_size / entry_price
        edge = abs(our_prob - market_prob) * 100
        
        print(f"\n🎯 TRADE: {side} on {market.team1} vs {market.team2}")
        print(f"   Our Prob: {our_prob*100:.1f}% | Market: {market_prob*100:.1f}% | Edge: +{edge:.1f}%")
        print(f"   Entry: ${entry_price:.3f} | Size: ${bet_size:.2f} | Shares: {shares:.1f}")
        
        if self.dry_run:
            print(f"   [DRY RUN] Would execute trade")
            self.session_trades += 1
            return True
        
        result = self.pm_esports.place_order(token_id, "BUY", entry_price, shares)
        
        if result.get("success") or result.get("status") == "matched":
            print(f"   ✅ FILLED!")
            self.session_trades += 1
            self.positions[market.market_id] = {
                "side": side,
                "entry_price": entry_price,
                "shares": shares,
                "entry_time": datetime.datetime.now().isoformat()
            }
            return True
        else:
            print(f"   ⚠️ Order issue: {result}")
            return False

    def run_growth_mode(self):
        """
        TURBO MODE: 6-Day Sprint Growth Strategy.
        - Polls every 0.5s-1s
        - Aggressive balance compounding
        """
        print("🚀 ESPORTS TURBO MODE: Active for 6-day sprint")
        print(f"   Polling Interval: {POLL_INTERVAL_LIVE}s")
        print(f"   Compounding: Enabled")
        
        while True:
            try:
                # SYNC BALANCE: Ensure recent wins from other agents are available
                try:
                    self.balance = self.pm_esports.pm.get_usdc_balance()
                except: pass
                
                # Aggressive scaling: Use 10% of total bankroll per live match
                # Dynamic sizing based on bankroll
                current_balance = self.balance
                target_bet = current_balance * 0.10 
                # Cap at safe limits
                target_bet = max(MIN_BET_USD, min(target_bet, MAX_BET_USD))
                
                # Scan Live Matches
                self.scan_and_trade()
                
                time.sleep(POLL_INTERVAL_LIVE) # High-frequency polling
                
            except KeyboardInterrupt:
                print("\nStopping...")
                break
            except Exception as e:
                print(f"Error in growth loop: {e}")
                time.sleep(1)

    def save_state(self):
        """Save state for dashboard."""
        try:
            state_update = {
                "esports_trader_last_activity": f"Trades: {self.session_trades} | Watching {len(self.positions)} positions",
                "esports_trader_trades": self.session_trades,
                "esports_trader_pnl": self.session_pnl,
                "esports_trader_last_scan": datetime.datetime.now().strftime("%H:%M:%S"),
                "esports_trader_mode": "DRY RUN" if self.dry_run else "LIVE"
            }
            
            # Load existing state and update
            try:
                with open("bot_state.json", "r") as f:
                    existing = json.load(f)
                existing.update(state_update)
                state_update = existing
            except:
                pass
            
            with open("bot_state.json", "w") as f:
                json.dump(state_update, f, indent=2)
        except Exception as e:
            print(f"Error saving state: {e}")

    def scan_and_trade(self):
        """Main scan loop."""
        print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🔍 Scanning esports markets...")
        
        # Check if enabled
        
        # 1. Try Supabase
        if HAS_SUPABASE:
            try:
                supa = get_supabase_state()
                if supa:
                     if not supa.is_agent_running("esports"):
                         print("   Esports Trader paused via Supabase. Sleeping...")
                         return POLL_INTERVAL_IDLE
                     # self.dry_run = supa.get_global_dry_run() # Optional: sync dry run
            except Exception as e:
                print(f"Supabase check failed: {e}")

        # 2. Local Fallback
        try:
            with open("bot_state.json", "r") as f:
                state = json.load(f)
            if not state.get("esports_trader_running", True):
                print("   Esports Trader paused via dashboard. Sleeping...")
                return POLL_INTERVAL_IDLE
            self.dry_run = state.get("dry_run", True)
        except:
            pass
        
        # Auto-redeem any winning positions first
        if self.redeemer:
            try:
                print("   🔄 Checking for redeemable positions...")
                results = self.redeemer.scan_and_redeem()
                if results.get("redeemed", 0) > 0:
                    print(f"   💰 Redeemed {results['redeemed']} winning positions!")
                    time.sleep(3)  # Wait for balance update
            except Exception as e:
                print(f"   ⚠️ Redemption check failed: {e}")

        # Get Polymarket esports markets
        markets = self.pm_esports.get_esports_markets()
        print(f"   Found {len(markets)} esports markets on Polymarket")
        
        if not markets:
            return POLL_INTERVAL_IDLE
        
        # DIRECT TRADING MODE: Trade based on market prices + LLM validation
        # No need to wait for PandaScore - if Polymarket has a market, it's tradeable!
        print(f"   📊 Direct market mode - analyzing prices...")
        
        # Trade based on market prices directly - no external data needed
        trades_made = 0
        for market in markets:
            # Get current market odds
            market_yes, market_no = market.yes_price, market.no_price
            question = market.question
            
            # FILTER 1: Must have a clear favorite (>55% implied)
            if market_yes < 0.55 and market_no < 0.55:
                continue  # Too close to 50/50, skip
            
            # FILTER 2: Skip very extreme prices (>90c, low upside)
            if market_yes > 0.90 or market_no > 0.90:
                continue
            
            # Determine which side to evaluate
            if market_yes >= market_no:
                favorite_side = "YES"
                favorite_price = market_yes
                token_id = market.yes_token
            else:
                favorite_side = "NO"
                favorite_price = market_no
                token_id = market.no_token
            
            print(f"\n   📊 MARKET: {question[:60]}...")
            print(f"      Price: {favorite_side} @ ${favorite_price:.2f}")
            
            # LLM Validation
            trade_approved = False
            if self.validator:
                try:
                    is_valid, reason, conf = self.validator.validate(
                        market_question=question,
                        outcome=favorite_side,
                        price=favorite_price,
                        additional_context=ESPORTS_RISK_MANAGER_PROMPT
                    )
                    if is_valid:
                        print(f"      ✅ GREEN LIGHT: {reason} (conf: {conf*100:.0f}%)")
                        trade_approved = True
                    else:
                        print(f"      🛑 PASS: {reason} (conf: {conf*100:.0f}%)")
                except Exception as e:
                    print(f"      ⚠️ Validator Error: {e}")
                    # Fallback: if validator fails, allow trade if price is very good? 
                    # No, safer to skip if intelligence fails.
                    continue
            else:
                # No validator (e.g. missing keys), fallback to direct logic trust
                # Or skip? Let's allow if no validator but print warning
                print("      ⚠️ No validator active - proceeding with raw price logic")
                trade_approved = True

            if trade_approved:
                if self.execute_trade(market, favorite_side, favorite_price, favorite_price):
                    trades_made += 1
                    if trades_made >= MAX_CONCURRENT_POSITIONS:
                        print(f"   Max positions ({MAX_CONCURRENT_POSITIONS}) reached for this scan")
                        break
        
        print(f"\n   📈 Session: {self.session_trades} trades")
        
        # Save state for dashboard
        self.save_state()
        
        # Return faster poll interval since we're now trading actively
        return POLL_INTERVAL_LIVE
    
    def run(self):
        """Main run loop."""
        print("\n🎮 ESPORTS TRADER ACTIVE")
        print("   Watching for live matches with mispriced odds...")
        print()
        
        while True:
            try:
                poll_interval = self.scan_and_trade()
                print(f"\n   ⏳ Next scan in {poll_interval}s...")
                time.sleep(poll_interval)
                
            except KeyboardInterrupt:
                print("\n\nStopping Esports Trader...")
                print(f"Session: {self.session_trades} trades")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(30)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    is_live = "--live" in sys.argv
    
    trader = EsportsTrader(dry_run=not is_live)
    
    # Check for growth mode flag
    if "--growth" in sys.argv:
        trader.run_growth_mode()
    else:
        trader.run()
