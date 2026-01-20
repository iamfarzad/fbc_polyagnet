import os
import json
import logging

logger = logging.getLogger("HedgeFundAnalyst")

class HedgeFundAnalyst:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")

    def analyze_trade_opportunity(self, context: dict, proposed_trade: dict) -> dict:
        """
        context: The dictionary from SmartContext
        proposed_trade: {'ticker': 'Trump', 'side': 'YES', 'odds': 0.60}
        
        Returns:
            {
                "decision": "APPROVED" | "REJECTED" | "REDUCE_SIZE",
                "confidence": 0.0 to 1.0,
                "risk_adjustment_factor": 0.1 to 1.0,
                "reasoning": str
            }
        """
        
        # In a real scenario, we'd feed this prompt to GPT-4.
        # For now, we Implement the "Logic Gates" locally to be fast and free.
        
        decision = "APPROVED"
        factor = 1.0
        reasoning = []
        
        # 1. MOOD CHECK (Internal)
        mood = context['performance']['current_mood']
        if "COLD_STREAK" in mood:
            decision = "REDUCE_SIZE"
            factor = 0.5
            reasoning.append("Cold streak detected; halving size.")
        elif "HOT_STREAK" in mood:
            factor = 1.2 # Let winners ride a bit
            reasoning.append("Hot streak; +20% size.")
            
        # 2. LIQUIDITY CHECK (External)
        liquidity = context['market_depth']['liquidity_pressure']
        spread = context['market_depth'].get('spread', 0)
        
        if spread > 0.05: # >5% spread is risky
            decision = "REJECTED" if decision != "REJECTED" else decision
            factor = 0.0
            reasoning.append(f"Spread too wide ({spread*100:.1f}%)")
        
        # 3. SENTIMENT CHECK (Global)
        # If sentiment is highly volatile, reduce size
        if context['sentiment']['global_trend'] == "VOLATILE":
            factor *= 0.8
            reasoning.append("Global volatility penalty.")

        final_reason = "; ".join(reasoning) if reasoning else "Standard trade conditions met."

        return {
            "decision": decision,
            "confidence": 0.88,
            "risk_adjustment_factor": min(factor, 1.5), # Cap at 1.5x
            "reasoning": final_reason
        }
