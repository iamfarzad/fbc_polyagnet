import os
import json
import random
import logging

logger = logging.getLogger("LLMAnalyst")

class LLMAnalyst:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        
    def analyze_match(self, match_data: dict) -> dict:
        """
        Sends match stats to an LLM to get a 'Vibes' based win probability.
        match_data should contain teams, scores, gold diff, etc.
        """
        team_1 = "Team 1"
        team_2 = "Team 2"
        
        # Safely extract names
        try:
             opponents = match_data.get('opponents', [])
             if len(opponents) >= 2:
                 team_1 = opponents[0].get('opponent', {}).get('name', 'Team 1')
                 team_2 = opponents[1].get('opponent', {}).get('name', 'Team 2')
        except: pass

        # --- MOCK MODE (To save tokens) ---
        # Returns a slightly random probability to simulate AI "thinking"
        # We assume the user wants to enable real calls later via Config flag.
        
        mock_prob = 0.5 + (random.uniform(-0.1, 0.1)) 
        
        # Create a "smart" sounding reason
        reasons = [
            "Team A has better scaling composition.",
            "Gold lead is significant but early game is over.",
            "Map control favors the underdog currently.",
            "Key player shutdown on Team B.",
            "Objective bounty favors Team A."
        ]
        
        return {
            "win_probability": round(mock_prob, 2),
            "reasoning": f"Simulated Analysis: {random.choice(reasons)}"
        }

        # --- REAL IMPL (Commented out) ---
        """
        if not self.api_key: return mock_response
        
         prompt = f'''
        You are an expert League of Legends Analyst.
        Match: {team_1} vs {team_2}.
        Data: {json.dumps(match_data)}
        Predict win probability for {team_1}. JSON only: {{win_probability: float, reasoning: str}}
        '''
        # call openai...
        """
