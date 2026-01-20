import os
import requests
import json
import logging
import re
import time
import uuid
from datetime import datetime
from dotenv import load_dotenv
from typing import Tuple, List, Dict
from openai import OpenAI  # Tier 3 Auditor

logger = logging.getLogger("PyMLBot")

# Import context for LLM activity logging
try:
    from agents.utils.context import get_context, LLMActivity
    HAS_CONTEXT = True
except ImportError:
    HAS_CONTEXT = False

# Import MistakeAnalyzer for historical lessons
try:
    from agents.utils.mistake_analyzer import MistakeAnalyzer
    HAS_ANALYZER = True
except ImportError:
    HAS_ANALYZER = False
    MistakeAnalyzer = None

class SharedConfig:
    def __init__(self):
        load_dotenv()
        self.MIN_PROB = float(os.getenv("MIN_PROB", "0.90"))
        self.MAX_EXPOSURE = float(os.getenv("MAX_EXPOSURE", "0.25"))
        self.PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # Tier 3 Key
        self.POLYGON_WALLET_PRIVATE_KEY = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
        
        if not self.PERPLEXITY_API_KEY:
            logger.warning("No PERPLEXITY_API_KEY found. Research phase will fail.")
        if not self.OPENAI_API_KEY:
            logger.warning("No OPENAI_API_KEY found. Final Logic Audit will be skipped.")

class Validator:
    """
    Three-Tier Validation System:
    Tier 1 & 2: Perplexity Sonar-Pro (Web Research & Data Gathering - Uses Credits)
    Tier 3: OpenAI GPT-4o mini (Logic Audit & Hallucination Check - Low Cost)
    """
    
    def __init__(self, config: SharedConfig, agent_name: str = "safe"):
        self.config = config
        self.agent_name = agent_name
        self.perplexity_url = "https://api.perplexity.ai/chat/completions"
        self.context = get_context() if HAS_CONTEXT else None
        
        # Initialize MistakeAnalyzer for historical lessons
        if HAS_ANALYZER:
            self.analyzer = MistakeAnalyzer(agent_name=agent_name)
        else:
            self.analyzer = None
        
        # Initialize OpenAI Client for Tier 3
        if self.config.OPENAI_API_KEY:
            self.openai_client = OpenAI(api_key=self.config.OPENAI_API_KEY)
        else:
            self.openai_client = None

    def validate(self, market_question: str, outcome: str, price: float, additional_context: str = "", 
                 fast_mode: bool = False, # NEW FLAG
                 min_confidence: float = 0.70, min_edge_pct: float = 0.05) -> Tuple[bool, str, float]:
        
        # --- FAST MODE BYPASS ---
        # If fast_mode is True (Live Sports/HFT), we skip the 30s LLM research entirely.
        if fast_mode:
            logger.info(f"⚡ FAST MODE: Bypassing LLM Audit for Live Market: {market_question[:30]}")
            return True, "Fast-tracked live trade (No LLM delay)", 1.0

        # --- PHASE 1: PERPLEXITY RESEARCH (Tier 1 & 2) ---
        # Purpose: Use your $4,000 credits for heavy web-searching and news gathering.
        research_result = self._research_phase(market_question, outcome, price, additional_context)
        
        if not research_result or research_result.get("recommendation") == "PASS":
            reason = research_result.get("reason", "Research phase did not find sufficient edge.") if research_result else "Research API Error"
            return False, reason, 0.0

        # --- PHASE 2: OPENAI LOGIC AUDIT (Tier 3) ---
        # Purpose: Use GPT-4o mini's reasoning to audit the Perplexity research for "hallucinated edge."
        # Cost: Minimal (~$0.15 / 1M tokens).
        if self.openai_client:
            return self._audit_phase(market_question, outcome, price, research_result, min_confidence, min_edge_pct)
        
        # Fallback if OpenAI isn't configured
        logger.warning("OpenAI Auditor not configured. Relying solely on Perplexity Research.")
        is_valid = research_result.get("recommendation") == "BET"
        return is_valid, research_result.get("reason", ""), research_result.get("confidence", 0.0)

    def _research_phase(self, question: str, outcome: str, price: float, context: str) -> Dict:
        """Deep research using Perplexity credits."""
        prompt = f"""Search for the latest news (last 48h) and data for: "{question}"
        Evaluate the {outcome} outcome currently priced at ${price:.2f}.
        Identify breaking news, polls, or expert analysis.
        
        Context/Instructions: {context}
        
        RESPOND ONLY IN JSON:
        {{
          "news_summary": "Latest verified info",
          "key_factors": "Pro/Con factors",
          "estimated_true_prob": 0.XX,
          "recommendation": "BET" or "PASS",
          "reason": "One sentence summary",
          "confidence": 0.XX
        }}"""

        headers = {"Authorization": f"Bearer {self.config.PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "sonar-pro",
            "messages": [{"role": "system", "content": "You are a professional market researcher."}, {"role": "user", "content": prompt}],
            "temperature": 0.1
        }

        try:
            response = requests.post(self.perplexity_url, json=payload, headers=headers, timeout=45)
            content = response.json()["choices"][0]["message"]["content"]
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            return json.loads(json_match.group(0)) if json_match else None
        except Exception as e:
            logger.error(f"Perplexity Research Phase Error: {e}")
            return None

    def _audit_phase(self, question: str, outcome: str, price: float, research: Dict, min_conf: float, min_edge: float) -> Tuple[bool, str, float]:
        """Final Logic Check using GPT-4o mini with historical lessons."""
        
        # Fetch relevant lessons from past mistakes
        lessons_context = ""
        if self.analyzer:
            try:
                lessons = self.analyzer.get_relevant_lessons(question, limit=3)
                if lessons:
                    lessons_context = self.analyzer.format_lessons_for_prompt(lessons)
                    logger.info(f"📚 Injecting {len(lessons)} historical lessons into audit")
            except Exception as e:
                logger.debug(f"Could not fetch lessons: {e}")
        
        audit_prompt = f"""
        AUDIT REQUEST: A research bot recommends a BET on this market.
        Market: "{question}"
        Target Outcome: {outcome} @ ${price:.2f}
        
        RESEARCHER'S FINDINGS:
        - News: {research['news_summary']}
        - Estimated Prob: {research['estimated_true_prob']}
        - Reason: {research['reason']}
        
        {lessons_context}
        
        CRITICAL TASK:
        Find any logical flaws or 'traps' in the researcher's thinking. 
        Does the news actually support this outcome? Is the researcher being over-optimistic?
        If there are historical lessons above, ensure you don't repeat those same mistakes.
        
        RESPOND ONLY IN JSON:
        {{
          "audit_confidence": 0.XX,
          "is_logic_sound": true/false,
          "revised_prob": 0.XX,
          "critique": "One sentence critique",
          "final_recommendation": "BET" or "PASS"
        }}"""

        try:
            start_time = time.time()
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": "You are a skeptical risk manager."}, {"role": "user", "content": audit_prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )
            
            audit = json.loads(response.choices[0].message.content)
            
            # Final Decision Logic
            is_valid = (
                audit["is_logic_sound"] and 
                audit["final_recommendation"] == "BET" and
                audit["revised_prob"] > (price + min_edge) and
                audit["audit_confidence"] >= min_conf
            )
            
            # Log to Activity Feed
            if self.context:
                self.context.log_llm_activity(LLMActivity(
                    id=str(uuid.uuid4())[:8],
                    agent=self.agent_name,
                    timestamp=datetime.now().isoformat(),
                    action_type="logic_audit",
                    market_question=question[:50],
                    prompt_summary=f"Audit {outcome} @ {price}",
                    reasoning=audit["critique"],
                    conclusion="BET" if is_valid else "PASS",
                    confidence=audit["audit_confidence"],
                    data_sources=["Perplexity News", "OpenAI Logic Audit"],
                    duration_ms=int((time.time() - start_time) * 1000)
                ))

            return is_valid, audit["critique"], audit["audit_confidence"]

        except Exception as e:
            logger.error(f"OpenAI Audit Phase Error: {e}")
            return False, "Audit failed during processing", 0.0

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
}
"""

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
                # Use self.perplexity_url initialized in __init__
                response = requests.post(self.perplexity_url, json=payload, headers=headers, timeout=60)
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
