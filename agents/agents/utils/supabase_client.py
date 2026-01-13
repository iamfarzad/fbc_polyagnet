"""
Supabase Client for Polyagent
Provides shared state management across all agents.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger("SupabaseClient")

# Try to import supabase
try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    logger.warning("supabase-py not installed. Run: pip install supabase")


class SupabaseState:
    """
    Manages shared state across all agents using Supabase.
    Falls back to local JSON if Supabase is unavailable.
    """
    
    def __init__(self):
        self.client: Optional[Client] = None
        self.use_local_fallback = True
        
        if HAS_SUPABASE:
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
            
            if url and key:
                try:
                    self.client = create_client(url, key)
                    self.use_local_fallback = False
                    logger.info("✅ Supabase connected")
                except Exception as e:
                    logger.error(f"Supabase connection failed: {e}")
        
        if self.use_local_fallback:
            logger.warning("Using local JSON fallback for state")
    
    # =========================================================================
    # AGENT STATE
    # =========================================================================
    
    def get_agent_state(self, agent_name: str) -> Dict[str, Any]:
        """Get the current state for an agent."""
        if self.client:
            try:
                result = self.client.table("agent_state").select("*").eq("agent_name", agent_name).single().execute()
                if result.data:
                    return result.data
            except Exception as e:
                logger.error(f"Failed to get agent state: {e}")
        
        # Fallback
        return {"agent_name": agent_name, "is_running": True, "is_dry_run": True}
    
    def is_agent_running(self, agent_name: str) -> bool:
        """Check if an agent should be running."""
        state = self.get_agent_state(agent_name)
        return state.get("is_running", True)
    
    def is_dry_run(self, agent_name: str) -> bool:
        """Check if an agent is in dry run mode."""
        state = self.get_agent_state(agent_name)
        return state.get("is_dry_run", True)
    
    def update_agent_state(self, agent_name: str, updates: Dict[str, Any]) -> bool:
        """Update agent state (heartbeat, activity, etc.)."""
        if self.client:
            try:
                updates["updated_at"] = datetime.utcnow().isoformat()
                updates["heartbeat"] = datetime.utcnow().isoformat()
                
                self.client.table("agent_state").update(updates).eq("agent_name", agent_name).execute()
                return True
            except Exception as e:
                logger.error(f"Failed to update agent state: {e}")
        return False
    
    def set_agent_running(self, agent_name: str, is_running: bool) -> bool:
        """Toggle agent running state (from dashboard)."""
        return self.update_agent_state(agent_name, {"is_running": is_running})
    
    # =========================================================================
    # CONFIG
    # =========================================================================
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a global config value."""
        if self.client:
            try:
                result = self.client.table("config").select("value").eq("key", key).single().execute()
                if result.data:
                    return json.loads(result.data["value"]) if isinstance(result.data["value"], str) else result.data["value"]
            except Exception as e:
                logger.debug(f"Config key {key} not found: {e}")
        return default
    
    def get_max_bet(self) -> float:
        """Get the current max bet setting."""
        return float(self.get_config("max_bet_usd", 2.0))
    
    def get_global_dry_run(self) -> bool:
        """Check global dry run mode."""
        return self.get_config("global_dry_run", False)
    
    # =========================================================================
    # TRADES
    # =========================================================================
    
    def log_trade(self, agent: str, market_id: str, market_question: str, 
                  outcome: str, side: str, size_usd: float, price: float,
                  token_id: str = "", status: str = "pending", 
                  reasoning: str = "") -> Optional[int]:
        """Log a trade to the database."""
        if self.client:
            try:
                result = self.client.table("trades").insert({
                    "agent": agent,
                    "market_id": market_id,
                    "market_question": market_question,
                    "outcome": outcome,
                    "side": side,
                    "size_usd": size_usd,
                    "price": price,
                    "token_id": token_id,
                    "status": status,
                    "reasoning": reasoning
                }).execute()
                
                if result.data:
                    return result.data[0]["id"]
            except Exception as e:
                logger.error(f"Failed to log trade: {e}")
        return None
    
    def update_trade(self, trade_id: int, updates: Dict[str, Any]) -> bool:
        """Update a trade (e.g., mark as filled, add PnL)."""
        if self.client:
            try:
                self.client.table("trades").update(updates).eq("id", trade_id).execute()
                return True
            except Exception as e:
                logger.error(f"Failed to update trade: {e}")
        return False
    
    def get_recent_trades(self, agent: str = None, limit: int = 50) -> List[Dict]:
        """Get recent trades, optionally filtered by agent."""
        if self.client:
            try:
                query = self.client.table("trades").select("*").order("created_at", desc=True).limit(limit)
                if agent:
                    query = query.eq("agent", agent)
                result = query.execute()
                return result.data or []
            except Exception as e:
                logger.error(f"Failed to get trades: {e}")
        return []
    
    # =========================================================================
    # LLM ACTIVITY
    # =========================================================================
    
    def log_llm_activity(self, agent: str, action_type: str, market_question: str,
                         prompt_summary: str, reasoning: str, conclusion: str,
                         confidence: float, data_sources: List[str] = None,
                         tokens_used: int = 0, cost_usd: float = 0,
                         duration_ms: int = 0) -> bool:
        """Log LLM activity for transparency."""
        if self.client:
            try:
                self.client.table("llm_activity").insert({
                    "agent": agent,
                    "action_type": action_type,
                    "market_question": market_question,
                    "prompt_summary": prompt_summary,
                    "reasoning": reasoning,
                    "conclusion": conclusion,
                    "confidence": confidence,
                    "data_sources": data_sources or [],
                    "tokens_used": tokens_used,
                    "cost_usd": cost_usd,
                    "duration_ms": duration_ms
                }).execute()
                return True
            except Exception as e:
                logger.error(f"Failed to log LLM activity: {e}")
        return False


# Global singleton
_supabase_state = None

def get_supabase_state() -> SupabaseState:
    """Get the global Supabase state manager."""
    global _supabase_state
    if _supabase_state is None:
        _supabase_state = SupabaseState()
    return _supabase_state
