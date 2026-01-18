"""
Supabase Client for Polyagent
Provides shared state management across all agents.
Uses direct REST API calls for reliability.
"""

import os
import json
import logging
import httpx
from datetime import datetime
from typing import Optional, Dict, Any, List
try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None

logger = logging.getLogger("SupabaseClient")


class SupabaseState:
    """
    Manages shared state across all agents using Supabase REST API.
    Falls back to local JSON if Supabase is unavailable.
    """
    
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
        self.use_local_fallback = True
        
        if self.url and self.key:
            self.use_local_fallback = False
            self.headers = {
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            }
            # Initialize official client if available
            if create_client:
                try:
                    self.client = create_client(self.url, self.key)
                except Exception as e:
                    logger.warning(f"Failed to init Supabase client: {e}")
                    self.client = None
            else:
                self.client = None
                
            logger.info("✅ Supabase REST API configured")
        else:
            self.client = None
            logger.warning("Using local JSON fallback for state (no Supabase credentials)")
    
    def _rest_url(self, table: str) -> str:
        """Get REST API URL for a table."""
        return f"{self.url}/rest/v1/{table}"
    
    # =========================================================================
    # AGENT STATE
    # =========================================================================
    
    def get_agent_state(self, agent_name: str) -> Dict[str, Any]:
        """Get the current state for an agent."""
        if not self.use_local_fallback:
            try:
                url = f"{self._rest_url('agent_state')}?agent_name=eq.{agent_name}&select=*"
                with httpx.Client(timeout=10) as client:
                    resp = client.get(url, headers=self.headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data and len(data) > 0:
                            return data[0]
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
        if not self.use_local_fallback:
            try:
                url = f"{self._rest_url('agent_state')}?agent_name=eq.{agent_name}"
                updates["updated_at"] = datetime.utcnow().isoformat()
                updates["heartbeat"] = datetime.utcnow().isoformat()
                
                with httpx.Client(timeout=10) as client:
                    resp = client.patch(url, headers=self.headers, json=updates)
                    if resp.status_code in [200, 204]:
                        logger.info(f"Updated {agent_name}: {updates}")
                        return True
                    else:
                        logger.error(f"Update failed: {resp.status_code} - {resp.text}")
            except Exception as e:
                logger.error(f"Failed to update agent state: {e}")
        return False
    
    def set_agent_running(self, agent_name: str, is_running: bool) -> bool:
        """Toggle agent running state (from dashboard). Uses upsert to create row if missing."""
        if not self.use_local_fallback:
            try:
                url = self._rest_url('agent_state')
                payload = {
                    "agent_name": agent_name,
                    "is_running": is_running,
                    "updated_at": datetime.utcnow().isoformat(),
                    "heartbeat": datetime.utcnow().isoformat()
                }
                # Use upsert headers - will INSERT if not exists, UPDATE if exists
                upsert_headers = {**self.headers, "Prefer": "resolution=merge-duplicates"}
                
                with httpx.Client(timeout=10) as client:
                    resp = client.post(url, headers=upsert_headers, json=payload)
                    if resp.status_code in [200, 201, 204]:
                        logger.info(f"✅ Set {agent_name} running={is_running} via upsert")
                        return True
                    else:
                        logger.error(f"Upsert failed: {resp.status_code} - {resp.text}")
            except Exception as e:
                logger.error(f"Failed to set agent running: {e}")
        return False
    
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

    def set_global_dry_run(self, is_dry_run: bool) -> bool:
        """Set global dry run mode."""
        if self.client:
            try:
                # Upsert config
                self.client.table("config").upsert({
                    "key": "global_dry_run", 
                    "value": json.dumps(is_dry_run)
                }, on_conflict="key").execute()
                logger.info(f"Set Global Dry Run: {is_dry_run}")
                return True
            except Exception as e:
                logger.error(f"Failed to set global dry run: {e}")
        return False
    
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
        """Log LLM activity for transparency. Uses SDK first, REST fallback."""
        payload = {
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
        }
        
        # 1. Try SDK first
        if self.client:
            try:
                self.client.table("llm_activity").insert(payload).execute()
                logger.info(f"📝 LLM activity logged via SDK: {agent}/{action_type}")
                return True
            except Exception as e:
                logger.warning(f"SDK insert failed, trying REST: {e}")
        
        # 2. REST Fallback (if SDK fails or client is None)
        if not self.use_local_fallback:
            try:
                url = self._rest_url("llm_activity")
                with httpx.Client(timeout=10) as client:
                    resp = client.post(url, headers=self.headers, json=payload)
                    if resp.status_code in [200, 201]:
                        logger.info(f"📝 LLM activity logged via REST: {agent}/{action_type}")
                        return True
                    else:
                        logger.error(f"REST insert failed: {resp.status_code} - {resp.text}")
            except Exception as e:
                logger.error(f"REST insert exception: {e}")
        
        logger.error(f"FAILED to log LLM activity for {agent} (no SDK, no REST)")
        return False

    def get_llm_activity(self, limit: int = 50, agent: str = None) -> List[Dict]:
        """Get recent LLM activity from Supabase."""
        if self.client:
            try:
                query = self.client.table("llm_activity").select("*").order("created_at", desc=True).limit(limit)
                if agent:
                    query = query.eq("agent", agent)
                result = query.execute()
                return result.data or []
            except Exception as e:
                logger.error(f"Failed to get LLM activity: {e}")
        return []


# Global singleton
_supabase_state = None

def get_supabase_state() -> SupabaseState:
    """Get the global Supabase state manager."""
    global _supabase_state
    if _supabase_state is None:
        _supabase_state = SupabaseState()
    return _supabase_state
