import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("HedgeFundAnalyst")

class HedgeFundAnalyst:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.enabled = True # Can be toggled via config later
        self.agent_name = "hedge_fund_analyst"
        
        # Initialize OpenAI client if key exists
        self.client = None
        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                logger.warning("OpenAI library not found. LLM features disabled.")
        
        # Initialize MistakeAnalyzer for learning from past trades
        self.mistake_analyzer = None
        try:
            from agents.utils.mistake_analyzer import MistakeAnalyzer
            self.mistake_analyzer = MistakeAnalyzer(agent_name=self.agent_name)
        except ImportError:
            logger.warning("MistakeAnalyzer not available. Trade learning disabled.")
                
    def analyze_trade_opportunity(self, context: dict, proposed_trade: dict) -> dict:
        """
        Analyzes a trade using LLM reasoning (GPT-4o-mini) with local fallback.
        Incorporates lessons from past trades and social signals.
        """
        # 0. Pre-check: Social signals (whale positions, comment sentiment)
        social_check = self._check_social_signals(proposed_trade, context)
        if social_check and social_check.get("decision") == "REJECTED":
            logger.info(f"Trade rejected by social signals: {social_check.get('reasoning')}")
            return social_check

        # 1. Get relevant lessons from past mistakes
        lessons_text = ""
        if self.mistake_analyzer:
            try:
                lessons = self.mistake_analyzer.get_relevant_lessons(
                    proposed_trade.get("market_question", ""),
                    limit=3
                )
                lessons_text = self.mistake_analyzer.format_lessons_for_prompt(lessons)
            except Exception as e:
                logger.warning(f"Could not fetch lessons: {e}")

        # 2. Try LLM Analysis if available
        if self.client and self.enabled:
            try:
                result = self._call_llm(context, proposed_trade, lessons_text)
                if result:
                    return result
            except Exception as e:
                logger.error(f"LLM Analysis failed: {e}. Falling back to Logic Gates.")

        # 3. Fallback: Logic Gates (Original Implementation)
        return self._fallback_logic(context, proposed_trade)

    def _check_social_signals(self, proposed_trade: dict, context: dict) -> Optional[Dict[str, Any]]:
        """
        Check social signals including whale positions and comment sentiment.
        Returns REJECTED decision if signals are unfavorable.
        """
        try:
            # Get whale positions from context if available
            whale_positions = context.get('whale_positions', {})
            comment_sentiment = context.get('comment_sentiment', {})
            
            decision = "APPROVED"
            reasons = []
            
            # Check whale positions
            if whale_positions:
                whale_side = whale_positions.get('dominant_side')
                if whale_side and whale_side != proposed_trade.get('side'):
                    reasons.append(f"Whales are on {whale_side} side, conflicting with our {proposed_trade.get('side')} position")
                    # Soft rejection - just note it, don't hard reject
                    logger.warning(f"Whale position conflict: whales favor {whale_side}")
            
            # Check comment sentiment
            if comment_sentiment:
                sentiment_score = comment_sentiment.get('sentiment_score', 0)
                if sentiment_score < -0.6:  # Strongly negative
                    return {
                        "decision": "REJECTED",
                        "risk_adjustment_factor": 0.0,
                        "confidence": 0.85,
                        "reasoning": f"Strongly negative comment sentiment ({sentiment_score:.2f}) - market sentiment against trade"
                    }
                elif sentiment_score < -0.3:  # Moderately negative
                    reasons.append("Moderately negative comment sentiment")
            
            if decision == "APPROVED" and reasons:
                # Not a rejection, but note concerns
                return None
            
            return None
            
        except Exception as e:
            logger.error(f"Social signal check failed: {e}")
            return None

    def _call_llm(self, context: dict, proposed_trade: dict, lessons_text: str = "") -> Dict[str, Any]:
        """Call OpenAI to analyze the trade with lessons from past mistakes."""
        
        system_prompt = """You are the Senior Risk Manager for a quantitative hedge fund. 
Your job is to REJECT or MODIFY trades based on market conditions, portfolio status, and risk parameters.
You are conservative, cynical, and data-driven. You DO NOT trust 'vibes'.
You must output JSON only."""

        user_prompt = f"""
{lessons_text}

ANALYZE THIS TRADE PROPOSAL:
Ticker: {proposed_trade.get('ticker')}
Side: {proposed_trade.get('side')}
Odds: {proposed_trade.get('odds')}
Calculated Edge: {proposed_trade.get('edge', 'N/A')}

CURRENT CONTEXT:
1. Wallet: {json.dumps(context.get('wallet', {}))}
2. Performance Streak: {context.get('performance', {}).get('current_mood')} (Win Rate: {context.get('performance', {}).get('win_rate')})
3. Market Depth: {json.dumps(context.get('market_depth', {}))}
4. Global Sentiment: {json.dumps(context.get('sentiment', {}))}

INSTRUCTIONS:
- If we are in a COLD_STREAK, be extremely strict. Reduce size or REJECT.
- If Spread > 5%, REJECT (Liquidity Risk).
- If Sentiment is VOLATILE, reduce size.
- If Edge is minimal (<2%), REJECT.

OUTPUT FORMAT (JSON ONLY):
{{
    "decision": "APPROVED" | "REJECTED" | "REDUCE_SIZE",
    "risk_adjustment_factor": float (0.0 to 1.5, where 1.0 is standard size),
    "confidence": float (0.0 to 1.0),
    "reasoning": "Short, punchy explanation."
}}
"""
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        content = response.choices[0].message.content
        return json.loads(content)

    def _fallback_logic(self, context: dict, proposed_trade: dict) -> dict:
        """Standard hardcoded logic gates (Fast & Free)."""
        decision = "APPROVED"
        factor = 1.0
        reasoning = []
        
        # 1. MOOD CHECK (Internal)
        mood = context.get('performance', {}).get('current_mood', 'NEUTRAL')
        if "COLD_STREAK" in mood:
            decision = "REDUCE_SIZE"
            factor = 0.5
            reasoning.append("Cold streak detected; halving size.")
        elif "HOT_STREAK" in mood:
            factor = 1.2 # Let winners ride a bit
            reasoning.append("Hot streak; +20% size.")
            
        # 2. LIQUIDITY CHECK (External)
        depth = context.get('market_depth', {})
        spread = depth.get('spread', 0)
        
        if spread > 0.05: # >5% spread is risky
            decision = "REJECTED" if decision != "REJECTED" else decision
            factor = 0.0
            reasoning.append(f"Spread too wide ({spread*100:.1f}%)")
        
        # 3. SENTIMENT CHECK (Global)
        if context.get('sentiment', {}).get('global_trend') == "VOLATILE":
            factor *= 0.8
            reasoning.append("Global volatility penalty.")

        final_reason = "; ".join(reasoning) if reasoning else "Standard trade conditions met (Fallback Logic)."

        return {
            "decision": decision,
            "confidence": 0.88,
            "risk_adjustment_factor": min(factor, 1.5), # Cap at 1.5x
            "reasoning": final_reason
        }
