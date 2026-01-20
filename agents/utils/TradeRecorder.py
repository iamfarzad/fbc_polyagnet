"""
Utility module to standardize trade recording across all agents.

This module provides a centralized way for all agents to record trades
to bot_state.json, ensuring SmartContext can accurately calculate Mood
and performance metrics.
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger("TradeRecorder")

# Path to bot_state.json
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(BASE_DIR, "bot_state.json")


def record_trade(
    agent_name: str,
    market: str,
    side: str,  # "BUY" or "SELL"
    amount: float,
    price: float,
    token_id: Optional[str] = None,
    pnl: Optional[float] = None,
    outcome: Optional[str] = None,
    reasoning: Optional[str] = None
) -> bool:
    """
    Record a trade to bot_state.json recent_trades list.
    
    Args:
        agent_name: Name of the agent making the trade (e.g., "esports_trader")
        market: Market title or question
        side: "BUY" or "SELL"
        amount: Trade amount in USDC
        price: Price per share
        token_id: Optional token/market ID
        pnl: Optional realized PnL (for closing trades)
        outcome: Optional outcome name (e.g., "YES", "NO")
        reasoning: Optional trade reasoning
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Load current state
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
        else:
            state = {"recent_trades": []}
        
        # Initialize recent_trades if not present
        if "recent_trades" not in state:
            state["recent_trades"] = []
        
        # Create trade record
        trade_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent": agent_name,
            "market": market,
            "side": side,
            "amount_usd": float(amount),
            "price": float(price),
            "token_id": token_id,
            "pnl": float(pnl) if pnl is not None else None,
            "outcome": outcome,
            "reasoning": reasoning
        }
        
        # Add to recent trades
        state["recent_trades"].append(trade_record)
        
        # Keep only last 100 trades to prevent file bloat
        if len(state["recent_trades"]) > 100:
            state["recent_trades"] = state["recent_trades"][-100:]
        
        # Save state
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        
        logger.info(f"Recorded trade: {agent_name} {side} ${amount:.2f} on {market}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to record trade: {e}")
        return False


def get_recent_trades(limit: int = 10, agent_name: Optional[str] = None) -> list:
    """
    Get recent trades from bot_state.json.
    
    Args:
        limit: Maximum number of trades to return
        agent_name: Optional filter by agent name
    
    Returns:
        list: List of trade records
    """
    try:
        if not os.path.exists(STATE_FILE):
            return []
        
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
        
        trades = state.get("recent_trades", [])
        
        # Filter by agent if specified
        if agent_name:
            trades = [t for t in trades if t.get("agent") == agent_name]
        
        # Return last N trades
        return trades[-limit:] if limit else trades
        
    except Exception as e:
        logger.error(f"Failed to get recent trades: {e}")
        return []


def calculate_performance_metrics(agent_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate performance metrics from recent trades.
    
    Args:
        agent_name: Optional filter by agent name
    
    Returns:
        dict: Performance metrics including win_rate, avg_pnl, streak, etc.
    """
    try:
        trades = get_recent_trades(limit=100, agent_name=agent_name)
        
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "total_pnl": 0.0,
                "streak": "NEUTRAL"
            }
        
        # Filter only closed trades (with PnL)
        closed_trades = [t for t in trades if t.get("pnl") is not None]
        
        if not closed_trades:
            return {
                "total_trades": len(trades),
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "total_pnl": 0.0,
                "streak": "NEUTRAL",
                "note": "No closed trades yet"
            }
        
        # Calculate metrics
        wins = sum(1 for t in closed_trades if t["pnl"] > 0)
        total_trades = len(closed_trades)
        total_pnl = sum(t["pnl"] for t in closed_trades)
        avg_pnl = total_pnl / total_trades
        
        win_rate = (wins / total_trades) * 100
        
        # Determine streak (last 5 trades)
        recent_trades = closed_trades[-5:]
        recent_wins = sum(1 for t in recent_trades if t["pnl"] > 0)
        recent_losses = len(recent_trades) - recent_wins
        
        if recent_losses >= 3:
            streak = "COLD_STREAK"
        elif recent_wins >= 3:
            streak = "HOT_STREAK"
        else:
            streak = "NEUTRAL"
        
        return {
            "total_trades": total_trades,
            "win_rate": round(win_rate, 1),
            "avg_pnl": round(avg_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "streak": streak,
            "last_5_trades": recent_trades
        }
        
    except Exception as e:
        logger.error(f"Failed to calculate performance metrics: {e}")
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "total_pnl": 0.0,
            "streak": "NEUTRAL"
        }


def update_agent_activity(agent_name: str, activity: str, extra_data: Optional[Dict] = None):
    """
    Update agent activity status in bot_state.json.
    
    Args:
        agent_name: Name of the agent (e.g., "esports_trader")
        activity: Activity description
        extra_data: Optional additional data to store
    """
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
        else:
            state = {}
        
        # Update last activity
        state[f"{agent_name}_last_activity"] = activity
        state[f"{agent_name}_last_scan"] = datetime.utcnow().strftime("%H:%M:%S")
        
        # Add extra data if provided
        if extra_data:
            for key, value in extra_data.items():
                state[key] = value
        
        # Save state
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
            
    except Exception as e:
        logger.error(f"Failed to update agent activity: {e}")
