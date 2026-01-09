"""
Shared Context Manager for Multi-Agent Coordination

All agents read/write to a shared context that tracks:
- Open positions across all agents
- Recent trades and their outcomes
- Capital allocation per agent
- Market blacklist (already traded)
- Global risk metrics
"""

import os
import json
import time
import fcntl
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger("Context")

CONTEXT_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "shared_context.json")


@dataclass
class Position:
    market_id: str
    market_question: str
    agent: str  # "safe", "scalper", "copy"
    outcome: str  # "YES", "NO", "UP", "DOWN"
    entry_price: float
    size_usd: float
    timestamp: str
    token_id: str = ""


@dataclass 
class Trade:
    market_id: str
    agent: str
    outcome: str
    size_usd: float
    price: float
    timestamp: str
    status: str  # "pending", "filled", "failed"
    pnl: float = 0.0


@dataclass
class LLMActivity:
    """Tracks a single LLM interaction for transparency."""
    id: str
    agent: str  # "safe", "scalper", "copy"
    timestamp: str
    action_type: str  # "research", "validate", "discover", "analyze"
    market_question: str
    prompt_summary: str  # First 200 chars of prompt
    reasoning: str  # LLM's reasoning/analysis
    conclusion: str  # BET/PASS/etc
    confidence: float
    data_sources: List[str]  # What info the LLM found
    duration_ms: int
    tokens_used: int = 0
    cost_usd: float = 0.0


class SharedContext:
    """
    Thread-safe shared context for multi-agent coordination.
    Uses file locking to prevent race conditions.
    """
    
    # Capital allocation percentages per agent
    DEFAULT_ALLOCATION = {
        "safe": 0.50,      # 50% for safe high-prob bets
        "scalper": 0.30,   # 30% for 15-min crypto scalping  
        "copy": 0.20,      # 20% for copy trading
    }
    
    # Risk limits
    MAX_POSITIONS_TOTAL = 10
    MAX_POSITIONS_PER_MARKET = 1
    MAX_EXPOSURE_PCT = 0.80  # Max 80% of balance in positions
    TRADE_COOLDOWN_SEC = 30  # Min time between trades on same market
    
    def __init__(self, context_file: str = CONTEXT_FILE):
        self.context_file = context_file
        self._ensure_file()
    
    def _ensure_file(self):
        """Create context file if it doesn't exist."""
        if not os.path.exists(self.context_file):
            self._write({
                "positions": [],
                "recent_trades": [],
                "blacklist": [],  # market_ids to avoid
                "allocation": self.DEFAULT_ALLOCATION,
                "total_balance": 0.0,
                "last_update": datetime.now().isoformat(),
                "agent_status": {
                    "safe": {"active": True, "last_action": None},
                    "scalper": {"active": True, "last_action": None},
                    "copy": {"active": True, "last_action": None},
                }
            })
    
    def _read(self) -> Dict:
        """Read context with file locking."""
        try:
            with open(self.context_file, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                data = json.load(f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return data
        except (json.JSONDecodeError, FileNotFoundError):
            self._ensure_file()
            return self._read()
    
    def _write(self, data: Dict):
        """Write context with file locking."""
        data["last_update"] = datetime.now().isoformat()
        with open(self.context_file, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(data, f, indent=2)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    # =========== QUERY METHODS ===========
    
    def get_open_positions(self, agent: str = None) -> List[Dict]:
        """Get all open positions, optionally filtered by agent."""
        ctx = self._read()
        positions = ctx.get("positions", [])
        if agent:
            positions = [p for p in positions if p.get("agent") == agent]
        return positions
    
    def get_position_for_market(self, market_id: str) -> Optional[Dict]:
        """Check if any agent has a position in this market."""
        positions = self.get_open_positions()
        for p in positions:
            if p.get("market_id") == market_id:
                return p
        return None
    
    def get_recent_trades(self, limit: int = 20) -> List[Dict]:
        """Get recent trades across all agents."""
        ctx = self._read()
        trades = ctx.get("recent_trades", [])
        return sorted(trades, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]
    
    def get_allocated_capital(self, agent: str, total_balance: float) -> float:
        """Get the capital allocated to a specific agent."""
        ctx = self._read()
        allocation = ctx.get("allocation", self.DEFAULT_ALLOCATION)
        pct = allocation.get(agent, 0.10)
        return total_balance * pct
    
    def get_available_capital(self, agent: str, total_balance: float) -> float:
        """Get available capital for an agent (allocated minus in positions)."""
        allocated = self.get_allocated_capital(agent, total_balance)
        positions = self.get_open_positions(agent)
        in_positions = sum(p.get("size_usd", 0) for p in positions)
        return max(0, allocated - in_positions)
    
    def get_total_exposure(self) -> float:
        """Get total USD in all open positions."""
        positions = self.get_open_positions()
        return sum(p.get("size_usd", 0) for p in positions)
    
    def is_market_blacklisted(self, market_id: str) -> bool:
        """Check if market is blacklisted."""
        ctx = self._read()
        return market_id in ctx.get("blacklist", [])
    
    def get_last_trade_time(self, market_id: str) -> Optional[float]:
        """Get timestamp of last trade on this market."""
        trades = self.get_recent_trades(100)
        for t in trades:
            if t.get("market_id") == market_id:
                try:
                    ts = datetime.fromisoformat(t.get("timestamp", ""))
                    return ts.timestamp()
                except:
                    pass
        return None
    
    # =========== VALIDATION METHODS ===========
    
    def can_trade(self, agent: str, market_id: str, size_usd: float, total_balance: float) -> tuple[bool, str]:
        """
        Check if an agent can execute a trade.
        Returns (can_trade, reason).
        """
        # Check if market is blacklisted
        if self.is_market_blacklisted(market_id):
            return False, "Market is blacklisted"
        
        # Check if already have position in this market
        existing = self.get_position_for_market(market_id)
        if existing:
            return False, f"Already have position via {existing.get('agent')} agent"
        
        # Check position count
        all_positions = self.get_open_positions()
        if len(all_positions) >= self.MAX_POSITIONS_TOTAL:
            return False, f"Max positions ({self.MAX_POSITIONS_TOTAL}) reached"
        
        # Check total exposure
        current_exposure = self.get_total_exposure()
        max_exposure = total_balance * self.MAX_EXPOSURE_PCT
        if current_exposure + size_usd > max_exposure:
            return False, f"Would exceed max exposure (${current_exposure + size_usd:.2f} > ${max_exposure:.2f})"
        
        # Check agent's allocated capital
        available = self.get_available_capital(agent, total_balance)
        if size_usd > available:
            return False, f"Exceeds {agent}'s available capital (${size_usd:.2f} > ${available:.2f})"
        
        # Check trade cooldown
        last_trade = self.get_last_trade_time(market_id)
        if last_trade and (time.time() - last_trade) < self.TRADE_COOLDOWN_SEC:
            return False, f"Trade cooldown active ({self.TRADE_COOLDOWN_SEC}s)"
        
        return True, "OK"
    
    # =========== UPDATE METHODS ===========
    
    def add_position(self, position: Position):
        """Record a new open position."""
        ctx = self._read()
        positions = ctx.get("positions", [])
        positions.append(asdict(position))
        ctx["positions"] = positions
        self._write(ctx)
        logger.info(f"[{position.agent}] Added position: {position.market_question[:30]}...")
    
    def remove_position(self, market_id: str):
        """Remove a closed position."""
        ctx = self._read()
        positions = ctx.get("positions", [])
        ctx["positions"] = [p for p in positions if p.get("market_id") != market_id]
        self._write(ctx)
    
    def add_trade(self, trade: Trade):
        """Record a trade (for history)."""
        ctx = self._read()
        trades = ctx.get("recent_trades", [])
        trades.append(asdict(trade))
        # Keep last 100 trades
        ctx["recent_trades"] = trades[-100:]
        self._write(ctx)
    
    def blacklist_market(self, market_id: str, reason: str = ""):
        """Add market to blacklist."""
        ctx = self._read()
        blacklist = ctx.get("blacklist", [])
        if market_id not in blacklist:
            blacklist.append(market_id)
            ctx["blacklist"] = blacklist
            self._write(ctx)
            logger.info(f"Blacklisted market {market_id}: {reason}")
    
    def update_agent_status(self, agent: str, action: str):
        """Update an agent's last action."""
        ctx = self._read()
        if "agent_status" not in ctx:
            ctx["agent_status"] = {}
        ctx["agent_status"][agent] = {
            "active": True,
            "last_action": action,
            "timestamp": datetime.now().isoformat()
        }
        self._write(ctx)
    
    def set_allocation(self, allocation: Dict[str, float]):
        """Update capital allocation percentages."""
        ctx = self._read()
        ctx["allocation"] = allocation
        self._write(ctx)
    
    def update_balance(self, balance: float):
        """Update the total balance snapshot."""
        ctx = self._read()
        ctx["total_balance"] = balance
        self._write(ctx)
    
    # =========== UTILITY METHODS ===========
    
    def get_summary(self) -> Dict:
        """Get a summary of current state for logging/display."""
        ctx = self._read()
        positions = ctx.get("positions", [])
        
        return {
            "total_positions": len(positions),
            "positions_by_agent": {
                "safe": len([p for p in positions if p.get("agent") == "safe"]),
                "scalper": len([p for p in positions if p.get("agent") == "scalper"]),
                "copy": len([p for p in positions if p.get("agent") == "copy"]),
            },
            "total_exposure": self.get_total_exposure(),
            "allocation": ctx.get("allocation", {}),
            "blacklisted_markets": len(ctx.get("blacklist", [])),
            "last_update": ctx.get("last_update"),
        }
    
    def broadcast(self, agent: str, message: str, data: Dict = None):
        """
        Broadcast a message to other agents (stored in context).
        Useful for signals like "high confidence opportunity" or "risk alert".
        """
        ctx = self._read()
        if "broadcasts" not in ctx:
            ctx["broadcasts"] = []
        
        ctx["broadcasts"].append({
            "from": agent,
            "message": message,
            "data": data or {},
            "timestamp": datetime.now().isoformat(),
            "read_by": []
        })
        
        # Keep last 50 broadcasts
        ctx["broadcasts"] = ctx["broadcasts"][-50:]
        self._write(ctx)
    
    def get_broadcasts(self, agent: str, unread_only: bool = True) -> List[Dict]:
        """Get broadcasts, optionally only unread ones for this agent."""
        ctx = self._read()
        broadcasts = ctx.get("broadcasts", [])
        
        if unread_only:
            broadcasts = [b for b in broadcasts if agent not in b.get("read_by", [])]
        
        # Mark as read
        for b in broadcasts:
            if agent not in b.get("read_by", []):
                b["read_by"].append(agent)
        
        ctx["broadcasts"] = ctx.get("broadcasts", [])
        self._write(ctx)
        
        return broadcasts

    # =========== LLM ACTIVITY TRACKING ===========
    
    def log_llm_activity(self, activity: LLMActivity):
        """Log an LLM interaction for the activity feed."""
        ctx = self._read()
        if "llm_activity" not in ctx:
            ctx["llm_activity"] = []
        
        ctx["llm_activity"].append(asdict(activity))
        
        # Keep last 100 activities
        ctx["llm_activity"] = ctx["llm_activity"][-100:]
        self._write(ctx)
        logger.info(f"[{activity.agent}] LLM {activity.action_type}: {activity.conclusion} ({activity.confidence:.0%})")
    
    def get_llm_activity(self, limit: int = 50, agent: str = None) -> List[Dict]:
        """Get recent LLM activity, optionally filtered by agent."""
        ctx = self._read()
        activities = ctx.get("llm_activity", [])
        
        if agent:
            activities = [a for a in activities if a.get("agent") == agent]
        
        # Sort by timestamp descending
        activities = sorted(activities, key=lambda x: x.get("timestamp", ""), reverse=True)
        return activities[:limit]
    
    def get_llm_stats(self) -> Dict:
        """Get aggregate LLM usage statistics."""
        activities = self.get_llm_activity(limit=1000)
        
        total_calls = len(activities)
        total_tokens = sum(a.get("tokens_used", 0) for a in activities)
        total_cost = sum(a.get("cost_usd", 0) for a in activities)
        avg_confidence = sum(a.get("confidence", 0) for a in activities) / max(total_calls, 1)
        
        # By agent
        by_agent = {}
        for agent in ["safe", "scalper", "copy"]:
            agent_acts = [a for a in activities if a.get("agent") == agent]
            by_agent[agent] = {
                "calls": len(agent_acts),
                "avg_confidence": sum(a.get("confidence", 0) for a in agent_acts) / max(len(agent_acts), 1),
                "bet_rate": len([a for a in agent_acts if a.get("conclusion") == "BET"]) / max(len(agent_acts), 1)
            }
        
        # Recent decisions
        decisions = {
            "BET": len([a for a in activities if a.get("conclusion") == "BET"]),
            "PASS": len([a for a in activities if a.get("conclusion") == "PASS"]),
            "ERROR": len([a for a in activities if "error" in a.get("conclusion", "").lower()])
        }
        
        return {
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "avg_confidence": avg_confidence,
            "by_agent": by_agent,
            "decisions": decisions
        }


# Singleton instance
_context = None

def get_context() -> SharedContext:
    """Get the shared context singleton."""
    global _context
    if _context is None:
        _context = SharedContext()
    return _context
