import os
import requests
import json
import logging
import datetime
from dotenv import load_dotenv
from typing import Dict, Tuple

logger = logging.getLogger("PyMLBot")

class SharedConfig:
    def __init__(self):
        load_dotenv()
        self.MIN_PROB = float(os.getenv("MIN_PROB", "0.90"))
        self.MAX_EXPOSURE = float(os.getenv("MAX_EXPOSURE", "0.25"))
        self.PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
        self.POLYGON_WALLET_PRIVATE_KEY = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
        
        if not self.PERPLEXITY_API_KEY:
             # logger might not be configured yet in some contexts, but okay for now
             print("Warning: No PERPLEXITY_API_KEY found.")

class Validator:
    def __init__(self, config: SharedConfig):
        self.config = config
        self.api_url = "https://api.perplexity.ai/chat/completions"

    def validate(self, market_question: str, outcome: str, price: float, additional_context: str = "") -> Tuple[bool, str, float]:
        """
        Validates a trade opportunity using Perplexity.
        Returns: (is_valid, reason, confidence_score)
        """
        if not self.config.PERPLEXITY_API_KEY:
            return True, "No Perplexity Key, skipping validation", 1.0

        prompt = f"""
        Analyze the Polymarket market: "{market_question}".
        Current price for outcome "{outcome}" is {price} (implied probability {price*100}%).
        
        {additional_context}
        
        Rules:
        - Analyze recent news, polls, and statistical data.
        - Determine if the true probability is significantly higher than {price} (for YES) or lower (for NO).
        - Output a JSON with keys: "confidence" (0.0 to 1.0), "recommendation" (BET or PASS), "reason".
        
        Only recommend BET if confidence > 0.92.
        """
        
        headers = {
            "Authorization": f"Bearer {self.config.PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "sonar-pro",
            "messages": [
                {"role": "system", "content": "You are a superforecaster AI."},
                {"role": "user", "content": prompt}
            ]
        }
        
        try:
            response = requests.post(self.api_url, json=payload, headers=headers)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            
            # Simple parsing
            import re
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                confidence = float(data.get("confidence", 0))
                rec = data.get("recommendation", "PASS")
                logger.info(f"LLM Analysis: {rec} (Conf: {confidence}) - {data.get('reason')}")
                return (rec == "BET" and confidence > 0.92), data.get("reason", ""), confidence
            else:
                logger.warning(f"Could not parse LLM response: {content}")
                return False, "Parse Error", 0.0

        except Exception as e:
            logger.error(f"Validator Error: {e}")
            return False, str(e), 0.0
