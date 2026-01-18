#!/usr/bin/env python3
"""
Esports Live Match Monitor
Monitors PandaScore and Riot APIs for live esports matches and alerts when trading opportunities are available.

This runs as a separate process group on Fly.io and sends notifications to the dashboard.
"""

import os
import sys
import time
import requests
import threading
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.utils.supabase_client import get_supabase_state

class EsportsMonitor:
    """Monitors live esports matches and sends notifications."""

    def __init__(self):
        self.pandascore_key = os.getenv("PANDASCORE_API_KEY")
        self.supabase = get_supabase_state()
        self.last_notification_time = 0
        self.notification_cooldown = 300  # 5 minutes between notifications
        self.live_matches_cache = {}
        self.cache_expiry = 60  # Cache for 60 seconds

        # Import RiotEsportsAPI if available
        try:
            from agents.application.esports_trader import RiotEsportsAPI
            self.riot_api = RiotEsportsAPI()
        except ImportError:
            self.riot_api = None

        print("🎮 Esports Monitor initialized")
        print(f"   PandaScore API: {'✅' if self.pandascore_key else '❌'}")
        print(f"   Riot eSports API: {'✅' if self.riot_api else '❌'}")
        print(f"   Supabase: {'✅' if self.supabase else '❌'}")

    def get_all_live_matches(self) -> Dict[str, List[Dict]]:
        """Get live matches from all sources."""
        now = time.time()
        if now - self.live_matches_cache.get('last_check', 0) < self.cache_expiry:
            return self.live_matches_cache.get('matches', {})

        matches = {
            'pandascore': [],
            'riot': []
        }

        # Check PandaScore
        if self.pandascore_key:
            try:
                # Check all game types
                game_types = ['lol', 'cs2', 'valorant', 'dota2', 'r6siege', 'cod', 'rl']

                for game_type in game_types:
                    try:
                        url = f"https://api.pandascore.co/{game_type}/matches/running"
                        headers = {"Authorization": f"Bearer {self.pandascore_key}"}
                        resp = requests.get(url, headers=headers, timeout=10)

                        if resp.status_code == 200:
                            game_matches = resp.json()
                            if game_matches:
                                matches['pandascore'].extend([
                                    {**match, 'game_type': game_type}
                                    for match in game_matches
                                ])
                        elif resp.status_code == 403:
                            print(f"⚠️ PandaScore {game_type} access denied (403)")
                        elif resp.status_code == 429:
                            print(f"⚠️ PandaScore {game_type} rate limited (429)")
                    except Exception as e:
                        print(f"🔍 PandaScore {game_type} error: {e}")

            except Exception as e:
                print(f"🔍 PandaScore error: {e}")

        # Check Riot eSports API
        if self.riot_api:
            try:
                riot_events = self.riot_api.get_live_events()
                if riot_events:
                    matches['riot'] = riot_events
            except Exception as e:
                print(f"🎮 Riot API error: {e}")

        # Cache results
        self.live_matches_cache = {
            'last_check': now,
            'matches': matches
        }

        return matches

    def log_to_llm_terminal(self, action_type: str, market_question: str,
                          prompt_summary: str, reasoning: str, conclusion: str,
                          confidence: float = 0.0, data_sources: List[str] = None):
        """Log monitoring activity to LLM terminal."""
        if not self.supabase:
            return

        try:
            import uuid
            activity_data = {
                'id': str(uuid.uuid4())[:8],
                'agent': 'esports_monitor',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'action_type': action_type,
                'market_question': market_question,
                'prompt_summary': prompt_summary,
                'reasoning': reasoning,
                'conclusion': conclusion,
                'confidence': confidence,
                'data_sources': data_sources or ['PandaScore', 'Riot eSports'],
                'duration_ms': 0,
                'tokens_used': 0,
                'cost_usd': 0.0
            }

            # Log to Supabase
            self.supabase.table('llm_activity').insert(activity_data).execute()

            # Print to stdout for Fly.io logs
            print(f"📝 {action_type}: {market_question} → {conclusion}")

        except Exception as e:
            print(f"🔍 LLM log error: {e}")

    def send_notification(self, message: str, matches: Dict[str, List[Dict]]):
        """Send notification about live matches detected."""
        current_time = time.time()
        if current_time - self.last_notification_time < self.notification_cooldown:
            return  # Too soon for another notification

        try:
            # Count total matches
            total_matches = len(matches.get('pandascore', [])) + len(matches.get('riot', []))

            if total_matches == 0:
                return

            # Create detailed match summary
            match_details = []
            for source, match_list in matches.items():
                for match in match_list[:5]:  # Show first 5 matches
                    if source == 'pandascore':
                        opponents = match.get('opponents', [])
                        if len(opponents) >= 2:
                            team1 = opponents[0].get('opponent', {}).get('name', 'Unknown')
                            team2 = opponents[1].get('opponent', {}).get('name', 'Unknown')
                            game = match.get('game_type', 'unknown')
                            match_details.append(f"{team1} vs {team2} ({game.upper()})")
                    elif source == 'riot':
                        teams = match.get('match', {}).get('teams', [])
                        if len(teams) >= 2:
                            team1 = teams[0].get('name', 'Unknown')
                            team2 = teams[1].get('name', 'Unknown')
                            match_details.append(f"{team1} vs {team2} (LoL)")

            match_summary = "\n".join(f"• {detail}" for detail in match_details[:10])

            # Log to LLM terminal
            self.log_to_llm_terminal(
                action_type="NOTIFICATION",
                market_question=f"{total_matches} Live Esports Matches Detected",
                prompt_summary=f"Monitoring detected {total_matches} active matches",
                reasoning=f"Found {len(matches.get('pandascore', []))} via PandaScore, {len(matches.get('riot', []))} via Riot API. Trading opportunities available!",
                conclusion="LIVE MATCHES FOUND",
                confidence=1.0,
                data_sources=["PandaScore", "Riot eSports"]
            )

            # Print notification to logs (will appear in dashboard)
            print(f"🔔 LIVE ESPORTS ALERT: {total_matches} matches found!")
            print(f"📊 Match Details:\n{match_summary}")

            self.last_notification_time = current_time

        except Exception as e:
            print(f"🔍 Notification error: {e}")

    def monitor_loop(self):
        """Main monitoring loop."""
        print("🎮 Starting esports monitoring loop...")
        print("   Checking for live matches every 60 seconds")
        print("   Will notify when matches are detected")

        while True:
            try:
                # Get live matches
                matches = self.get_all_live_matches()

                total_matches = len(matches.get('pandascore', [])) + len(matches.get('riot', []))

                if total_matches > 0:
                    print(f"🎯 FOUND {total_matches} LIVE MATCHES!")
                    self.send_notification("Live matches detected", matches)
                else:
                    print(f"🔍 No live matches at {datetime.now().strftime('%H:%M:%S UTC')}")

                # Log periodic status
                self.log_to_llm_terminal(
                    action_type="MONITOR",
                    market_question="Esports Match Monitoring",
                    prompt_summary="Checking for live esports matches",
                    reasoning=f"Scanned APIs for live matches. Found {total_matches} active games.",
                    conclusion="SCAN_COMPLETE",
                    confidence=total_matches > 0,
                    data_sources=["PandaScore", "Riot eSports"]
                )

            except Exception as e:
                print(f"🔍 Monitor error: {e}")
                import traceback
                traceback.print_exc()

            # Wait before next check
            time.sleep(60)

def main():
    """Main entry point."""
    monitor = EsportsMonitor()
    monitor.monitor_loop()

if __name__ == "__main__":
    main()