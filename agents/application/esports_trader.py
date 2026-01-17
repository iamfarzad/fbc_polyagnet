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

# Trading parameters - LIVE CONFIG
MIN_EDGE_PERCENT = 1.5          # Lower threshold for small trades
MIN_BET_USD = 5.00              # Fixed $5 trades
MAX_BET_USD = 5.00              # Fixed $5 trades
BET_PERCENT = 0.40              # 40% of bankroll allocated to esports
MAX_CONCURRENT_POSITIONS = 10   # Allow 10 concurrent positions

# Timing - LIVE TRADING MODE (aggressive)
POLL_INTERVAL_LIVE = 5          # Poll every 5s during live match
POLL_INTERVAL_IDLE = 30         # Poll every 30s when no live match
EXIT_EDGE_THRESHOLD = 0.01      # Exit when edge drops below 1%

# API Rate Limiting (Gamma API is generous - no strict limits for reads)
MAX_REQUESTS_PER_HOUR = 10000   # Gamma API is very permissive
MAX_REQUESTS_PER_MINUTE = 100   # Allow 100 requests per minute (safe for Gamma)
REQUEST_COUNT_RESET_HOUR = 60 * 60  # 1 hour in seconds

# ESPORTS SERIES IDs (from Gamma /sports API - DO NOT CHANGE)
# These are the correct series IDs for fetching live match markets
ESPORTS_SERIES = {
    "cs2": 10310,       # Counter-Strike 2
    "lol": 10311,       # League of Legends
    "dota2": 10309,     # Dota 2
    "valorant": 10437,  # Valorant
    "lcs": 10288,       # League Championship Series
    "wildrift": 10429,  # Wild Rift
    "hok": 10434,       # Honor of Kings
}

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
        
        # Combine factors with weights based on game time
        if state.game_time < 600:  # First 10 minutes - kills matter more
            prob += (gold_factor * 0.6) + (kill_factor * 1.2) + (obj_factor * 0.2)
        elif state.game_time < 1200:  # 10-20 minutes - balanced
            prob += (gold_factor * 0.8) + (kill_factor * 0.8) + (obj_factor * 0.4)
        else:  # Late game - gold and objectives dominate
            prob += (gold_factor * 1.0) + (kill_factor * 0.4) + (obj_factor * 0.6)

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
        print(f"🔍 DEBUG: RiotAPIProvider.get_live_matches called, key exists: {bool(self.pandascore_key)}")
        # Try PandaScore for pro matches (easier API)
        if self.pandascore_key:
            try:
                url = "https://api.pandascore.co/lol/matches/running"
                headers = {"Authorization": f"Bearer {self.pandascore_key}"}
                print(f"🔍 DEBUG: Making API call to {url}")
                resp = requests.get(url, headers=headers, timeout=10)
                print(f"🔍 DEBUG: API response status: {resp.status_code}")
                if resp.status_code == 200:
                    matches = resp.json()
                    print(f"🔍 DEBUG: Found {len(matches)} live LoL matches")
                    return matches
                else:
                    print(f"🔍 DEBUG: API error: {resp.status_code} - {resp.text}")
            except Exception as e:
                print(f"🔍 DEBUG: PandaScore exception: {e}")

        print("🔍 DEBUG: No pandascore key or API failed, returning empty list")
        return []
    
    def get_match_state(self, match_id: str) -> Optional[GameState]:
        """Get current state of a live LoL match with enhanced game data."""
        if not self.pandascore_key:
            return None

        try:
            # First get match overview
            match_url = f"https://api.pandascore.co/lol/matches/{match_id}"
            headers = {"Authorization": f"Bearer {self.pandascore_key}"}
            resp = requests.get(match_url, headers=headers, timeout=10)

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

            # ENHANCED: Get detailed game data from game endpoint
            game_id = current_game.get("id")
            if game_id:
                try:
                    game_url = f"https://api.pandascore.co/lol/games/{game_id}"
                    game_resp = requests.get(game_url, headers=headers, timeout=10)

                    if game_resp.status_code == 200:
                        detailed_game = game_resp.json()
                        # Update current_game with detailed data
                        current_game.update(detailed_game)
                except Exception as e:
                    print(f"Warning: Could not fetch detailed game data: {e}")

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
                team1_objectives=team1_data.get("tower_kills", 0) + team1_data.get("dragon_kills", 0) + team1_data.get("baron_kills", 0),
                team2_objectives=team2_data.get("tower_kills", 0) + team2_data.get("dragon_kills", 0) + team2_data.get("baron_kills", 0),
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

    def get_game_frames(self, game_id: str, game_type: str) -> Optional[Dict]:
        """
        Get real-time frames data for enhanced game state analysis.

        Available for: LoL (/lol/games/{id}/frames)
        This provides second-by-second game statistics for the Teemu edge.
        """
        if not self.pandascore_key:
            return None

        try:
            if game_type == "lol":
                url = f"https://api.pandascore.co/lol/games/{game_id}/frames"
            else:
                return None  # Frames only available for LoL currently

            headers = {"Authorization": f"Bearer {self.pandascore_key}"}
            resp = requests.get(url, headers=headers, timeout=10)

            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"Frames API error: {resp.status_code}")
                return None

        except Exception as e:
            print(f"Error fetching game frames: {e}")
            return None

    def get_game_rounds(self, game_id: str, game_type: str) -> Optional[Dict]:
        """
        Get round-by-round data for CS2/Valorant.

        Available for: CS2 (/csgo/games/{id}/rounds), Valorant (/valorant/games/{id}/rounds)
        """
        if not self.pandascore_key:
            return None

        try:
            if game_type == "cs2":
                url = f"https://api.pandascore.co/csgo/games/{game_id}/rounds"
            elif game_type == "valorant":
                url = f"https://api.pandascore.co/valorant/games/{game_id}/rounds"
            else:
                return None

            headers = {"Authorization": f"Bearer {self.pandascore_key}"}
            resp = requests.get(url, headers=headers, timeout=10)

            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"Rounds API error: {resp.status_code}")
                return None

        except Exception as e:
            print(f"Error fetching game rounds: {e}")
            return None


class EsportsDataAggregator:
    """Aggregates data from multiple esports APIs."""
    
    def __init__(self):
        self.lol_provider = RiotAPIProvider()
        self.cs2_provider = CS2DataProvider()
        
    def get_all_live_matches(self) -> List[Dict]:
        """Get all currently live matches across games."""
        print("🔍 DEBUG: get_all_live_matches called")
        matches = []

        try:
            # LoL matches
            print("🔍 DEBUG: Getting LoL matches...")
            lol_matches = self.lol_provider.get_live_matches()
            print(f"🔍 DEBUG: LoL provider returned {len(lol_matches)} matches")
            for match in lol_matches:
                match["game_type"] = "lol"
                matches.append(match)

            # CS2 matches
            print("🔍 DEBUG: Getting CS2 matches...")
            cs2_matches = self.cs2_provider.get_live_matches()
            print(f"🔍 DEBUG: CS2 provider returned {len(cs2_matches)} matches")
            for match in cs2_matches:
                match["game_type"] = "cs2"
                matches.append(match)

            print(f"🔍 DEBUG: Total live matches found: {len(matches)}")
        except Exception as e:
            print(f"🔍 DEBUG: Exception in get_all_live_matches: {e}")
            import traceback
            traceback.print_exc()

        return matches
    
    def get_upcoming_matches(self, game_type: str, hours_ahead: int = 24) -> List[Dict]:
        """
        Get upcoming matches to know when to expect trading opportunities.

        This helps the bot know when esports tournaments are scheduled.
        """
        if not self.lol_provider.pandascore_key:
            return []

        try:
            url = f"https://api.pandascore.co/{game_type}/matches/upcoming"
            headers = {"Authorization": f"Bearer {self.lol_provider.pandascore_key}"}

            # Get matches in the next N hours
            params = {"per_page": 50}  # Get more to filter by time

            resp = requests.get(url, headers=headers, params=params, timeout=10)

            if resp.status_code != 200:
                return []

            matches = resp.json()

            # Filter to matches starting within our time window
            from datetime import datetime, timedelta
            now = datetime.now()
            cutoff = now + timedelta(hours=hours_ahead)

            upcoming = []
            for match in matches:
                scheduled_at = match.get("scheduled_at")
                if scheduled_at:
                    try:
                        match_time = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                        if now <= match_time <= cutoff:
                            upcoming.append(match)
                    except:
                        pass

            return upcoming

        except Exception as e:
            print(f"Error fetching upcoming matches: {e}")
            return []

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
        """
        Get active esports markets using correct series IDs.
        
        Uses ESPORTS_SERIES dict to fetch live match markets directly.
        This replaces the broken keyword-search approach.
        """
        import ast
        result_markets = []
        
        print(f"   Fetching esports from {len(ESPORTS_SERIES)} game types...")
        
        for game_type, series_id in ESPORTS_SERIES.items():
            try:
                url = "https://gamma-api.polymarket.com/events"
                params = {
                    "series_id": series_id,
                    "active": "true",
                    "closed": "false",
                    "limit": 50
                }
                
                resp = requests.get(url, params=params, timeout=15)
                if resp.status_code != 200:
                    print(f"   ⚠️ {game_type} API error: {resp.status_code}")
                    continue
                
                events = resp.json()
                
                if not events:
                    continue
                    
                print(f"   📊 {game_type.upper()}: {len(events)} events")
                
                # Extract markets from events
                for event in events:
                    markets = event.get("markets", [])
                    
                    for m in markets:
                        # Skip if not accepting orders
                        if not m.get("acceptingOrders", True):
                            continue
                            
                        # Parse tokens
                        clob_ids = m.get("clobTokenIds")
                        if not clob_ids or clob_ids == "[]":
                            continue
                        
                        try:
                            tokens = ast.literal_eval(clob_ids) if isinstance(clob_ids, str) else clob_ids
                            if len(tokens) < 2:
                                continue
                        except:
                            continue
                        
                        # Parse prices
                        outcomes = m.get("outcomePrices", "[0.5, 0.5]")
                        if isinstance(outcomes, str):
                            try:
                                outcomes = ast.literal_eval(outcomes)
                            except:
                                outcomes = [0.5, 0.5]
                        
                        yes_price = float(outcomes[0]) if outcomes else 0.5
                        no_price = float(outcomes[1]) if len(outcomes) > 1 else 1 - yes_price
                        
                        # Extract team names from question
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
                            volume=float(m.get("volume24hr", 0) or 0),
                            end_date=m.get("endDate", "")
                        ))
                        
            except Exception as e:
                print(f"   ⚠️ {game_type} fetch error: {e}")
                continue
        
        print(f"   ✅ Total: {len(result_markets)} esports markets found")
        return result_markets
    
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

        # API Rate Limiting
        self.api_requests_this_hour = 0
        self.api_requests_this_minute = 0
        self.last_request_time = 0
        self.hour_start_time = time.time()
        self.minute_start_time = time.time()
        
        # Get balance with error logging
        try:
            self.balance = self.pm_esports.pm.get_usdc_balance()
            print(f"   💰 Initial balance: ${self.balance:.2f}")
        except Exception as e:
            print(f"   ⚠️ Balance retrieval error: {e}")
            self.balance = 0
        
        print("=" * 60)
        print("🎮 ESPORTS LIVE TRADER - TeemuTeumuTeumu Style")
        print("=" * 60)
        print(f"Mode: {'DRY RUN' if dry_run else '🔴 LIVE TRADING'}")
        print(f"Balance: ${self.balance:.2f}")
        print(f"Min Edge: {MIN_EDGE_PERCENT}%")
        print(f"Bet Size: ${MIN_BET_USD}-${MAX_BET_USD} (fixed small amounts)")
        print(f"Strategy: Hybrid - Market edges + Live data when available")
        print(f"Markets: 900+ live esports markets discovered")
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
        """Calculate bet size - fixed $5 trades with 40% wallet allocation."""
        try:
            self.balance = self.pm_esports.pm.get_usdc_balance()
        except:
            pass

        # 40% of wallet allocated to esports
        esports_allocation = self.balance * BET_PERCENT
        
        # Fixed $5 trades, but cap at allocated amount
        if esports_allocation >= MIN_BET_USD:
            return min(MAX_BET_USD, esports_allocation / MAX_CONCURRENT_POSITIONS)
        else:
            print(f"   ⚠️ Insufficient esports allocation: ${esports_allocation:.2f} (need ${MIN_BET_USD})")
            return 0  # Not enough balance
    
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
        CONSERVATIVE GROWTH MODE: Free-tier friendly growth strategy.
        - Polls conservatively to stay within API limits
        - Moderate balance compounding
        """
        print("🚀 ESPORTS CONSERVATIVE GROWTH MODE: Free-tier optimized")
        print(f"   Polling Interval: {POLL_INTERVAL_LIVE}s (rate limit friendly)")
        print(f"   Compounding: Moderate")
        print(f"   API Limits: {MAX_REQUESTS_PER_HOUR}/hour, {MAX_REQUESTS_PER_MINUTE}/minute")
        print(f"   ⚠️  WARNING: Requires PANDASCORE_API_KEY for profitable trading")

        while True:
            try:
                # SYNC BALANCE: Ensure recent wins from other agents are available
                try:
                    self.balance = self.pm_esports.pm.get_usdc_balance()
                except: pass

                # Conservative scaling: Use 5% of total bankroll per live match
                current_balance = self.balance
                target_bet = current_balance * 0.05
                # Cap at safe limits
                target_bet = max(MIN_BET_USD, min(target_bet, MAX_BET_USD))

                # Scan Live Matches (with rate limiting)
                sleep_time = self.scan_and_trade()
                time.sleep(sleep_time)  # Use returned sleep time (may be rate limited)

            except KeyboardInterrupt:
                print("\nStopping...")
                break
            except Exception as e:
                print(f"Error in growth loop: {e}")
                time.sleep(5)

    def check_rate_limits(self) -> float:
        """
        Check API rate limits and return appropriate sleep time.
        Returns seconds to sleep before next API call.
        """
        current_time = time.time()

        # Reset counters if needed
        if current_time - self.hour_start_time >= REQUEST_COUNT_RESET_HOUR:
            self.api_requests_this_hour = 0
            self.hour_start_time = current_time

        if current_time - self.minute_start_time >= 60:
            self.api_requests_this_minute = 0
            self.minute_start_time = current_time

        # Check limits
        if self.api_requests_this_hour >= MAX_REQUESTS_PER_HOUR * 0.9:  # 90% of limit
            sleep_time = 300  # 5 minutes
            print(f"   ⚠️ NEARING HOURLY LIMIT ({self.api_requests_this_hour}/{MAX_REQUESTS_PER_HOUR}) - Sleeping {sleep_time}s")
            return sleep_time

        if self.api_requests_this_minute >= MAX_REQUESTS_PER_MINUTE * 0.8:  # 80% of limit
            sleep_time = 60  # 1 minute
            print(f"   ⚠️ NEARING MINUTE LIMIT ({self.api_requests_this_minute}/{MAX_REQUESTS_PER_MINUTE}) - Sleeping {sleep_time}s")
            return sleep_time

        return 0  # No need to sleep

    def increment_request_count(self):
        """Increment API request counters."""
        current_time = time.time()
        self.api_requests_this_hour += 1
        self.api_requests_this_minute += 1
        self.last_request_time = current_time

    def save_state(self):
        """Save state for dashboard."""
        try:
            state_update = {
                "esports_trader_last_activity": f"Trades: {self.session_trades} | Watching {len(self.positions)} positions",
                "esports_trader_trades": self.session_trades,
                "esports_trader_pnl": self.session_pnl,
                "esports_trader_last_scan": datetime.datetime.now().strftime("%H:%M:%S"),
                "esports_trader_mode": "DRY RUN" if self.dry_run else "LIVE",
                "esports_trader_api_usage": f"{self.api_requests_this_hour}/{MAX_REQUESTS_PER_HOUR} requests this hour"
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
        """
        Hybrid Strategy Scan:
        1. Discovery: Polymarket Gamma API (Series IDs) -> Finds ALL games.
        2. Signal: PandaScore/Riot Data -> Provides "Teemu Advantage" (Latency Edge).
        3. Execution: Direct CLOB.
        """
        print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🔍 Scanning esports markets...")

        # 0. Check Rate Limits First
        rate_limit_sleep = self.check_rate_limits()
        if rate_limit_sleep > 0:
            return rate_limit_sleep

        # 1. Check Pause State (only for pausing, NOT for dry_run - respect --live flag)
        try:
            with open("bot_state.json", "r") as f:
                state = json.load(f)
            if not state.get("esports_trader_running", True):
                print("   Esports Trader paused via dashboard. Sleeping...")
                return POLL_INTERVAL_IDLE
            # NOTE: Do NOT override self.dry_run here - respect the --live flag from command line
        except: pass
        
        # 2. Auto-Redeem
        if self.redeemer:
            try: self.redeemer.scan_and_redeem()
            except: pass

        # 3. DISCOVERY: Get Polymarket markets (Gamma API)
        markets = self.pm_esports.get_esports_markets()
        print(f"   found {len(markets)} esports markets on Polymarket")
        
        if not markets:
            # Check for upcoming matches when no live markets
            self._check_upcoming_matches()
            return POLL_INTERVAL_IDLE

        # 4. SIGNAL: Get Live Data (PandaScore/Riot) - REQUIRED FOR EDGE!
        # This is our competitive advantage. Without it, we don't trade.
        live_matches = []
        pandascore_available = bool(os.getenv("PANDASCORE_API_KEY"))
        print(f"🔍 DEBUG: pandascore_available = {pandascore_available}, env var = {bool(os.getenv('PANDASCORE_API_KEY'))}")

        if not pandascore_available:
            print(f"   ❌ NO PANDASCORE API KEY: Esports trading disabled")
            print(f"      Environment check: {[k for k in os.environ.keys() if 'panda' in k.lower()]}")
            print(f"      Fly.io secrets should be available - check fly secrets list")
            print(f"      Get free API key at pandascore.co to enable profitable trading")
            print(f"      Without data, esports trading becomes unprofitable gambling")
            return POLL_INTERVAL_IDLE

        print(f"🔍 DEBUG: About to call get_all_live_matches(), pandascore_available={pandascore_available}")
        try:
            live_matches = self.data_aggregator.get_all_live_matches()
            # Track API usage (each live matches call counts as ~2-3 requests)
            self.increment_request_count()
            self.increment_request_count()  # For both LoL and CS2 calls
            print(f"   found {len(live_matches)} active games in data feed")
        except Exception as e:
            print(f"   ⚠️ Data feed error: {e}")
            print(f"      Disabling trading until Pandascore is working")
            return POLL_INTERVAL_IDLE

        trades_made = 0
        
        for market in markets:
            question = market.question
            yes_price = market.yes_price
            no_price = market.no_price
            
            # --- CHECK 1: INTERNAL ARBITRAGE ---
            # If Yes + No < 0.99, it's free money (rare but happens)
            spread_sum = yes_price + no_price
            if spread_sum < 0.985: # 1.5% profit buffer
                print(f"\n   🚨 ARBITRAGE DETECTED: {question[:40]}...")
                print(f"      Yes({yes_price}) + No({no_price}) = {spread_sum:.3f}")
                # Buy both sides? Or just the cheaper one?
                # Usually one side is mispriced. Let's buy the favorite side if clear, or both.
                # Simple logic: Buy the side with higher liquidity/volume to close gap
                target_side = "YES" if yes_price < no_price else "NO" 
                print(f"      ⚡ Executing ARB on {target_side}")
                self.execute_trade(market, target_side, 0.99, yes_price if target_side=="YES" else no_price)
                continue

            # --- CHECK 2: FILTER GARBAGE ---
            if yes_price > 0.92 or no_price > 0.92: continue # Too expensive
            if yes_price < 0.08 or no_price < 0.08: continue # Too cheap/lotto

            # --- CHECK 3: HYBRID TRADING LOGIC ---

            # Match Market -> Live Data (when available)
            live_match = self.match_market_to_live_game(market, live_matches)

            if live_match and live_matches:  # PandaScore data available
                # === PATH A: TEEMU MODE (DATA DRIVEN) ===
                # We have live stats (Gold, Kills) -> Huge Edge
                game_type = live_match.get("game_type", "lol")
                match_id = str(live_match.get("id"))
                state = self.data_aggregator.get_match_state(match_id, game_type)

                if state and state.is_live:
                    true_prob = self.model.calculate(state)

                    # Calculate Edge
                    market_prob = yes_price
                    edge = true_prob - market_prob

                    print(f"\n   ⚔️ TEEMU MODE: {question[:40]}...")
                    print(f"      Stats: {state.team1} vs {state.team2} | Gold Diff: {state.gold_diff():+d}")
                    print(f"      True Prob: {true_prob*100:.1f}% vs Market: {market_prob*100:.1f}%")

                    if abs(edge) > MIN_EDGE_PERCENT / 100:
                        side = "YES" if edge > 0 else "NO"
                        print(f"      🔥 DATA EDGE: {side} (Edge: {abs(edge)*100:.1f}%)")
                        if self.execute_trade(market, side, true_prob, market.yes_price if side=="YES" else market.no_price):
                            trades_made += 1
                        continue

            # === PATH B: MARKET-BASED TRADING (DISABLED - TOO RISKY WITHOUT DATA) ===
            # WARNING: Without Pandascore data, this is essentially gambling
            # The market-based heuristics are often wrong and lead to losses

            print(f"   ⚠️ NO PANDASCORE DATA: Skipping market-based trading for {question[:30]}...")
            print(f"      Get Pandascore API key at pandascore.co to enable data-driven trading")
            print(f"      Market odds: Yes={yes_price:.3f}, No={no_price:.3f}")

            # DISABLED: Don't make trades without data advantage
            # The following code would gamble based on simplistic assumptions:

            # Look for arbitrage opportunities (rare and usually already arbitraged)
            # if spread_sum < 0.985:  # Only true arbitrage
            #     print(f"\n   💰 TRUE ARBITRAGE: {question[:40]}...")
            #     side = "YES" if yes_price < no_price else "NO"
            #     if self.execute_trade(market, side, 0.99, yes_price if side=="YES" else no_price):
            #         trades_made += 1
            #     continue

            # # Don't do market edge detection without data - it's gambling
            # print(f"      ❌ SKIPPING: No data advantage = no trade")

            continue

        # Save state & Return
        self.save_state()
        return POLL_INTERVAL_LIVE

    def _check_upcoming_matches(self):
        """Check for upcoming matches to inform about potential trading windows."""
        try:
            upcoming_matches = []
            for game in ["lol", "csgo", "dota2", "valorant"]:
                matches = self.data_aggregator.get_upcoming_matches(game, hours_ahead=48)  # Next 48 hours
                upcoming_matches.extend([(game, m) for m in matches])

            if upcoming_matches:
                print(f"📅 Upcoming esports matches in next 48h: {len(upcoming_matches)}")
                # Show next 3 matches
                for game, match in upcoming_matches[:3]:
                    teams = [op['opponent']['name'] for op in match.get('opponents', []) if op.get('opponent')]
                    team_str = f"{teams[0]} vs {teams[1]}" if len(teams) >= 2 else "TBD"
                    scheduled = match.get('scheduled_at', 'TBD')
                    print(f"   {game.upper()}: {team_str} @ {scheduled[:16] if scheduled != 'TBD' else 'TBD'}")
            else:
                print(f"📅 No esports matches scheduled in next 48h - bot will check periodically")

        except Exception as e:
            print(f"⚠️ Error checking upcoming matches: {e}")

    def run(self):
        """Main run loop with hybrid strategy."""
        print("🔍 DEBUG: run() method called!")
        print("\n🎮 ESPORTS TRADER ACTIVE - DATA-DRIVEN MODE")
        print("   ⚠️  REQUIRES PANDASCORE API KEY for profitable trading")
        print("   📊 Strategy: Live game stats vs market odds (latency arbitrage)")
        print("   🎯 Target: 0.5-2% edge per trade on 900+ live esports markets")
        print("   🛑 Without Pandascore: Trading DISABLED (prevents losses)")
        print()

        # Check for Pandascore immediately
        pandascore_key = os.getenv("PANDASCORE_API_KEY")
        print(f"🔍 PANDASCORE_API_KEY status: {'FOUND' if pandascore_key else 'NOT FOUND'}")
        if pandascore_key:
            print(f"   Key preview: {pandascore_key[:10]}...")
        else:
            # Try alternative environment variable names that Fly.io might use
            alt_keys = ["PANDASCORE_API_KEY", "pandascore_api_key", "PANDA_KEY"]
            for alt_key in alt_keys:
                alt_value = os.getenv(alt_key)
                if alt_value:
                    print(f"   ✅ Found key under alt name: {alt_key}")
                    pandascore_key = alt_value
                    break

            # Check all environment variables for anything containing 'panda'
            all_panda_vars = {k: v for k, v in os.environ.items() if 'panda' in k.lower()}
            if all_panda_vars:
                print(f"   🐼 Found panda vars: {list(all_panda_vars.keys())}")
                for k, v in all_panda_vars.items():
                    print(f"      {k}: {v[:10]}...")
                    if not pandascore_key:
                        pandascore_key = v

            if not pandascore_key:
                print("❌ PANDASCORE_API_KEY not found!")
                print("   1. Go to https://pandascore.co")
                print("   2. Sign up for free account")
                print("   3. Get API key from dashboard")
                print("   4. Set PANDASCORE_API_KEY environment variable")
                print("   5. Restart the esports trader")
                print("\n   Without this key, the bot will not trade (to prevent losses)")
                print("\n   💡 Pro tip: Pandascore has a generous free tier (1000 requests/day)")
                print("   This gives you ~1 year of data for development and testing")
                print("\n   🚀 QUICK SETUP:")
                print("   export PANDASCORE_API_KEY='your_key_here'  # Add to your .env or Fly.io secrets")
                print("   fly secrets set PANDASCORE_API_KEY=your_key_here  # For Fly.io deployment")
                return
        
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
