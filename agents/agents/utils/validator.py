import os
import requests
import json
import logging
import re
import time
import uuid
from datetime import datetime
from dotenv import load_dotenv
from typing import Tuple, List

logger = logging.getLogger("PyMLBot")

# Import context for LLM activity logging
try:
    from agents.utils.context import get_context, LLMActivity
    HAS_CONTEXT = True
except ImportError:
    HAS_CONTEXT = False


class SharedConfig:
    def __init__(self):
        load_dotenv()
        self.MIN_PROB = float(os.getenv("MIN_PROB", "0.90"))
        self.MAX_EXPOSURE = float(os.getenv("MAX_EXPOSURE", "0.25"))
        self.PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
        self.POLYGON_WALLET_PRIVATE_KEY = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
        
        if not self.PERPLEXITY_API_KEY:
            print("Warning: No PERPLEXITY_API_KEY found.")


class Validator:
    """
    Validates trading opportunities using Perplexity AI for research.
    
    The LLM is instructed to:
    1. Search for recent news and developments
    2. Analyze relevant statistics and polls
    3. Consider market sentiment and expert opinions
    4. Evaluate if there's an edge vs current market price
    """
    
    def __init__(self, config: SharedConfig, agent_name: str = "safe"):
        self.config = config
        self.agent_name = agent_name
        self.api_url = "https://api.perplexity.ai/chat/completions"
        self.context = get_context() if HAS_CONTEXT else None

    def validate(self, market_question: str, outcome: str, price: float, additional_context: str = "", 
                 min_confidence: float = 0.70, min_edge_pct: float = 0.05) -> Tuple[bool, str, float]:
        """
        Validates a trade opportunity using Perplexity.
        
        Args:
            market_question: The Polymarket question text
            outcome: YES or NO
            price: Current market price (0.0-1.0)
            additional_context: Extra info (e.g., "copy trading signal")
            min_confidence: Minimum LLM confidence required (0.0-1.0)
            min_edge_pct: Minimum edge required (e.g. 0.05 for 5%)
            
        Returns:
            (is_valid, reason, confidence_score)
        """
        if not self.config.PERPLEXITY_API_KEY:
            return True, "No Perplexity Key, skipping validation", 1.0

        implied_prob = price * 100
        
        system_prompt = """You are an elite superforecaster AI specialized in prediction markets.

Your task is to research and analyze betting opportunities on Polymarket.
You have access to real-time web search - USE IT to gather the latest information.

For each market, you must:
1. SEARCH for the most recent news articles (last 24-48 hours)
2. FIND relevant statistics, polls, or expert predictions
3. IDENTIFY any breaking developments that affect the outcome
4. COMPARE your estimated true probability vs the market price
5. DETERMINE if there's a profitable edge (true prob significantly > market price)

Be rigorous. Most opportunities are NOT good bets. Only recommend betting when:
- You have HIGH confidence based on concrete evidence
- The true probability is meaningfully higher than the market price
- Recent news/data strongly supports the outcome

IMPORTANT: If this is a sports/politics market, search for odds from professional bookmakers (Pinnacle, Betfair, PredictIt). 
If pro bookmakers have this at 70% and Polymarket is at 60%, there may be edge. Use bookmaker odds as your anchor."""

        user_prompt = f"""MARKET ANALYSIS REQUEST

Question: "{market_question}"
Outcome to evaluate: {outcome}
Current market price: ${price:.2f} (implied {implied_prob:.1f}% probability)

{f"Additional context: {additional_context}" if additional_context else ""}

RESEARCH INSTRUCTIONS:
1. Search for the latest news about this topic (last 48 hours)
2. Find any relevant polls, statistics, or expert opinions
3. Identify key factors that will determine the outcome
4. Estimate the TRUE probability based on your research
5. Calculate if there's a profitable edge vs the ${price:.2f} market price

OUTPUT FORMAT (JSON only):
{{
  "recent_news": "Brief summary of latest developments you found",
  "key_factors": "Main factors affecting the outcome",
  "estimated_true_prob": 0.XX,
  "edge_analysis": "Why the market may be mispriced (or not)",
  "confidence": 0.XX,
  "recommendation": "BET" or "PASS",
  "reason": "One sentence summary"
}}

CRITICAL RULES:
- Only recommend BET if confidence > {min_confidence:.2f} AND estimated_true_prob > {price + min_edge_pct:.2f}
- If news is unclear or mixed, recommend PASS
- If you can't find recent relevant news, recommend PASS
- Be conservative - capital preservation is priority"""

        headers = {
            "Authorization": f"Bearer {self.config.PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "sonar-pro",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 1000
        }
        
        start_time = time.time()
        
        try:
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Calculate tokens and cost
            usage = result.get("usage", {})
            tokens_used = usage.get("total_tokens", 0)
            # Perplexity sonar-pro: ~$5/1M tokens
            cost_usd = tokens_used * 0.000005
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Parse JSON from response
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                confidence = float(data.get("confidence", 0))
                rec = data.get("recommendation", "PASS")
                reason = data.get("reason", "")
                estimated_prob = float(data.get("estimated_true_prob", 0))
                news = data.get("recent_news", "")
                key_factors = data.get("key_factors", "")
                edge_analysis = data.get("edge_analysis", "")
                
                logger.info(f"LLM Research: {rec} | Conf: {confidence:.2f} | Est Prob: {estimated_prob:.2f}")
                logger.info(f"  News: {news[:100]}...")
                logger.info(f"  Reason: {reason}")
                
                # Log to context for UI
                if self.context and HAS_CONTEXT:
                    self.context.log_llm_activity(LLMActivity(
                        id=str(uuid.uuid4())[:8],
                        agent=self.agent_name,
                        timestamp=datetime.now().isoformat(),
                        action_type="validate",
                        market_question=market_question[:100],
                        prompt_summary=f"Evaluate {outcome} @ ${price:.2f} ({implied_prob:.0f}% implied)",
                        reasoning=f"News: {news[:150]}... | Factors: {key_factors[:100]}... | Edge: {edge_analysis[:100]}...",
                        conclusion=rec,
                        confidence=confidence,
                        data_sources=[s.strip() for s in news.split(",")[:3]] if news else ["No sources"],
                        duration_ms=duration_ms,
                        tokens_used=tokens_used,
                        cost_usd=cost_usd
                    ))
                
                # Validate the recommendation
                is_valid = (
                    rec == "BET" and 
                    confidence >= min_confidence and 
                    estimated_prob > (price + min_edge_pct)
                )
                
                return is_valid, reason, confidence
            else:
                logger.warning(f"Could not parse LLM response: {content[:200]}")
                if self.context and HAS_CONTEXT:
                    self.context.log_llm_activity(LLMActivity(
                        id=str(uuid.uuid4())[:8],
                        agent=self.agent_name,
                        timestamp=datetime.now().isoformat(),
                        action_type="validate",
                        market_question=market_question[:100],
                        prompt_summary=f"Evaluate {outcome} @ ${price:.2f}",
                        reasoning=f"Parse error: {content[:100]}...",
                        conclusion="ERROR",
                        confidence=0.0,
                        data_sources=[],
                        duration_ms=duration_ms,
                        tokens_used=tokens_used,
                        cost_usd=cost_usd
                    ))
                return False, "Parse Error", 0.0

        except requests.exceptions.Timeout:
            logger.error("Perplexity API timeout")
            if self.context and HAS_CONTEXT:
                self.context.log_llm_activity(LLMActivity(
                    id=str(uuid.uuid4())[:8],
                    agent=self.agent_name,
                    timestamp=datetime.now().isoformat(),
                    action_type="validate",
                    market_question=market_question[:100],
                    prompt_summary=f"Evaluate {outcome} @ ${price:.2f}",
                    reasoning="API request timed out after 30s",
                    conclusion="TIMEOUT",
                    confidence=0.0,
                    data_sources=[],
                    duration_ms=30000,
                    tokens_used=0,
                    cost_usd=0.0
                ))
            return False, "API Timeout", 0.0
        except Exception as e:
            logger.error(f"Validator Error: {e}")
            return False, str(e), 0.0

    def discover_top_traders(self, cache_file: str = "whale_addresses.json") -> list[dict]:
        """
        Use Perplexity to research top Polymarket traders + known address mappings.
        
        Strategy:
        1. LLM searches for trader names and any addresses mentioned in news
        2. Map known trader names to their addresses (from leaderboard profile URLs)
        3. Combine both sources
        
        Returns:
            List of {"address": "0x...", "name": "...", "reason": "..."}
        """
        # Known top trader name -> address mapping (from polymarket.com/leaderboard profile URLs)
        # Updated: These can be refreshed by visiting the leaderboard page
        KNOWN_TRADERS = {
            "kch123": "0x6a72f61820b26b1fe4d956e17b6dc2a1ea3033ee",
            "SeriouslySirius": "0x16b29c50f2439faf627209b2ac0c7bbddaa8a881",
            "DrPufferfish": "0xdb27bf2ac5d428a9c63dbc914611036855a6c56e",
            "SemyonMarmeladov": "0x37e4728b3c4607fb2b3b205386bb1d1fb1a8c991",
            "212121212121212121212": "0x1bc0d88ca86b9049cf05d642e634836d5ddf4429",
            "GamblingIsAllYouNeed": "0x507e52ef684ca2dd91f90a9d26d149dd3288beae",
            "swisstony": "0x204f72f35326db932158cba6adff0b9a1da95e14",
            "Ems123": "0xb889590a2fab0c810584a660518c4c020325a430",
            "gmanas": "0xe90bec87d9ef430f27f9dcfe72c34b76967d5da2",
            "RN1": "0x2005d16a84ceefa912d4e380cd32e7ff827875ea",
            "BlueHorseshoe86": "0x44de2a52d8d2d3ddcf39d58e315a10df53ba9c08",
        }
        
        # Check cache first (refresh every 24 hours)
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cache = json.load(f)
                if time.time() - cache.get("timestamp", 0) < 86400:  # 24 hours
                    logger.info(f"Using cached whale list ({len(cache.get('traders', []))} addresses)")
                    return cache.get("traders", [])
            except:
                pass
        
        traders = []
        
        # Step 1: Use LLM to find any new traders or addresses
        if self.config.PERPLEXITY_API_KEY:
            logger.info("Researching top Polymarket traders via LLM...")
            
            prompt = """Find the current TOP PERFORMING traders on Polymarket.

Search for:
1. The Polymarket leaderboard - who are the top 10-15 traders by profit?
2. Any Twitter/X discussions about Polymarket whales
3. News articles about successful Polymarket traders
4. Any wallet addresses (0x format) mentioned

Return JSON with trader names and any addresses you find:
{
  "traders": [
    {"name": "trader name", "address": "0x... or null", "pnl": "$X profit", "reason": "why notable"}
  ]
}"""

            headers = {
                "Authorization": f"Bearer {self.config.PERPLEXITY_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "sonar-pro",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 2000
            }
            
            start_time = time.time()
            try:
                response = requests.post(self.api_url, json=payload, headers=headers, timeout=60)
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                
                usage = result.get("usage", {})
                tokens_used = usage.get("total_tokens", 0)
                cost_usd = tokens_used * 0.000005
                duration_ms = int((time.time() - start_time) * 1000)
                
                json_match = re.search(r"\{.*\}", content, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                    llm_traders = data.get("traders", [])
                    
                    # Log LLM activity
                    if self.context and HAS_CONTEXT:
                        self.context.log_llm_activity(LLMActivity(
                            id=str(uuid.uuid4())[:8],
                            agent=self.agent_name,
                            timestamp=datetime.now().isoformat(),
                            action_type="discover",
                            market_question="Top Polymarket Traders Discovery",
                            prompt_summary="Search for top performing traders on leaderboard",
                            reasoning=f"Found {len(llm_traders)} traders from LLM search",
                            conclusion=f"FOUND_{len(llm_traders)}",
                            confidence=0.8 if llm_traders else 0.2,
                            data_sources=["Polymarket Leaderboard", "Twitter/X", "News"],
                            duration_ms=duration_ms,
                            tokens_used=tokens_used,
                            cost_usd=cost_usd
                        ))
                    
                    for t in llm_traders:
                        name = t.get("name", "")
                        addr = t.get("address")
                        reason = t.get("reason", t.get("pnl", "Top trader"))
                        
                        # If LLM found an address, use it
                        if addr and addr.startswith("0x") and len(addr) == 42:
                            traders.append({"name": name, "address": addr.lower(), "reason": reason})
                            logger.info(f"  LLM found: {name} -> {addr[:12]}...")
                        # Otherwise, try to map name to known address
                        elif name in KNOWN_TRADERS:
                            traders.append({
                                "name": name, 
                                "address": KNOWN_TRADERS[name], 
                                "reason": reason
                            })
                            logger.info(f"  Mapped: {name} -> {KNOWN_TRADERS[name][:12]}...")
                        # Check if name IS an address
                        elif name.startswith("0x") and len(name) == 42:
                            traders.append({"name": name, "address": name.lower(), "reason": reason})
                            logger.info(f"  Address-name: {name[:12]}...")
                            
            except Exception as e:
                logger.error(f"LLM trader discovery error: {e}")
        
        # Step 2: Add known traders not already found
        found_addrs = {t["address"].lower() for t in traders}
        for name, addr in KNOWN_TRADERS.items():
            if addr.lower() not in found_addrs:
                traders.append({"name": name, "address": addr, "reason": "Known top trader"})
        
        # Cache results
        cache_data = {"timestamp": time.time(), "traders": traders}
        try:
            with open(cache_file, "w") as f:
                json.dump(cache_data, f, indent=2)
        except:
            pass
        
        logger.info(f"Total traders discovered: {len(traders)}")
        return traders
