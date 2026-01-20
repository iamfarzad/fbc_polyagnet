import os
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger("UniversalAnalyst")


class UniversalAnalyst:
    """
    Unified LLM interface for all agents to request AI-driven analysis.
    Supports: Scalper sentiment, Whale psychology, Esports match, and NEW alpha research.
    """
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.perplexity_key = os.getenv("PERPLEXITY_API_KEY")

    def ask_strategy(self, context_type: str, data: Any) -> Dict[str, Any]:
        """
        Generic entry point for agents to get AI advice.
        context_type: 'scalper_sentiment', 'whale_psychology', 'esports_match'
        """
        if not self.api_key:
            return {"decision": "NEUTRAL", "confidence": 0.0, "reason": "No API Key"}

        try:
            prompt = ""
            if context_type == "scalper_sentiment":
                prompt = f"Analyze these recent trades for scalping direction: {data}. Return LONG/SHORT/WAIT."
            
            elif context_type == "whale_psychology":
                prompt = f"Whale trade history: {data}. Are they informed or tilting? Return COPY/IGNORE."
            
            elif context_type == "esports_match":
                prompt = f"LoL Match Stats: {data}. predict win probability."
            
            # MOCK RESPONSE (Replace with actual OpenAI call when ready)
            return {
                "decision": "APPROVED", 
                "confidence": 0.85, 
                "reason": "Simulated LLM Approval (Mock)"
            }
            
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return {"decision": "ERROR", "confidence": 0.0, "reason": str(e)}

    # =========================================================================
    # NEW ALPHA RESEARCH METHODS (from Newagentinstruction.md)
    # =========================================================================

    def _call_perplexity(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        """Helper to call Perplexity API for research."""
        if not self.perplexity_key:
            return None
        
        try:
            headers = {
                "Authorization": f"Bearer {self.perplexity_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "sonar",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens
            }
            resp = requests.post(
                "https://api.perplexity.ai/chat/completions",
                json=payload,
                headers=headers,
                timeout=30
            )
            result = resp.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Perplexity API error: {e}")
            return None

    def analyze_sentiment_velocity(self, token: str) -> Dict[str, Any]:
        """
        Analyze social velocity divergence from price.
        Returns: accumulation_phase, euphoria_phase, or neutral
        """
        prompt = f"""Run a deep-dive on {token} social velocity.

• Compare mention frequency vs. the 30-day baseline.
• Is the narrative shift led by 'Alpha' accounts or low-quality bot farms?
• Extract the top 3 recurring arguments from the skeptics.
• Verdict: Are we in the 'Quiet Accumulation' or 'Mass Retail Euphoria' phase?

Return a JSON with: phase, confidence (0-1), top_concerns (list), recommendation (BUY/WAIT/EXIT)."""

        result = self._call_perplexity(prompt)
        
        if not result:
            return {
                "phase": "unknown",
                "confidence": 0.0,
                "recommendation": "WAIT",
                "reason": "Research API unavailable"
            }
        
        # Parse response (simplified - in production, use structured output)
        try:
            # Try to extract JSON from response
            if "{" in result:
                json_str = result[result.index("{"):result.rindex("}")+1]
                return json.loads(json_str)
        except:
            pass
        
        return {
            "phase": "analyzed",
            "confidence": 0.7,
            "recommendation": "WAIT",
            "analysis": result[:500]
        }

    def scan_sector_narratives(self, sectors: list) -> Dict[str, Any]:
        """
        Front-run narrative rotations by scanning emerging sectors.
        Returns: top projects, liquidity environment, 30-day playbook
        """
        sectors_str = ", ".join(sectors) if sectors else "AI, DePIN, RWA, BTCFi"
        
        prompt = f"""Scan X for 'narrative seeds' in the [{sectors_str}] space.

• Which sub-sectors are gaining mentions among top-tier crypto researchers?
• Identify 3 projects with <$10M MC that are being consistently mentioned in 'thread alpha.'
• How does the current liquidity environment (M2 supply) favor this specific narrative?
• Give me a 30-day front-run playbook.

Return JSON with: emerging_sectors, alpha_projects (list), liquidity_outlook, playbook."""

        result = self._call_perplexity(prompt, max_tokens=700)
        
        if not result:
            return {
                "emerging_sectors": [],
                "alpha_projects": [],
                "playbook": "Research unavailable"
            }
        
        try:
            if "{" in result:
                json_str = result[result.index("{"):result.rindex("}")+1]
                return json.loads(json_str)
        except:
            pass
        
        return {
            "emerging_sectors": sectors,
            "analysis": result[:600],
            "playbook": "See analysis"
        }

    def build_exit_strategy(self, token: str, entry_price: float, current_price: float) -> Dict[str, Any]:
        """
        Design cold-blooded exit plan based on social mania triggers.
        Returns: take_profit_levels, invalidation_point, dca_schedule
        """
        gain_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        
        prompt = f"""Design a cold-blooded exit plan for {token}.
Entry: ${entry_price:.4f}, Current: ${current_price:.4f}, Gain: {gain_pct:.1f}%

• Define 4 take-profit levels based on 'Social Mania' triggers (e.g., when influencer starts posting).
• What is the 'Invalidation Point' where the narrative is officially dead?
• Build a DCA-out schedule that maximizes profit while leaving a 'moonbag' for extreme upside.

Return JSON: take_profit_levels (list with price and trigger), invalidation_price, moonbag_percent, dca_schedule."""

        result = self._call_perplexity(prompt, max_tokens=600)
        
        if not result:
            # Return sensible defaults
            return {
                "take_profit_levels": [
                    {"level": 1, "price": current_price * 1.25, "sell_pct": 25, "trigger": "25% gain"},
                    {"level": 2, "price": current_price * 1.50, "sell_pct": 25, "trigger": "50% gain"},
                    {"level": 3, "price": current_price * 2.00, "sell_pct": 30, "trigger": "2x"},
                ],
                "invalidation_price": entry_price * 0.85,
                "moonbag_percent": 20,
                "strategy": "Default tiered exit"
            }
        
        try:
            if "{" in result:
                json_str = result[result.index("{"):result.rindex("}")+1]
                return json.loads(json_str)
        except:
            pass
        
        return {
            "analysis": result[:500],
            "moonbag_percent": 20,
            "strategy": "See analysis"
        }

    def deception_audit(self, project: str) -> Dict[str, Any]:
        """
        Execute anti-rug deception audit.
        Returns: team_verified, lp_secure, social_authentic, rug_risk_score
        """
        prompt = f"""Execute a 'Deception Audit' on {project}.

• Team: Are the founders' histories verifiable or do they appear 'AI-generated'?
• Liquidity: Is the LP truly locked, or is there a back-door function in the contract?
• Social Signal: Are the followers 'hollow' (high count, zero engagement)?
• Comparison: How does this project's launch pattern compare to documented rugs from 2024-2025?

Return JSON: team_verified (bool), lp_status, social_authentic (bool), rug_risk_score (1-10), red_flags (list)."""

        result = self._call_perplexity(prompt, max_tokens=600)
        
        if not result:
            return {
                "team_verified": False,
                "lp_status": "unknown",
                "social_authentic": False,
                "rug_risk_score": 5,
                "red_flags": ["Unable to verify - proceed with caution"]
            }
        
        try:
            if "{" in result:
                json_str = result[result.index("{"):result.rindex("}")+1]
                return json.loads(json_str)
        except:
            pass
        
        return {
            "analysis": result[:500],
            "rug_risk_score": 5,
            "recommendation": "DYOR"
        }
