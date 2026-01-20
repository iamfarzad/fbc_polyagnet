import os
import json
import logging
from typing import Optional

logger = logging.getLogger("LLMAnalyst")

class LLMAnalyst:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Default to cost-effective model
        
    def analyze_match(self, match_data: dict) -> dict:
        """
        Sends match stats to OpenAI LLM to get a data-driven win probability.
        match_data should contain teams, scores, gold diff, player stats, etc.
        
        Returns:
            dict: {win_probability: float, reasoning: str}
        """
        team_1 = "Team 1"
        team_2 = "Team 2"
        
        # Safely extract team names
        try:
            opponents = match_data.get('opponents', [])
            if len(opponents) >= 2:
                team_1 = opponents[0].get('opponent', {}).get('name', 'Team 1')
                team_2 = opponents[1].get('opponent', {}).get('name', 'Team 2')
        except Exception as e:
            logger.warning(f"Failed to extract team names: {e}")
        
        # Check if OpenAI API key is available
        if not self.api_key:
            logger.error("OPENAI_API_KEY not set. Cannot perform real analysis.")
            return {
                "win_probability": 0.5,
                "reasoning": "Error: OPENAI_API_KEY not configured. Please set environment variable.",
                "error": "missing_api_key"
            }
        
        # Construct the prompt
        prompt = f'''You are an expert esports analyst specializing in {match_data.get('videogame', {}).get('name', 'League of Legends')}.

Match: {team_1} vs {team_2}

Match Data:
{json.dumps(match_data, indent=2, default=str)}

Task: Predict the win probability for {team_1} based on the provided data. Consider:
- Current game state (score, gold, objectives)
- Team compositions and scaling potential
- Individual player performance (KDA, gold, damage)
- Momentum and objective control
- Historical factors if available

Provide your analysis in JSON format:
{{
  "win_probability": <float between 0.0 and 1.0>,
  "reasoning": "<detailed explanation of your analysis>"
}}

Return ONLY the JSON, no additional text.'''
        
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=self.api_key)
            
            logger.info(f"Calling OpenAI API for match analysis: {team_1} vs {team_2}")
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert esports analyst. Provide only valid JSON responses with win_probability (float) and reasoning (string)."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent analysis
                max_tokens=500,
                response_format={"type": "json_object"}  # Enforce JSON response
            )
            
            # Parse response
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Validate and sanitize result
            win_prob = float(result.get("win_probability", 0.5))
            win_prob = max(0.0, min(1.0, win_prob))  # Clamp to [0, 1]
            
            reasoning = result.get("reasoning", "No reasoning provided")
            
            logger.info(f"LLM Analysis: {team_1} win probability = {win_prob:.2f}")
            
            return {
                "win_probability": round(win_prob, 2),
                "reasoning": reasoning,
                "model": self.model,
                "tokens_used": response.usage.total_tokens
            }
            
        except ImportError:
            logger.error("OpenAI package not installed. Run: pip install openai")
            return {
                "win_probability": 0.5,
                "reasoning": "Error: OpenAI package not installed. Run 'pip install openai'",
                "error": "missing_package"
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response as JSON: {e}")
            return {
                "win_probability": 0.5,
                "reasoning": "Error: Could not parse LLM response",
                "error": "json_parse_error"
            }
            
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return {
                "win_probability": 0.5,
                "reasoning": f"Error: {str(e)}",
                "error": "api_error"
            }
