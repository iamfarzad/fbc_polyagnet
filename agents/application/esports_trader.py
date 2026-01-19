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
from agents.utils.context import get_context, Position, Trade, LLMActivity

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
# Can be overridden via environment variable MIN_EDGE_PERCENT
MIN_EDGE_PERCENT = float(os.getenv("MIN_EDGE_PERCENT", "5.0"))  # RAISED to 5% - only take high-confidence edges
MIN_EDGE_PERCENT_TEST = 3.0     # Test mode threshold
MIN_BET_USD = 5.00              # Fixed $5 trades
MAX_BET_USD = 10.00             # Increased to $10 for more impact
BET_PERCENT = 0.85              # Allocates up to 85% of your $130 to esports trades
MAX_CONCURRENT_POSITIONS = 20   # Expands capacity to hold more high-probability winners

# Timing - LIVE TRADING MODE (More aggressive for increased activity)
POLL_INTERVAL_LIVE = 15         # Poll every 15s (was 30s) for faster response
POLL_INTERVAL_IDLE = 60         # Poll every 1m when idle (was 2m)
EXIT_EDGE_THRESHOLD = 0.01      # Exit when edge drops below 1%

# API Rate Limiting (Gamma API is generous - no strict limits for reads)
# API Rate Limiting (PandaScore Free Tier = 1000/hour)
MAX_REQUESTS_PER_HOUR = 1000    # Hard limit for PandaScore
MAX_REQUESTS_PER_MINUTE = 60    # Safe burst limit
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
    "r6siege": 10503,   # Rainbow Six Siege
    "cod": 10502,       # Call of Duty
    "rocket-league": 10504,  # Rocket League
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
    # Series info (for BO3/BO5 momentum trading)
    series_score1: int = 0      # Maps/games won by team1 (NEW)
    series_score2: int = 0      # Maps/games won by team2 (NEW)
    number_of_games: int = 3    # BO1, BO3, or BO5 (NEW)
    
    def gold_diff(self) -> int:
        """Gold difference (positive = team1 ahead)."""
        return self.team1_gold - self.team2_gold
    
    def score_diff(self) -> int:
        """Score difference (positive = team1 ahead)."""
        return self.team1_score - self.team2_score
    
    def has_series_edge(self) -> bool:
        """Check if there's a series score advantage (someone is ahead in BO3/BO5)."""
        if self.number_of_games <= 1:
            return False
        return self.series_score1 != self.series_score2

    def series_leader(self) -> Optional[str]:
        """Return which team is leading the series, or None if tied."""
        if self.series_score1 > self.series_score2:
            return self.team1
        elif self.series_score2 > self.series_score1:
            return self.team2
        return None


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
    
    @staticmethod
    def calculate_series_edge(state: GameState) -> float:
        """
        Calculates win probability based on series map score with CONTEXT-AWARE adjustments.
        Uses "Giant" team awareness to recognize elite teams that dominate with leads.
        This is the "Map Momentum" edge that works on PandaScore free tier.
        """
        # LAYER A: GIANT AWARENESS - Elite teams with leads are near-certain winners
        GIANTS = [
            "falcons", "spirit", "liquid", "gaimin", "furia", "g2", "vitality",
            "navi", "natus vincere", "virtus pro", "mouz", "heroic", "cloud9",
            "astralis", "nip", "fnatic", "sk gaming", "mibr", "pain", "imperial",
            "team liquid", "evil geniuses", "psg.lgd", "tundra", "secret", "og"
        ]

        team1_name = state.team1.lower().strip() if state.team1 else ""
        team2_name = state.team2.lower().strip() if state.team2 else ""

        # Check if either team is a recognized giant
        team1_is_giant = any(giant in team1_name for giant in GIANTS)
        team2_is_giant = any(giant in team2_name for giant in GIANTS)

        # BO1 LOGIC: SKIP - No edge without in-game data, too risky
        # Markets price underdogs correctly; assuming 50/50 leads to gambling on losers
        if state.number_of_games == 1:
            return None  # Signal to skip this market entirely

        # GIANT OVERRIDE: Move to 85/15 for Growth Sniper Mode
        if state.series_score1 > state.series_score2:
            if team1_is_giant:
                return 0.85  # Giant Lead (allows entries up to ~84¢)
            elif team2_is_giant:
                return 0.15  # Underdog vs Giant (allows entries at ~10¢-14¢)
        elif state.series_score2 > state.series_score1:
            if team2_is_giant:
                return 0.85  # Giant Lead
            elif team1_is_giant:
                return 0.15  # Underdog vs Giant

        # Standard series momentum logic (only used when no giants involved)
        # Best of 3 Logic
        if state.number_of_games == 3:
            if state.series_score1 == 1 and state.series_score2 == 0:
                return 0.72  # Team 1 up 1-0 has ~72% win prob (historical data)
            if state.series_score1 == 0 and state.series_score2 == 1:
                return 0.28  # Team 2 up 1-0

        # Best of 5 Logic
        if state.number_of_games == 5:
            if state.series_score1 == 2: return 0.88  # Team 1 up 2-0 (almost won)
            if state.series_score1 == 1: return 0.65  # Team 1 up 1-0
            if state.series_score2 == 2: return 0.12  # Team 2 up 2-0
            if state.series_score2 == 1: return 0.35  # Team 2 up 1-0

        return 0.50 # Default to 50/50 if scores are tied (0-0, 1-1)

    @staticmethod
    def series_win_probability(series_score_1: int, series_score_2: int, best_of: int = 3) -> float:
        """
        Calculate win probability based on series score (BO3/BO5).
        
        This is the "Map Momentum" edge - statistically, winning Map 1 
        in a BO3 gives ~65-70% win probability that markets often underprice.
        
        Based on historical esports data:
        - BO3 @ 1-0: Team leading has ~67% win rate
        - BO3 @ 2-0: Already won (100%)
        - BO5 @ 1-0: ~60% for leader
        - BO5 @ 2-0: ~75% for leader
        - BO5 @ 2-1: ~60% for leader
        """
        maps_to_win = (best_of // 2) + 1  # BO3 = 2, BO5 = 3
        
        # Check if series is already won
        if series_score_1 >= maps_to_win:
            return 1.0
        if series_score_2 >= maps_to_win:
            return 0.0
        
        # Calculate remaining maps needed
        team1_needs = maps_to_win - series_score_1
        team2_needs = maps_to_win - series_score_2
        
        # Historical probabilities based on esports data
        # Key: (team1_needs, team2_needs) -> team1 win probability
        bo3_probs = {
            (2, 2): 0.50,   # 0-0 start
            (1, 2): 0.67,   # 1-0 lead (THIS IS THE EDGE)
            (2, 1): 0.33,   # 0-1 down
            (1, 1): 0.50,   # 1-1 tied
        }
        
        bo5_probs = {
            (3, 3): 0.50,   # 0-0 start
            (2, 3): 0.60,   # 1-0 lead
            (3, 2): 0.40,   # 0-1 down
            (1, 3): 0.75,   # 2-0 lead (BIG EDGE)
            (3, 1): 0.25,   # 0-2 down
            (2, 2): 0.50,   # 1-1 tied
            (1, 2): 0.60,   # 2-1 lead
            (2, 1): 0.40,   # 1-2 down
            (1, 1): 0.50,   # 2-2 tied (final map)
        }
        
        probs = bo5_probs if best_of == 5 else bo3_probs
        return probs.get((team1_needs, team2_needs), 0.50)
    
    @classmethod
    def calculate(cls, state: GameState) -> float:
        """Calculate win probability based on game type."""
        if state.game_type == "lol":
            return cls.lol_win_probability(state)
        elif state.game_type == "cs2":
            return cls.cs2_win_probability(state)
        elif state.game_type == "dota2":
            return cls.dota2_win_probability(state)
        elif state.game_type == "valorant":
            # Valorant logic is identical to CS2 (Round based, 13 to win)
            return cls.cs2_win_probability(state)
        elif state.game_type in ["r6siege", "cod"]:
            # R6 and CoD are round-based like CS2
            return cls.cs2_win_probability(state)
        elif state.game_type == "rocket-league":
            # Rocket League: Score-based probability
            prob = 0.50
            score_diff = state.score_diff()
            # ~3% per goal difference
            prob += score_diff * 0.03
            return max(0.05, min(0.95, prob))
        else:
            # Fallback: Use score difference for unknown game types
            prob = 0.50
            score_diff = state.score_diff()
            prob += score_diff * 0.02  # Conservative 2% per point
            return max(0.05, min(0.95, prob))


# =============================================================================
# DATA PROVIDERS
# =============================================================================

class RiotEsportsAPI:
    """
    Official Riot eSports API for League of Legends live game data.
    FREE and provides real-time gold/kills for pro matches!
    
    This bypasses the PandaScore paywall by using Riot's own eSports feed.
    """
    
    def __init__(self):
        self.base_url = "https://esports-api.lolesports.com/persisted/gw"
        self.live_url = "https://feed.lolesports.com/livestats/v1"
        self.api_key = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"  # Public LoL Esports API key
        
    def get_live_events(self) -> List[Dict]:
        """Get currently live LoL esports events."""
        try:
            url = f"{self.base_url}/getLive"
            headers = {"x-api-key": self.api_key}
            params = {"hl": "en-US"}
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                events = data.get("data", {}).get("schedule", {}).get("events", [])
                live_events = [e for e in events if e.get("state") == "inProgress"]
                sys.stderr.write(f"🎮 RIOT ESPORTS: Found {len(live_events)} live LoL events\n"); sys.stderr.flush()
                return live_events
            return []
        except Exception as e:
            sys.stderr.write(f"🎮 RIOT ESPORTS error: {e}\n"); sys.stderr.flush()
            return []
    
    def get_live_game_stats(self, game_id: str) -> Optional[Dict]:
        """
        Get real-time game statistics (gold, kills, etc.) for a live game.
        This is the KEY data that PandaScore blocks on free tier!
        """
        try:
            # Try the live stats feed
            url = f"{self.live_url}/window/{game_id}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            
            # Fallback: try details endpoint
            url = f"{self.live_url}/details/{game_id}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
                
            return None
        except Exception as e:
            sys.stderr.write(f"🎮 RIOT LIVE STATS error for {game_id}: {e}\n"); sys.stderr.flush()
            return None
    
    def get_lol_game_state(self, match_info: Dict) -> Optional[GameState]:
        """
        Convert Riot eSports live data into a GameState for edge calculation.
        This gives us the GOLD LEAD data that PandaScore free tier blocks!
        """
        try:
            # Extract game ID from match info
            games = match_info.get("match", {}).get("games", [])
            current_game = None
            for game in games:
                if game.get("state") == "inProgress":
                    current_game = game
                    break
            
            if not current_game:
                return None
            
            game_id = current_game.get("id")
            if not game_id:
                return None
            
            # Fetch live stats
            stats = self.get_live_game_stats(game_id)
            if not stats:
                return None
            
            # Parse the frame data
            frames = stats.get("frames", [])
            if not frames:
                return None
            
            latest_frame = frames[-1]  # Most recent game state
            
            # Extract team data
            blue_team = latest_frame.get("blueTeam", {})
            red_team = latest_frame.get("redTeam", {})
            
            team1_gold = blue_team.get("totalGold", 0)
            team2_gold = red_team.get("totalGold", 0)
            team1_kills = blue_team.get("totalKills", 0)
            team2_kills = red_team.get("totalKills", 0)
            team1_towers = blue_team.get("towers", 0)
            team2_towers = red_team.get("towers", 0)
            game_time = latest_frame.get("gameTime", 0) // 1000  # Convert ms to seconds
            
            # Get team names from match info
            teams = match_info.get("match", {}).get("teams", [])
            team1_name = teams[0].get("name", "Blue") if len(teams) > 0 else "Blue"
            team2_name = teams[1].get("name", "Red") if len(teams) > 1 else "Red"
            
            sys.stderr.write(f"🎮 RIOT LIVE: {team1_name} ({team1_gold}g, {team1_kills}k) vs {team2_name} ({team2_gold}g, {team2_kills}k) @ {game_time//60}m\n")
            sys.stderr.flush()
            
            return GameState(
                game_type="lol",
                match_id=str(game_id),
                team1=team1_name,
                team2=team2_name,
                team1_score=team1_kills,
                team2_score=team2_kills,
                team1_gold=team1_gold,
                team2_gold=team2_gold,
                team1_objectives=team1_towers,
                team2_objectives=team2_towers,
                game_time=game_time,
                is_live=True,
                raw_data=stats
            )
            
        except Exception as e:
            sys.stderr.write(f"🎮 RIOT GameState error: {e}\n"); sys.stderr.flush()
            import traceback
            traceback.print_exc(file=sys.stderr)
            return None


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
        self._rate_limit_until = 0

    def get_live_matches(self) -> List[Dict]:
        """Get currently live LoL matches."""
        # Check Backoff
        if time.time() < self._rate_limit_until:
             sys.stderr.write(f"⏳ Pausing Pandascore (LoL) due to 429 until {self._rate_limit_until}\n"); sys.stderr.flush()
             return []

        sys.stderr.write(f"🔍 DEBUG: RiotAPIProvider.get_live_matches called, key exists: {bool(self.pandascore_key)}\n")
        sys.stderr.flush()
        # Try PandaScore for pro matches (easier API)
        if self.pandascore_key:
            try:
                url = "https://api.pandascore.co/lol/matches/running"
                headers = {"Authorization": f"Bearer {self.pandascore_key}"}
                sys.stderr.write(f"🔍 DEBUG: LoL API call to {url}\n"); sys.stderr.flush()
                resp = requests.get(url, headers=headers, timeout=10)
                sys.stderr.write(f"🔍 DEBUG: LoL API response status: {resp.status_code}\n"); sys.stderr.flush()
                if resp.status_code == 200:
                    matches = resp.json()
                    sys.stderr.write(f"🔍 DEBUG: Found {len(matches)} live LoL matches\n"); sys.stderr.flush()
                    if matches:
                        # Log sample match for debugging
                        sample = matches[0] if matches else {}
                        opps = sample.get("opponents", [])
                        if len(opps) >= 2:
                            t1 = opps[0].get("opponent", {}).get("name", "?")
                            t2 = opps[1].get("opponent", {}).get("name", "?")
                            sys.stderr.write(f"🔍 DEBUG: Sample LoL match: {t1} vs {t2}\n"); sys.stderr.flush()
                    return matches
                elif resp.status_code == 429:
                    sys.stderr.write(f"⚠️ PANDASCORE 429 (Too Many Requests) - Sleeping 60s\n"); sys.stderr.flush()
                    self._rate_limit_until = time.time() + 60
                    return []
                else:
                    sys.stderr.write(f"🔍 DEBUG: LoL API error {resp.status_code}: {resp.text[:200]}\n"); sys.stderr.flush()
            except Exception as e:
                sys.stderr.write(f"🔍 DEBUG: PandaScore LoL exception: {e}\n"); sys.stderr.flush()
                import traceback
                traceback.print_exc(file=sys.stderr)

        sys.stderr.write("🔍 DEBUG: LoL provider returning empty list\n"); sys.stderr.flush()
        return []
    
    def get_match_state(self, match_id: str) -> Optional[GameState]:
        """Get current state of a live LoL match with enhanced game data."""
        if not self.pandascore_key:
            sys.stderr.write(f"🔍 DEBUG: LoL match state skipped - no API key\n"); sys.stderr.flush()
            return None

        try:
            # First get match overview
            match_url = f"https://api.pandascore.co/lol/matches/{match_id}"
            headers = {"Authorization": f"Bearer {self.pandascore_key}"}
            resp = requests.get(match_url, headers=headers, timeout=10)

            if resp.status_code != 200:
                sys.stderr.write(f"🔍 DEBUG: LoL match state fetch failed: {resp.status_code} - {resp.text[:200]}\n"); sys.stderr.flush()
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
        self._rate_limit_until = 0
    
    def get_live_matches(self) -> List[Dict]:
        """Get currently live CS2 matches."""
        if time.time() < self._rate_limit_until:
             sys.stderr.write(f"⏳ Pausing Pandascore (CS2) due to 429 until {self._rate_limit_until}\n"); sys.stderr.flush()
             return []

        if self.pandascore_key:
            try:
                # Try both CS2 and CSGO endpoints (PandaScore may use different naming)
                urls = [
                    "https://api.pandascore.co/csgo/matches/running",
                    "https://api.pandascore.co/cs2/matches/running"
                ]
                
                for url in urls:
                    sys.stderr.write(f"🔍 DEBUG: CS2 API call to {url}\n"); sys.stderr.flush()
                    headers = {"Authorization": f"Bearer {self.pandascore_key}"}
                    resp = requests.get(url, headers=headers, timeout=10)
                    sys.stderr.write(f"🔍 DEBUG: CS2 API response status: {resp.status_code}\n"); sys.stderr.flush()
                    
                    if resp.status_code == 200:
                        matches = resp.json()
                        sys.stderr.write(f"🔍 DEBUG: Found {len(matches)} live CS2 matches from {url}\n"); sys.stderr.flush()
                        if matches:
                            return matches
                    elif resp.status_code == 429:
                        sys.stderr.write(f"⚠️ PANDASCORE CS2 429 - Sleeping 60s\n"); sys.stderr.flush()
                        self._rate_limit_until = time.time() + 60
                        return []
                    elif resp.status_code == 404:
                        # Endpoint doesn't exist, try next URL
                        sys.stderr.write(f"🔍 DEBUG: {url} returned 404, trying next endpoint\n"); sys.stderr.flush()
                        continue
                    else:
                        sys.stderr.write(f"🔍 DEBUG: CS2 API error {resp.status_code}: {resp.text[:200]}\n"); sys.stderr.flush()

            except Exception as e:
                sys.stderr.write(f"🔍 DEBUG: PandaScore CS2 exception: {e}\n"); sys.stderr.flush()
                import traceback
                traceback.print_exc(file=sys.stderr)
        
        sys.stderr.write("🔍 DEBUG: CS2 provider returning empty list\n"); sys.stderr.flush()
        return []
    
    def get_match_state(self, match_id: str) -> Optional[GameState]:
        """Get current state of a live CS2 match."""
        if not self.pandascore_key:
            return None
            
        try:
            # Try csgo endpoint first (PandaScore uses csgo for CS2)
            url = f"https://api.pandascore.co/csgo/matches/{match_id}"
            headers = {"Authorization": f"Bearer {self.pandascore_key}"}
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code != 200:
                sys.stderr.write(f"🔍 DEBUG: CS2 match state fetch failed: {resp.status_code} - {resp.text[:200]}\n"); sys.stderr.flush()
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


class ValorantDataProvider:
    """Fetches live Valorant match data."""
    
    def __init__(self):
        self.pandascore_key = os.getenv("PANDASCORE_API_KEY")
        self._rate_limit_until = 0
    
    def get_live_matches(self) -> List[Dict]:
        """Get currently live Valorant matches."""
        if time.time() < self._rate_limit_until:
             return []

        if self.pandascore_key:
            try:
                url = "https://api.pandascore.co/valorant/matches/running"
                headers = {"Authorization": f"Bearer {self.pandascore_key}"}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    sys.stderr.write(f"⚠️ PANDASCORE VAL 429 - Sleeping 60s\n"); sys.stderr.flush()
                    self._rate_limit_until = time.time() + 60

            except Exception as e:
                print(f"PandaScore Valorant error: {e}")
        
        return []
    
    def get_match_state(self, match_id: str) -> Optional[GameState]:
        """Get current state of a live Valorant match."""
        if not self.pandascore_key:
            return None
            
        try:
            url = f"https://api.pandascore.co/valorant/matches/{match_id}"
            headers = {"Authorization": f"Bearer {self.pandascore_key}"}
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code != 200:
                sys.stderr.write(f"🔍 DEBUG: Valorant match state fetch failed: {resp.status_code} - {resp.text[:200]}\n"); sys.stderr.flush()
                return None
                
            data = resp.json()
            opponents = data.get("opponents", [])
            if len(opponents) < 2:
                return None
                
            team1 = opponents[0].get("opponent", {}).get("name", "Team1")
            team2 = opponents[1].get("opponent", {}).get("name", "Team2")
            
            # Get current game
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
                game_type="valorant",
                match_id=match_id,
                team1=team1,
                team2=team2,
                team1_score=team1_score,
                team2_score=team2_score,
                is_live=data.get("status") == "running",
                raw_data=data
            )
            
        except Exception as e:
            sys.stderr.write(f"🔍 DEBUG: Valorant match state error: {e}\n"); sys.stderr.flush()
            return None


class Dota2DataProvider:
    """Fetches live Dota 2 match data."""
    
    def __init__(self):
        self.pandascore_key = os.getenv("PANDASCORE_API_KEY")
        self._rate_limit_until = 0
    
    def get_live_matches(self) -> List[Dict]:
        """Get currently live Dota 2 matches."""
        if time.time() < self._rate_limit_until:
            sys.stderr.write(f"⏳ Pausing Pandascore (Dota2) due to 429 until {self._rate_limit_until}\n"); sys.stderr.flush()
            return []

        if self.pandascore_key:
            try:
                url = "https://api.pandascore.co/dota2/matches/running"
                headers = {"Authorization": f"Bearer {self.pandascore_key}"}
                sys.stderr.write(f"🔍 DEBUG: Dota2 API call to {url}\n"); sys.stderr.flush()
                resp = requests.get(url, headers=headers, timeout=10)
                sys.stderr.write(f"🔍 DEBUG: Dota2 API response status: {resp.status_code}\n"); sys.stderr.flush()
                if resp.status_code == 200:
                    matches = resp.json()
                    sys.stderr.write(f"🔍 DEBUG: Found {len(matches)} live Dota2 matches\n"); sys.stderr.flush()
                    if matches:
                        sample = matches[0] if matches else {}
                        opps = sample.get("opponents", [])
                        if len(opps) >= 2:
                            t1 = opps[0].get("opponent", {}).get("name", "?")
                            t2 = opps[1].get("opponent", {}).get("name", "?")
                            sys.stderr.write(f"🔍 DEBUG: Sample Dota2 match: {t1} vs {t2}\n"); sys.stderr.flush()
                    return matches
                elif resp.status_code == 429:
                    sys.stderr.write(f"⚠️ PANDASCORE Dota2 429 - Sleeping 60s\n"); sys.stderr.flush()
                    self._rate_limit_until = time.time() + 60
                    return []
                else:
                    sys.stderr.write(f"🔍 DEBUG: Dota2 API error {resp.status_code}: {resp.text[:200]}\n"); sys.stderr.flush()
            except Exception as e:
                sys.stderr.write(f"🔍 DEBUG: PandaScore Dota2 exception: {e}\n"); sys.stderr.flush()
                import traceback
                traceback.print_exc(file=sys.stderr)
        
        sys.stderr.write("🔍 DEBUG: Dota2 provider returning empty list\n"); sys.stderr.flush()
        return []


class RainbowSixDataProvider:
    """Fetches live Rainbow Six Siege match data."""
    
    def __init__(self):
        self.pandascore_key = os.getenv("PANDASCORE_API_KEY")
        self._rate_limit_until = 0
    
    def get_live_matches(self) -> List[Dict]:
        """Get currently live Rainbow Six Siege matches."""
        if time.time() < self._rate_limit_until:
            return []

        if self.pandascore_key:
            try:
                url = "https://api.pandascore.co/r6siege/matches/running"
                headers = {"Authorization": f"Bearer {self.pandascore_key}"}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    sys.stderr.write(f"⚠️ PANDASCORE R6 429 - Sleeping 60s\n"); sys.stderr.flush()
                    self._rate_limit_until = time.time() + 60
            except Exception as e:
                sys.stderr.write(f"🔍 DEBUG: PandaScore R6 exception: {e}\n"); sys.stderr.flush()
        
        return []


class CallOfDutyDataProvider:
    """Fetches live Call of Duty match data."""
    
    def __init__(self):
        self.pandascore_key = os.getenv("PANDASCORE_API_KEY")
        self._rate_limit_until = 0
    
    def get_live_matches(self) -> List[Dict]:
        """Get currently live Call of Duty matches."""
        if time.time() < self._rate_limit_until:
            return []

        if self.pandascore_key:
            try:
                url = "https://api.pandascore.co/codmw/matches/running"
                headers = {"Authorization": f"Bearer {self.pandascore_key}"}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    sys.stderr.write(f"⚠️ PANDASCORE CoD 429 - Sleeping 60s\n"); sys.stderr.flush()
                    self._rate_limit_until = time.time() + 60
            except Exception as e:
                sys.stderr.write(f"🔍 DEBUG: PandaScore CoD exception: {e}\n"); sys.stderr.flush()
        
        return []


class RocketLeagueDataProvider:
    """Fetches live Rocket League match data."""
    
    def __init__(self):
        self.pandascore_key = os.getenv("PANDASCORE_API_KEY")
        self._rate_limit_until = 0
    
    def get_live_matches(self) -> List[Dict]:
        """Get currently live Rocket League matches."""
        if time.time() < self._rate_limit_until:
            return []

        if self.pandascore_key:
            try:
                url = "https://api.pandascore.co/rl/matches/running"
                headers = {"Authorization": f"Bearer {self.pandascore_key}"}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    sys.stderr.write(f"⚠️ PANDASCORE RL 429 - Sleeping 60s\n"); sys.stderr.flush()
                    self._rate_limit_until = time.time() + 60
            except Exception as e:
                sys.stderr.write(f"🔍 DEBUG: PandaScore RL exception: {e}\n"); sys.stderr.flush()
        
        return []

class EsportsDataAggregator:
    """Aggregates data from multiple esports APIs."""
    
    def __init__(self):
        self.lol_provider = RiotAPIProvider()
        self.cs2_provider = CS2DataProvider()
        self.val_provider = ValorantDataProvider()
        self.dota2_provider = Dota2DataProvider()
        self.r6_provider = RainbowSixDataProvider()
        self.cod_provider = CallOfDutyDataProvider()
        self.rl_provider = RocketLeagueDataProvider()
        # Official Riot eSports API for free live LoL stats!
        self.riot_esports = RiotEsportsAPI()
        self._riot_events_cache = {}  # Cache Riot live events for matching
        
    def get_all_live_matches(self) -> List[Dict]:
        """Get all currently live matches across games."""
        sys.stderr.write("🔍 DEBUG: get_all_live_matches called\n"); sys.stderr.flush()
        matches = []

        try:
            # LoL matches
            sys.stderr.write("🔍 DEBUG: Getting LoL matches...\n"); sys.stderr.flush()
            lol_matches = self.lol_provider.get_live_matches()
            sys.stderr.write(f"🔍 DEBUG: LoL provider returned {len(lol_matches)} matches\n"); sys.stderr.flush()
            for match in lol_matches:
                match["game_type"] = "lol"
                matches.append(match)

            # CS2 matches
            sys.stderr.write("🔍 DEBUG: Getting CS2 matches...\n"); sys.stderr.flush()
            cs2_matches = self.cs2_provider.get_live_matches()
            sys.stderr.write(f"🔍 DEBUG: CS2 provider returned {len(cs2_matches)} matches\n"); sys.stderr.flush()
            for match in cs2_matches:
                match["game_type"] = "cs2"
                matches.append(match)

            # Valorant matches
            sys.stderr.write("🔍 DEBUG: Getting Valorant matches...\n"); sys.stderr.flush()
            val_matches = self.val_provider.get_live_matches()
            sys.stderr.write(f"🔍 DEBUG: Valorant provider returned {len(val_matches)} matches\n"); sys.stderr.flush()
            for match in val_matches:
                match["game_type"] = "valorant"
                matches.append(match)

            # Dota 2 matches
            sys.stderr.write("🔍 DEBUG: Getting Dota2 matches...\n"); sys.stderr.flush()
            dota2_matches = self.dota2_provider.get_live_matches()
            sys.stderr.write(f"🔍 DEBUG: Dota2 provider returned {len(dota2_matches)} matches\n"); sys.stderr.flush()
            for match in dota2_matches:
                match["game_type"] = "dota2"
                matches.append(match)

            # Rainbow Six matches
            sys.stderr.write("🔍 DEBUG: Getting R6 matches...\n"); sys.stderr.flush()
            r6_matches = self.r6_provider.get_live_matches()
            sys.stderr.write(f"🔍 DEBUG: R6 provider returned {len(r6_matches)} matches\n"); sys.stderr.flush()
            for match in r6_matches:
                match["game_type"] = "r6siege"
                matches.append(match)

            # Call of Duty matches
            sys.stderr.write("🔍 DEBUG: Getting CoD matches...\n"); sys.stderr.flush()
            cod_matches = self.cod_provider.get_live_matches()
            sys.stderr.write(f"🔍 DEBUG: CoD provider returned {len(cod_matches)} matches\n"); sys.stderr.flush()
            for match in cod_matches:
                match["game_type"] = "cod"
                matches.append(match)

            # Rocket League matches
            sys.stderr.write("🔍 DEBUG: Getting RL matches...\n"); sys.stderr.flush()
            rl_matches = self.rl_provider.get_live_matches()
            sys.stderr.write(f"🔍 DEBUG: RL provider returned {len(rl_matches)} matches\n"); sys.stderr.flush()
            for match in rl_matches:
                match["game_type"] = "rocket-league"
                matches.append(match)

            sys.stderr.write(f"🔍 DEBUG: Total live matches found: {len(matches)}\n"); sys.stderr.flush()
        except Exception as e:
            sys.stderr.write(f"🔍 DEBUG: Exception in get_all_live_matches: {e}\n"); sys.stderr.flush()
            import traceback
            traceback.print_exc(file=sys.stderr)

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

    def get_match_state(self, match_id: str, game_type: str, raw_match: Dict = None) -> Optional[GameState]:
        """Get state for a specific match. Falls back to basic state from raw_match if detailed fetch fails."""
        state = None
        
        if game_type == "lol":
            # TRY 1: Official Riot eSports API (FREE, has gold/kills data!)
            state = self._try_riot_esports_for_lol(raw_match)
            if state:
                sys.stderr.write(f"🎮 RIOT ESPORTS: Got live LoL stats for {match_id}!\n"); sys.stderr.flush()
            else:
                # TRY 2: PandaScore (blocked on free tier, but try anyway)
                state = self.lol_provider.get_match_state(match_id)
        elif game_type == "cs2":
            state = self.cs2_provider.get_match_state(match_id)
        elif game_type == "valorant":
            state = self.val_provider.get_match_state(match_id)
        elif game_type == "dota2":
            state = self._get_dota2_match_state(match_id)
        elif game_type in ["r6siege", "cod", "rocket-league"]:
            state = self._get_basic_match_state(match_id, game_type)
        
        # Fallback: create basic state from raw running match data
        if state is None and raw_match:
            state = self._create_basic_state_from_raw(raw_match, game_type, match_id)
            if state:
                sys.stderr.write(f"🔍 DEBUG: Using fallback basic state for {match_id}\n"); sys.stderr.flush()
        
        return state
    
    def _try_riot_esports_for_lol(self, raw_match: Dict) -> Optional[GameState]:
        """Try to get LoL live stats from official Riot eSports API."""
        if not raw_match:
            return None
        
        try:
            # Get team names from PandaScore match
            opponents = raw_match.get("opponents", [])
            if len(opponents) < 2:
                return None
            
            team1_name = opponents[0].get("opponent", {}).get("name", "")
            team2_name = opponents[1].get("opponent", {}).get("name", "")
            
            # Fetch live events from Riot eSports API
            live_events = self.riot_esports.get_live_events()
            
            # Try to find a matching event
            for event in live_events:
                match_info = event.get("match", {})
                teams = match_info.get("teams", [])
                if len(teams) < 2:
                    continue
                
                riot_team1 = teams[0].get("name", "")
                riot_team2 = teams[1].get("name", "")
                
                # Fuzzy match team names
                if self._teams_match(team1_name, team2_name, riot_team1, riot_team2):
                    sys.stderr.write(f"🎮 RIOT: Matched {team1_name} vs {team2_name} to Riot event!\n")
                    sys.stderr.flush()
                    return self.riot_esports.get_lol_game_state(event)
            
            return None
            
        except Exception as e:
            sys.stderr.write(f"🎮 RIOT match error: {e}\n"); sys.stderr.flush()
            return None
    
    def _teams_match(self, ps_team1: str, ps_team2: str, riot_team1: str, riot_team2: str) -> bool:
        """Check if PandaScore teams match Riot teams (order-independent, fuzzy)."""
        def normalize(name: str) -> str:
            return name.lower().replace(" ", "").replace("esports", "").replace("gaming", "")
        
        ps1, ps2 = normalize(ps_team1), normalize(ps_team2)
        r1, r2 = normalize(riot_team1), normalize(riot_team2)
        
        # Check both orderings
        return (ps1 in r1 or r1 in ps1) and (ps2 in r2 or r2 in ps2) or \
               (ps1 in r2 or r2 in ps1) and (ps2 in r1 or r1 in ps2)
    
    def _create_basic_state_from_raw(self, raw_match: Dict, game_type: str, match_id: str) -> Optional[GameState]:
        """Create a basic GameState from raw running match data when detailed fetch fails."""
        try:
            opponents = raw_match.get("opponents", [])
            if len(opponents) < 2:
                return None
            
            team1 = opponents[0].get("opponent", {}).get("name", "Team1")
            team2 = opponents[1].get("opponent", {}).get("name", "Team2")
            team1_id = opponents[0].get("opponent", {}).get("id")
            team2_id = opponents[1].get("opponent", {}).get("id")
            
            # Get SERIES scores from results (maps/games WON in BO3/BO5)
            # This is the key data for Series Momentum trading!
            results = raw_match.get("results", [])
            series_score1 = 0
            series_score2 = 0

            for result in results:
                team_id = result.get("team_id")
                score = result.get("score", 0)
                if team_id == team1_id:
                    series_score1 = score
                elif team_id == team2_id:
                    series_score2 = score

            # Get series format (BO1, BO3, BO5)
            number_of_games = raw_match.get("number_of_games", 3)
            
            # Check for current game stats (gold, kills) from games array
            team1_gold = 0
            team2_gold = 0
            team1_kills = 0
            team2_kills = 0
            game_time = 0
            
            games = raw_match.get("games", [])
            for game in games:
                if game.get("status") == "running":
                    # Found the running game - extract stats
                    teams = game.get("teams", [])
                    if len(teams) >= 2:
                        team1_kills = teams[0].get("kills", 0)
                        team2_kills = teams[1].get("kills", 0)
                        team1_gold = teams[0].get("gold", 0) or teams[0].get("gold_earned", 0)
                        team2_gold = teams[1].get("gold", 0) or teams[1].get("gold_earned", 0)
                    game_time = game.get("length", 0)
                    break
            
            series_info = f"BO{number_of_games} @ {series_score1}-{series_score2}" if number_of_games > 1 else "BO1"
            sys.stderr.write(f"🔍 DEBUG: Fallback state for {match_id}: {team1} vs {team2} | {series_info} | Gold: {team1_gold}-{team2_gold}, Kills: {team1_kills}-{team2_kills}\n"); sys.stderr.flush()
            
            return GameState(
                game_type=game_type,
                match_id=match_id,
                team1=team1,
                team2=team2,
                team1_score=team1_kills,  # In-game kills/rounds (may be 0)
                team2_score=team2_kills,
                team1_gold=team1_gold,
                team2_gold=team2_gold,
                game_time=game_time,
                is_live=raw_match.get("status") == "running",
                raw_data=raw_match,
                # Series info for momentum trading
                series_score1=series_score1,
                series_score2=series_score2,
                number_of_games=number_of_games
            )
        except Exception as e:
            sys.stderr.write(f"🔍 DEBUG: Failed to create basic state: {e}\n"); sys.stderr.flush()
            import traceback
            traceback.print_exc(file=sys.stderr)
            return None
    
    def _get_dota2_match_state(self, match_id: str) -> Optional[GameState]:
        """Get Dota2 match state (similar to LoL)."""
        if not self.dota2_provider.pandascore_key:
            return None
        
        try:
            url = f"https://api.pandascore.co/dota2/matches/{match_id}"
            headers = {"Authorization": f"Bearer {self.dota2_provider.pandascore_key}"}
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code != 200:
                sys.stderr.write(f"🔍 DEBUG: Dota2 match state fetch failed: {resp.status_code} - {resp.text[:200]}\n"); sys.stderr.flush()
                return None
            
            data = resp.json()
            opponents = data.get("opponents", [])
            if len(opponents) < 2:
                return None
            
            team1 = opponents[0].get("opponent", {}).get("name", "Team1")
            team2 = opponents[1].get("opponent", {}).get("name", "Team2")
            
            # Get current game stats
            games = data.get("games", [])
            current_game = None
            for game in games:
                if game.get("status") == "running":
                    current_game = game
                    break
            
            if not current_game:
                return GameState(
                    game_type="dota2",
                    match_id=match_id,
                    team1=team1,
                    team2=team2,
                    is_live=data.get("status") == "running",
                    raw_data=data
                )
            
            # Parse game stats
            team1_data = current_game.get("teams", [{}])[0] if current_game.get("teams") else {}
            team2_data = current_game.get("teams", [{}])[1] if len(current_game.get("teams", [])) > 1 else {}
            
            return GameState(
                game_type="dota2",
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
            sys.stderr.write(f"🔍 DEBUG: Dota2 match state error: {e}\n"); sys.stderr.flush()
            return None
    
    def _get_basic_match_state(self, match_id: str, game_type: str) -> Optional[GameState]:
        """Get basic match state for R6, CoD, RL (score-based only)."""
        pandascore_key = os.getenv("PANDASCORE_API_KEY")
        if not pandascore_key:
            return None
        
        try:
            # Map game types to PandaScore API endpoints
            endpoint_map = {
                "r6siege": "r6siege",
                "cod": "codmw",
                "rocket-league": "rl"  # PandaScore uses 'rl' not 'rocket-league'
            }
            endpoint = endpoint_map.get(game_type, game_type)
            
            url = f"https://api.pandascore.co/{endpoint}/matches/{match_id}"
            headers = {"Authorization": f"Bearer {pandascore_key}"}
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code != 200:
                sys.stderr.write(f"🔍 DEBUG: {game_type} match state fetch failed: {resp.status_code} - {resp.text[:200]}\n"); sys.stderr.flush()
                return None
            
            data = resp.json()
            opponents = data.get("opponents", [])
            if len(opponents) < 2:
                return None
            
            team1 = opponents[0].get("opponent", {}).get("name", "Team1")
            team2 = opponents[1].get("opponent", {}).get("name", "Team2")
            
            # Get current game/map scores
            games = data.get("games", [])
            current_game = None
            for game in games:
                if game.get("status") == "running":
                    current_game = game
                    break
            
            team1_score = 0
            team2_score = 0
            
            if current_game:
                # Extract scores from current game
                results = data.get("results", [])
                for result in results:
                    if result.get("team_id") == opponents[0].get("opponent", {}).get("id"):
                        team1_score = result.get("score", 0)
                    elif result.get("team_id") == opponents[1].get("opponent", {}).get("id"):
                        team2_score = result.get("score", 0)
            
            return GameState(
                game_type=game_type,
                match_id=match_id,
                team1=team1,
                team2=team2,
                team1_score=team1_score,
                team2_score=team2_score,
                is_live=data.get("status") == "running",
                raw_data=data
            )
        except Exception as e:
            sys.stderr.write(f"🔍 DEBUG: {game_type} match state error: {e}\n"); sys.stderr.flush()
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
        """Place an order on Polymarket using the shared Gnosis-safe wrapper."""
        # Use the shared wrapper which handles Proxy Wallet signatures correctly
        return self.pm.place_limit_order(token_id, price, size, side)


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

        # Initialize Shared Context
        try:
            self.context = get_context()
            self.LLMActivity = LLMActivity
        except Exception as e:
            print(f"⚠️ Context init failed: {e}")
            self.context = None
            self.LLMActivity = None

        # State
        self.positions = {}  # market_id -> position data, token_id -> position data
        self.session_trades = 0
        self.session_pnl = 0.0

        # WALLET SYNC: Load existing positions to prevent duplicates
        try:
            import requests
            # Use Polymarket Data API directly (same as dashboard)
            dashboard_wallet = os.getenv("DASHBOARD_WALLET", "0xdb1f88Ab5B531911326788C018D397d352B7265c")
            url = f"https://data-api.polymarket.com/positions?user={dashboard_wallet}"
            resp = requests.get(url, timeout=10)

            if resp.status_code == 200:
                current_positions = resp.json()
                synced_count = 0
                for pos in current_positions:
                    # Track by asset_id (token contract) to prevent duplicate positions
                    asset_id = pos.get('asset', '')  # This is the token contract address
                    if asset_id and float(pos.get('size', 0)) > 0:  # Only track positions with size > 0
                        self.positions[asset_id] = {
                            'size': float(pos.get('size', 0)),
                            'value': float(pos.get('currentValue', 0)),
                            'cost': float(pos.get('cost', 0)),
                            'outcome': pos.get('outcome', ''),
                            'market': pos.get('title', pos.get('question', 'Unknown')),
                            'synced': True  # Mark as synced from wallet
                        }
                        synced_count += 1
                print(f"✅ WALLET SYNC: Loaded {synced_count} existing positions from Polymarket")
            else:
                print(f"⚠️ WALLET SYNC: API error {resp.status_code} - continuing without sync")
        except Exception as e:
            print(f"⚠️ WALLET SYNC: Could not sync existing positions: {e}")
            # Continue anyway - better to trade with potential duplicates than not trade at all

        # API Rate Limiting
        self.last_request_time = 0
        self.api_requests_this_hour = 0
        self.api_requests_this_minute = 0
        self.hour_start_time = time.time()
        self.minute_start_time = time.time()
        
        # Tiered Polling State
        self.last_live_poll = 0
        self.whale_watch_only = False
        self.last_activity_log = 0
        
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
        print(f"Min Edge: {MIN_EDGE_PERCENT}% (from {'env var' if os.getenv('MIN_EDGE_PERCENT') else 'default'})")
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
    
    def match_market_to_live_game(self, market: PolymarketMatch, live_matches: List[Dict]) -> Tuple[Optional[Dict], bool]:
        """
        Try to match a Polymarket market to a live game.
        Uses improved fuzzy matching with team name normalization.
        
        Returns:
            Tuple of (match, is_reversed) where:
            - match: The PandaScore match dict, or None if no match found
            - is_reversed: True if teams matched in reverse order (PM Team1 = PS Team2)
        """
        def normalize_team_name(name: str) -> str:
            """Normalize team names for better matching."""
            name = name.lower().strip()
            # Remove common suffixes/prefixes
            name = name.replace(" esports", "").replace(" gaming", "").replace(" gaming esports", "")
            name = name.replace(" esport", "").replace(" e-sports", "")
            # Remove special characters
            name = name.replace(".", "").replace("-", " ").replace("_", " ")
            # Remove extra spaces
            name = " ".join(name.split())
            return name
        
        def fuzzy_match(team1: str, team2: str) -> bool:
            """Check if two team names match using fuzzy logic."""
            t1_norm = normalize_team_name(team1)
            t2_norm = normalize_team_name(team2)
            
            # Exact match after normalization
            if t1_norm == t2_norm:
                return True
            
            # Substring match (either direction)
            if t1_norm in t2_norm or t2_norm in t1_norm:
                return True
            
            # Word-based matching (check if key words match)
            t1_words = set(t1_norm.split())
            t2_words = set(t2_norm.split())
            # Remove common words
            common_words = {"team", "the", "and", "of", "vs", "v"}
            t1_words -= common_words
            t2_words -= common_words
            
            # If significant overlap in key words, consider it a match
            if len(t1_words) > 0 and len(t2_words) > 0:
                overlap = len(t1_words & t2_words)
                min_words = min(len(t1_words), len(t2_words))
                if overlap >= min_words * 0.6:  # 60% word overlap
                    return True
            
            return False
        
        market_team1 = market.team1
        market_team2 = market.team2
        
        for match in live_matches:
            opponents = match.get("opponents", [])
            if len(opponents) < 2:
                continue
            
            live_team1 = opponents[0].get("opponent", {}).get("name", "")
            live_team2 = opponents[1].get("opponent", {}).get("name", "")
            
            # Check if teams match (improved fuzzy)
            team1_match = fuzzy_match(market_team1, live_team1)
            team2_match = fuzzy_match(market_team2, live_team2)
            
            # Also check reversed order
            team1_match_rev = fuzzy_match(market_team1, live_team2)
            team2_match_rev = fuzzy_match(market_team2, live_team1)
            
            # Log matching attempts for first few markets (diagnostic)
            if hasattr(self, '_match_diagnostic_count'):
                self._match_diagnostic_count += 1
            else:
                self._match_diagnostic_count = 1
            
            # CRITICAL FIX: Track if teams matched in reverse order
            is_reversed = (team1_match_rev and team2_match_rev)
            
            if self._match_diagnostic_count <= 5:
                print(f"      🔍 Match Diagnostic: PM '{market_team1}' vs '{market_team2}' | PS '{live_team1}' vs '{live_team2}'")
                print(f"         Normalized: PM '{normalize_team_name(market_team1)}' vs '{normalize_team_name(market_team2)}'")
                print(f"         Normalized: PS '{normalize_team_name(live_team1)}' vs '{normalize_team_name(live_team2)}'")
                print(f"         Match: T1={team1_match}, T2={team2_match}, Rev={is_reversed}")
            
            if (team1_match and team2_match) or is_reversed:
                if self._match_diagnostic_count <= 5:
                    reversed_str = " (REVERSED)" if is_reversed else ""
                    print(f"         ✅ MATCH FOUND!{reversed_str}")
                return match, is_reversed
        
        return None, False
    
    def calculate_bet_size(self, ev: float = 0.10, price: float = 0.50, cap_override: float = None) -> float:
        """
        Calculate bet size using Half-Kelly Criterion.
        
        Scaling Rules:
        - Current ($77): $10 max with limit orders
        - Growth ($150+): $15 via Half-Kelly  
        - Stealth ($300+): $15-50 capped at 15% order book depth
        - 🐋 Whale Detected: Dynamic cap up to $500
        """
        try:
            self.balance = self.pm_esports.pm.get_usdc_balance()
        except:
            pass

        # Use risk engine for Kelly-based sizing
        from agents.utils.risk_engine import kelly_size
        
        # 40% of wallet allocated to esports
        esports_allocation = self.balance * BET_PERCENT
        
        if esports_allocation < MIN_BET_USD:
            print(f"   ⚠️ Insufficient esports allocation: ${esports_allocation:.2f} (need ${MIN_BET_USD})")
            return 0
        
        # Calculate Kelly size with invisibility cap
        if cap_override:
             invisibility_cap = cap_override
        else:
            # Scale cap based on balance tiers
            if self.balance < 150:
                invisibility_cap = 10.0
            elif self.balance < 300:
                invisibility_cap = 15.0
            else:
                invisibility_cap = 50.0
        
        size = kelly_size(esports_allocation, ev, price, 
                         max_risk_pct=0.10, invisibility_cap=invisibility_cap)
        
        # Gap D: Balance Safety Cap (Never bet more than 20% of TOTAL balance)
        SAFETY_CAP_USD = self.balance * 0.20
        if size > SAFETY_CAP_USD:
            print(f"   ⚠️ Capping size to 20% of balance: ${SAFETY_CAP_USD:.2f} (was ${size:.2f})")
            size = SAFETY_CAP_USD

        print(f"   📊 Kelly Size: ${size:.2f} (balance: ${self.balance:.2f}, cap: ${invisibility_cap})")
        return size
    
    KNOWN_PROS = [
        "0x6a72f61820b26b1fe4d956e17b6dc2a1ea3033ee", # kch123
        "0x16b29c50f2439faf627209b2ac0c7bbddaa8a881", # SeriouslySirius
        "0xdb27bf2ac5d428a9c63dbc914611036855a6c56e", # DrPufferfish
        "0x37e4728b3c4607fb2b3b205386bb1d1fb1a8c991", # SemyonMarmeladov
        "0x507e52ef684ca2dd91f90a9d26d149dd3288beae", # GamblingIsAllYouNeed
        "0x204f72f35326db932158cba6adff0b9a1da95e14", # swisstony
        "0xe90bec87d9ef430f27f9dcfe72c34b76967d5da2", # gmanas
    ]
    
    def get_market_whales(self, token_id: str) -> bool:
        """
        Dynamically finds if any 'Smart Money' is in this specific market.
        Returns True if a known pro OR organic whale (>10% supply) is found.
        """
        try:
            # Endpoint: https://data-api.polymarket.com/token-holders?token_id=...
            # Note: Using raw requests to match existing codebase style for Data API
            # Gap C: Reduce timeout to 2s to catch Teemu latency window
            url = f"https://data-api.polymarket.com/token-holders?token_id={token_id}"
            resp = requests.get(url, timeout=2)
            
            if resp.status_code != 200:
                return False
                
            holders = resp.json()
            if not holders:
                return False
                
            for holder in holders[:10]: # Check top 10 holders
                address = holder.get('address', '').lower()
                percent = float(holder.get('percentage', 0))
                
                # Logic A: Known Pro
                if address in self.KNOWN_PROS:
                    print(f"   🐋 WHALE DETECTED (Known Pro): {address[:8]}...")
                    return True
                
                # Logic B: Organic Whale (>10% supply)
                if percent > 0.10:
                    print(f"   🐋 WHALE DETECTED (Organic): {address[:8]}... owns {percent*100:.1f}%")
                    return True
                    
        except Exception as e:
            print(f"   ⚠️ Whale check failed: {e}")
            
        return False
        
    def check_liquidity_depth(self, token_id: str, desired_size_usd: float) -> float:
        """
        Check order book depth to ensure we don't wipe out liquidity.
        Returns the capped size (max 15% of available ask liquidity).
        """
        try:
            book = self.pm_esports.pm.client.get_order_book(token_id)
            if not book or not book.asks:
                return 0.0 # No liquidity
            
            # Sum up total available liquidity in the order book (ASKS)
            # Since we are buying, we consume asks.
            total_liquidity = 0.0
            for ask in book.asks:
                try:
                    price = float(ask.price)
                    size = float(ask.size)
                    total_liquidity += price * size
                except: pass
                
            # Cap at 15% of total liquidity
            max_safe_size = total_liquidity * 0.15
            
            # Log if constrained
            if desired_size_usd > max_safe_size:
                # print(f"   💧 Liquidity Check: Desired ${desired_size_usd:.2f} > 15% of ${total_liquidity:.2f} (${max_safe_size:.2f})")
                pass
                
            return min(desired_size_usd, max_safe_size)
            
        except Exception as e:
            print(f"   ⚠️ Liquidity check failed: {e}")
            # Fail safe: assume low liquidity if check fails
            return min(desired_size_usd, 10.0) 

    def execute_trade(self, market: PolymarketMatch, side: str, our_prob: float, market_prob: float) -> bool:
        """Execute a trade with safety checks and Kelly sizing."""
        
        # 0. SAFETY: Check for existing open orders on this token (Prevent Charlton Loop)
        token_id = market.yes_token if side == "YES" else market.no_token
        try:
            open_orders = self.pm_esports.pm.get_open_orders()
            if any(o.get('asset_id') == token_id for o in open_orders):
                print(f"   ⚠️ Open order already exists for {market.team1} vs {market.team2}. Skipping.")
                return False
        except Exception as e:
            print(f"   ⚠️ Failed to check open orders: {e}")
            # Fail safe: don't trade if we can't verify open orders
            return False

        # 1. Calc Edge & EV
        edge = our_prob - market_prob
        # Simple EV approx: (Win Prob * Profit) - (Loss Prob * Risk)
        # Profit = (1 - price), Risk = price
        # EV = (our_prob * (1 - market_prob)) - ((1 - our_prob) * market_prob)
        # Simplified for sizing: just pass the raw edge as EV proxy or use proper calc
        entry_price = min(0.95, market.yes_price + 0.01) if side == "YES" else min(0.95, market.no_price + 0.01)
        
        # Calculate EV for Kelly
        potential_profit = 1.0 - entry_price
        ev = (our_prob * potential_profit) - ((1.0 - our_prob) * entry_price)

        # 1.5. Dynamic Whale Search
        # If we have a Teemu signal (Edge > 0), check for Smart Money to scale up
        cap_override = None
        whale_found = False
        try:
            if self.get_market_whales(token_id):
                whale_found = True
                cap_override = 500.0 # Boost to $500 if trusting a whale
        except: pass
        
        # 2. Get Sizing
        bet_size = self.calculate_bet_size(ev=ev, price=entry_price, cap_override=cap_override)
        
        # Check if size is 0
        if bet_size == 0:
            print(f"   ⚠️ Bet size calculated as 0 (EV: {ev:.3f}, Price: {entry_price:.3f})")
            return False
            
        # Gap A: Liquidity Depth Check (Prevent wiping the book)
        liquidity_cap = self.check_liquidity_depth(token_id, bet_size)
        if liquidity_cap < bet_size:
            print(f"   ⚠️ Liquidity constrained: Capping size to ${liquidity_cap:.2f} (15% of depth)")
            bet_size = liquidity_cap
            
        # Re-check 0 after liquidity cap
        if bet_size < 1.0: # Minimum viable bet
            print(f"   ⚠️ Bet size too small after liquidity cap: ${bet_size:.2f}")
            return False

        shares = bet_size / entry_price
        edge_pct = abs(edge) * 100
        
        print(f"\n🎯 TRADE: {side} on {market.team1} vs {market.team2}")
        print(f"   Our Prob: {our_prob*100:.1f}% | Market: {market_prob*100:.1f}% | Edge: +{edge_pct:.1f}%")
        print(f"   Entry: ${entry_price:.3f} | Size: ${bet_size:.2f} | Shares: {shares:.1f}")
        if whale_found:
             print(f"   🐋 SIZE BOOSTED due to Whale Presence")
        
        if self.dry_run:
            print(f"   [DRY RUN] Would execute trade")
            self.session_trades += 1
            return True
        
        # 3. Execute
        result = self.pm_esports.place_order(token_id, "BUY", entry_price, shares)
        
        if result.get("success") or result.get("status") == "matched":
            print(f"   ✅ FILLED!")
            self.session_trades += 1
            # Store position by market_id (for dashboard)
            self.positions[market.market_id] = {
                "side": side,
                "entry_price": entry_price,
                "shares": shares,
                "entry_time": datetime.datetime.now().isoformat()
            }

            # Also store by token_id (for wallet sync duplicate prevention)
            self.positions[token_id] = {
                "market_id": market.market_id,
                "side": side,
                "entry_price": entry_price,
                "shares": shares,
                "entry_time": datetime.datetime.now().isoformat(),
                "synced": False  # Mark as newly created position
            }

            # Store conflict key to prevent betting on other outcomes of same match
            match_conflict_key = f"{state.match_id}_active"
            self.positions[match_conflict_key] = {
                "market_id": market.market_id,
                "outcome": side,
                "entry_price": entry_price,
                "shares": shares,
                "entry_time": datetime.datetime.now().isoformat(),
                "strategy": strategy_name
            }
            
            # Log successful trade to LLM Terminal
            if self.context and self.LLMActivity and hasattr(self, 'context'):
                try:
                    import uuid
                    reasoning_log = f"Edge: {edge_pct:.1f}% | EV: {ev:.3f} | Size: ${bet_size:.2f}"
                    if whale_found:
                        reasoning_log += " | 🐋 Whale Follow (Cap $500)"
                        
                    self.context.log_llm_activity(self.LLMActivity(
                        id=str(uuid.uuid4())[:8],
                        agent="esports_trader",
                        action_type="trade",
                        market_question=f"{market.team1} vs {market.team2}",
                        prompt_summary=f"Placing {side} bet",
                        reasoning=reasoning_log,
                        conclusion="BET",
                        confidence=our_prob,
                        data_sources=["PandaScore", "Polymarket", "WhaleRadar"],
                        duration_ms=0
                    ))
                except: pass
                
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
        sys.stderr.write("🚨🚨🚨 DEBUG: scan_and_trade() method called! 🚨🚨🚨\n"); sys.stderr.flush()
        print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🔍 Scanning esports markets...")

        # HEARTBEAT LOG - proves agent is alive and Supabase works
        try:
            from agents.utils.supabase_client import get_supabase_state
            supa = get_supabase_state()
            if supa:
                supa.log_llm_activity(
                    agent="esports_trader",
                    action_type="heartbeat",
                    market_question="Scanning esports markets...",
                    prompt_summary="Heartbeat - Agent Active",
                    reasoning=f"Mode: {'LIVE' if not self.dry_run else 'DRY RUN'}, Session trades: {self.session_trades}",
                    conclusion="SCANNING",
                    confidence=1.0,
                    data_sources=["PandaScore", "Polymarket"],
                    tokens_used=0,
                    cost_usd=0,
                    duration_ms=0
                )
                print(f"   🟢 Heartbeat logged to Supabase")
        except Exception as e:
            print(f"   ⚠️ Heartbeat failed: {e}")

        # 0. Check Rate Limits First (this also resets hourly counters)
        rate_limit_sleep = self.check_rate_limits()
        if rate_limit_sleep > 0:
            print(f"   ⏸️ Rate limit check: Sleeping {rate_limit_sleep}s")
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

        sys.stderr.write(f"🔍 DEBUG: About to call get_all_live_matches(), pandascore_available={pandascore_available}\n"); sys.stderr.flush()
        
        # Smart Polling Logic (Tiered Prioritization)
        current_time = time.time()
        
        # Reset counters if hour has passed (CRITICAL: Must check BEFORE calculating ratio)
        if current_time - self.hour_start_time >= REQUEST_COUNT_RESET_HOUR:
            self.api_requests_this_hour = 0
            self.hour_start_time = current_time
            print(f"   🔄 Hourly API counter reset")
        
        usage_ratio = self.api_requests_this_hour / MAX_REQUESTS_PER_HOUR
        
        # Determine Poll Interval based on Tiers
        has_active_positions = len(self.positions) > 0
        
        if usage_ratio > 0.95:
             # Tier 4: EXHAUSTED -> Whale Watch Only
             self.whale_watch_only = True
             poll_interval = 300 # 5m
             print(f"   ⛔ API LIMIT HIT ({self.api_requests_this_hour}/{MAX_REQUESTS_PER_HOUR}) - Entering Whale-Watch Only Mode")
        elif usage_ratio > 0.80:
             # Tier 3: BACK-OFF -> 2m
             poll_interval = 120
             print(f"   ⚠️ High API Usage ({self.api_requests_this_hour}/{MAX_REQUESTS_PER_HOUR}, {usage_ratio*100:.1f}%) - Backing off to 120s polling")
        elif has_active_positions:
             # Tier 1: Active Positions -> 15s (Check for exits)
             poll_interval = 15
             print(f"   🎯 Active positions detected - Polling every 15s for exits")
        else:
             # Tier 2: Standard Live Scan -> 45s
             poll_interval = 45
             print(f"   🔍 Standard discovery mode - Polling every 45s (Usage: {self.api_requests_this_hour}/{MAX_REQUESTS_PER_HOUR}, {usage_ratio*100:.1f}%)")
             
        time_since_last = current_time - self.last_live_poll
        # Force poll on first scan (last_live_poll = 0) or if enough time has passed
        should_poll = (self.last_live_poll == 0) or (time_since_last >= poll_interval)
        
        if not should_poll:
            print(f"   ⏳ Smart Polling: Skipping Data API ({time_since_last:.1f}s / {poll_interval}s)")
            return POLL_INTERVAL_LIVE # Return early instead of processing with empty data
        else:
            print(f"   📡 Fetching live match data from PandaScore (poll_interval: {poll_interval}s)...")
            try:
                live_matches = self.data_aggregator.get_all_live_matches()
                self.last_live_poll = current_time
                self.whale_watch_only = False
                
                # Track API usage: get_all_live_matches() makes 7 API calls (LoL, CS2, Valorant, Dota2, R6, CoD, RL)
                self.increment_request_count()  # LoL
                self.increment_request_count()  # CS2
                self.increment_request_count()  # Valorant
                self.increment_request_count()  # Dota2
                self.increment_request_count()  # R6
                self.increment_request_count()  # CoD
                self.increment_request_count()  # RL
                print(f"   ✅ Found {len(live_matches)} live matches in data feed")
                print(f"   📊 API Usage: {self.api_requests_this_hour}/{MAX_REQUESTS_PER_HOUR} ({self.api_requests_this_hour/MAX_REQUESTS_PER_HOUR*100:.1f}%)")
                sys.stderr.write(f"   found {len(live_matches)} active games in data feed\n"); sys.stderr.flush()
            except Exception as e:
                print(f"   ⚠️ Data feed error: {e}")
                sys.stderr.write(f"   ⚠️ Data feed error: {e}\n"); sys.stderr.flush()
                # Don't disable entire trading, just skip this turn
                live_matches = []

        trades_made = 0
        match_state_cache = {} # Local cache for this scan cycle to batch requests
        matched_count = 0
        analyzed_count = 0
        
        print(f"   🔍 Processing {len(markets)} markets with {len(live_matches)} live matches...")

        # DEBUG: Log first few live matches to see what we're working with
        if live_matches and len(live_matches) > 0:
            print(f"   📋 Sample live matches:")
            for i, match in enumerate(live_matches[:3]):
                opponents = match.get("opponents", [])
                if len(opponents) >= 2:
                    t1 = opponents[0].get("opponent", {}).get("name", "?")
                    t2 = opponents[1].get("opponent", {}).get("name", "?")
                    game = match.get("game_type", "unknown")
                    print(f"      {i+1}. {t1} vs {t2} ({game})")

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

                # ACTIVATE BRAIN: Even arbitrage needs validation
                if self.validator:
                    target_price = yes_price if target_side == "YES" else no_price
                    should_trade, reason, confidence = self.validator.validate(
                        market.question, target_side, target_price, fast_mode=True)
                    if not should_trade:
                        print(f"      🧠 ARBITRAGE BLOCKED: {reason}")
                        continue

                if self.execute_trade(market, target_side, 0.99, yes_price if target_side=="YES" else no_price):
                    trades_made += 1
                continue

            # --- CHECK 2: FILTER GARBAGE ---
            if yes_price > 0.95 or no_price > 0.95: continue # Too expensive
            if yes_price < 0.08 or no_price < 0.08: continue # Too cheap/lotto

            # --- CHECK 3: HYBRID TRADING LOGIC ---

            # Match Market -> Live Data (when available)
            # CRITICAL FIX: Now returns (match, is_reversed) tuple
            live_match, is_reversed = self.match_market_to_live_game(market, live_matches)
            
            if live_match:
                matched_count += 1
                # Log all matches for visibility (helps diagnose matching issues)
                opponents = live_match.get("opponents", [])
                ps_team1 = opponents[0].get("opponent", {}).get("name", "Unknown") if len(opponents) > 0 else "Unknown"
                ps_team2 = opponents[1].get("opponent", {}).get("name", "Unknown") if len(opponents) > 1 else "Unknown"
                reversed_str = " (REVERSED)" if is_reversed else ""
                print(f"   ✅ Matched #{matched_count}: PM '{market.team1}' vs '{market.team2}' -> PS '{ps_team1}' vs '{ps_team2}'{reversed_str}")

                # DEBUG: Show series scores if available
                results = live_match.get("results", [])
                if results:
                    print(f"      📊 Series: {ps_team1} {results[0].get('score', 0)} - {results[1].get('score', 0)} {ps_team2}")
            else:
                # DEBUG: Show why first market didn't match (helps diagnose)
                if markets.index(market) == 0 and live_matches:
                    print(f"   🔍 DEBUG: Market '{market.team1}' vs '{market.team2}' not found in:")
                    for i, lm in enumerate(live_matches[:3]):
                        opps = lm.get("opponents", [])
                        if len(opps) >= 2:
                            lt1 = opps[0].get("opponent", {}).get("name", "?")
                            lt2 = opps[1].get("opponent", {}).get("name", "?")
                            print(f"      {i+1}. '{lt1}' vs '{lt2}'")

            if live_match and live_matches:  # PandaScore data available
                analyzed_count += 1

                # Extract basic series data (Available on Free Tier)
                # CRITICAL: Match results by team_id, not array order!
                opponents = live_match.get("opponents", [])
                results = live_match.get("results", [])
                num_games = live_match.get("number_of_games", 3)

                # Get team IDs from opponents
                team1_id = opponents[0].get("opponent", {}).get("id") if len(opponents) > 0 else None
                team2_id = opponents[1].get("opponent", {}).get("id") if len(opponents) > 1 else None

                # Match results to correct teams by team_id
                ps_s1 = 0  # PandaScore team1 score (maps won)
                ps_s2 = 0  # PandaScore team2 score (maps won)
                for result in results:
                    team_id = result.get("team_id")
                    score = result.get("score", 0)
                    if team_id == team1_id:
                        ps_s1 = score
                    elif team_id == team2_id:
                        ps_s2 = score

                # CRITICAL FIX: If teams matched in reverse order, swap the scores!
                # PandaScore: Team A vs Team B (s1=2, s2=0 means A is winning)
                # Polymarket: Team B vs Team A (market.team1 = B, YES = B wins)
                # Without swap: GameState thinks B is winning 2-0 -> bets YES on B -> WRONG!
                # With swap: GameState correctly knows A is winning 2-0 -> bets NO -> CORRECT!
                if is_reversed:
                    s1, s2 = ps_s2, ps_s1  # Swap: Polymarket team1 gets PandaScore team2's score
                    print(f"      🔄 SCORE SWAP: Reversed order, swapping {ps_s1}-{ps_s2} -> {s1}-{s2}")
                else:
                    s1, s2 = ps_s1, ps_s2

                # Create basic state from summary data
                state = GameState(
                    game_type=live_match.get("game_type", "lol"),
                    match_id=str(live_match.get("id")),
                    team1=market.team1,
                    team2=market.team2,
                    series_score1=s1,
                    series_score2=s2,
                    number_of_games=num_games,
                    is_live=True
                )

                # Try to get detailed stats (might 403) - USE CACHE TO SAVE API CALLS!
                if state.match_id in match_state_cache:
                    detailed_state = match_state_cache[state.match_id]
                    print(f"      💾 Using cached match state for {state.match_id}")
                else:
                    detailed_state = self.data_aggregator.get_match_state(state.match_id, state.game_type)
                    if detailed_state:
                        self.increment_request_count()  # Count API call
                        match_state_cache[state.match_id] = detailed_state  # Cache it
                        print(f"      📡 Fetched match state for {state.match_id} ({state.game_type.upper()})")

                if detailed_state and detailed_state.game_time > 0:
                    # PATH A: Full Teemu Edge (Gold/Kills)
                    true_prob = self.model.calculate(detailed_state)
                    strategy_name = "TEEMU_HFT"
                else:
                    # PATH C: Series Fallback (Map Score)
                    true_prob = self.model.calculate_series_edge(state)
                    strategy_name = "SERIES_MOMENTUM"

                # SKIP BO1s: If calculate_series_edge returned None, skip this market
                if true_prob is None:
                    print(f"      ⏭️ SKIPPING BO1: No edge without in-game data")
                    continue

                # Check for edge
                edge = true_prob - yes_price
                if abs(edge) > (MIN_EDGE_PERCENT / 100):
                    side = "YES" if edge > 0 else "NO"
                    print(f"      🔥 {strategy_name} EDGE: {side} ({abs(edge)*100:.1f}%)")

                    # ACTIVATE BRAIN: Validate with news/rosters before trading
                    if self.validator:
                        target_price = yes_price if side == "YES" else no_price
                        should_trade, reason, confidence = self.validator.validate(
                            market.question, side, target_price, fast_mode=True)
                        if not should_trade:
                            print(f"      🧠 VALIDATOR BLOCKED: {reason}")
                            continue
                        else:
                            print(f"      🧠 VALIDATOR APPROVED: {confidence:.1f} confidence")

                    # LAYER C: CONFLICT AWARENESS - Prevent betting against yourself
                    # Never bet on multiple outcomes of the same match
                    match_conflict_key = f"{state.match_id}_active"
                    if match_conflict_key in self.positions:
                        existing_match_pos = self.positions[match_conflict_key]
                        print(f"      🎯 CONFLICT BLOCKED: Already have position on {existing_match_pos.get('outcome', 'unknown')} side of this match")
                        continue

                    # MATCH TRACKER: Prevent duplicate positions (wallet sync + same match)
                    # Check if we already have this specific token (from wallet sync)
                    target_token = market.yes_token if side == "YES" else market.no_token
                    if target_token in self.positions:
                        existing_pos = self.positions[target_token]
                        if existing_pos.get('synced', False):
                            print(f"      🎯 WALLET SYNC BLOCKED: Already own {existing_pos.get('size', 0):.2f} shares of {side} token")
                        else:
                            print(f"      🎯 MATCH TRACKER BLOCKED: Already have position on {side} for this match")
                        continue

                    # Also prevent same match + side combination
                    match_key = f"{state.match_id}_{side}"
                    if match_key in self.positions:
                        print(f"      🎯 MATCH TRACKER BLOCKED: Already have position on {side} for this match")
                        continue

                    if self.execute_trade(market, side, true_prob, yes_price if side=="YES" else no_price):
                        trades_made += 1
                        # Track match position to prevent same match + side duplicates
                        self.positions[match_key] = {
                            "market_id": market.market_id,
                            "side": side,
                            "entry_price": yes_price if side=="YES" else no_price,
                            "entry_time": datetime.datetime.now().isoformat(),
                            "strategy": strategy_name,
                            "synced": False
                        }
                    continue

            # === PATH B: MARKET-BASED TRADING (DISABLED - TOO RISKY WITHOUT DATA) ===
            # WARNING: Without Pandascore data, this is essentially gambling
            # The market-based heuristics are often wrong and lead to losses

            # Only log occasionally to avoid spam (every 10th market or if no live_matches)
            if not live_matches or (markets.index(market) % 10 == 0):
                if not live_matches:
                    print(f"   ⚠️ NO PANDASCORE DATA: Skipping '{question[:40]}...' - No live matches found")
                else:
                    # This is the key diagnostic: market exists but no match found
                    print(f"   ⚠️ NO MATCH: Skipping '{question[:40]}...' - Doesn't match any of {len(live_matches)} live matches")
                    if markets.index(market) == 0:  # Show sample on first market
                        sample_teams = []
                        for m in live_matches[:3]:
                            opps = m.get("opponents", [])
                            if len(opps) >= 2:
                                t1 = opps[0].get("opponent", {}).get("name", "?")
                                t2 = opps[1].get("opponent", {}).get("name", "?")
                                sample_teams.append(f"{t1} vs {t2}")
                        if sample_teams:
                            print(f"      📋 Sample live matches: {', '.join(sample_teams)}")
            
            # Log "WAIT" status to dashboard (Throttled to 1/min)
            if time.time() - self.last_activity_log > 60 and self.context:
                 self.context.log_llm_activity(LLMActivity(
                    agent="esports_trader",
                    action_type="SCAN",
                    market_question=question,
                    prompt_summary=f"Skipping {question[:30]}...",
                    reasoning="No live Pandascore data available for this match. Skipping to avoid gambling on random odds.",
                    conclusion="WAIT (No Data)",
                    confidence=0.0,
                    data_sources=["Polymarket"],
                    duration_ms=0
                 ))
                 self.last_activity_log = time.time()

            print(f"      Get Pandascore API key at pandascore.co to enable data-driven trading")
            print(f"      Market odds: Yes={yes_price:.3f}, No={no_price:.3f}")

            # DISABLED: Don't make trades without data advantage
            # The following code would gamble based on simplistic assumptions:
            
            # Still check for arbitrage (free money)
            spread_sum = yes_price + no_price
            if spread_sum < 0.985:  # True arbitrage opportunity
                print(f"\n   💰 ARBITRAGE DETECTED: {question[:40]}...")
                print(f"      Yes({yes_price:.3f}) + No({no_price:.3f}) = {spread_sum:.3f} (< 0.985)")
                target_side = "YES" if yes_price < no_price else "NO"
                print(f"      ⚡ Executing ARB on {target_side}")

                # ACTIVATE BRAIN: Even arbitrage needs validation
                if self.validator:
                    target_price = yes_price if target_side == "YES" else no_price
                    should_trade, reason, confidence = self.validator.validate(
                        market.question, target_side, target_price, fast_mode=True)
                    if not should_trade:
                        print(f"      🧠 ARBITRAGE BLOCKED: {reason}")
                        continue

                if self.execute_trade(market, target_side, 0.99, yes_price if target_side=="YES" else no_price):
                    trades_made += 1
                continue

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

        # Summary log
        print(f"\n   📊 Scan Summary:")
        print(f"      Markets scanned: {len(markets)}")
        print(f"      Live matches available: {len(live_matches)}")
        print(f"      Markets matched: {matched_count}")
        print(f"      Markets analyzed: {analyzed_count}")
        print(f"      Trades executed: {trades_made}")
        
        # Diagnostic messages
        if trades_made == 0 and len(live_matches) == 0:
            print(f"      ⚠️ No live matches found - check PandaScore API")
        elif trades_made == 0 and matched_count == 0:
            print(f"      ⚠️ No markets matched to live games - team name mismatch likely")
            print(f"      💡 Tip: Check match diagnostic logs above to see team name differences")
            if len(live_matches) > 0:
                print(f"      📋 Sample PS teams: {[m.get('opponents', [{}])[0].get('opponent', {}).get('name', '?') for m in live_matches[:3]]}")
        elif trades_made == 0 and analyzed_count > 0:
            print(f"      ⚠️ Markets analyzed but no edge > {MIN_EDGE_PERCENT}% found")
            print(f"      💡 Tip: Consider lowering MIN_EDGE_PERCENT to {MIN_EDGE_PERCENT_TEST}% for more trades")
        elif trades_made == 0 and matched_count > 0 and analyzed_count == 0:
            print(f"      ⚠️ Markets matched but not analyzed - check match state fetching")

        # Save state & Return
        self.save_state()
        return POLL_INTERVAL_LIVE if trades_made > 0 else POLL_INTERVAL_IDLE

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
