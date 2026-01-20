import json
import os
import time
import logging
from typing import Dict, Any, List

# Setup paths (assuming this file is in agents/application/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(BASE_DIR, "bot_state.json")
LEDGER_FILE = os.path.join(BASE_DIR, "full_ledger.md")

logger = logging.getLogger("SmartContext")

class SmartContext:
    def __init__(self):
        self.context = {}

    def get_full_context(self, market_data: Dict = None) -> Dict[str, Any]:
        """
        Aggregates Wallet, Ledger, Market, and Sentiment into one payload.
        """
        self.context = {
            "timestamp": time.time(),
            "wallet": self._get_wallet_status(),
            "performance": self._get_recent_performance(),
            "market_depth": self._analyze_order_book(market_data) if market_data else {},
            "sentiment": self._get_daily_sentiment() 
        }
        return self.context

    def _get_wallet_status(self) -> Dict[str, Any]:
        """Reads current bankroll and active exposure."""
        try:
            balance = 0.0
            daily_pnl = 0.0
            
            # Try to read from bot_state.json first
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
                    # We might need to fetch actual balance from API if not in state, 
                    # but for context we use what's available.
                    # The Dashboard updates state with balance? No, dashboard pulls live. 
                    # We should rely on agents passing balance or reading a shared state if available.
                    # For now, simplistic state read.
                    daily_pnl = state.get("daily_pnl", 0)
            
            return {
                "cash": balance, # Agents usually pass this in, or we implement live fetch if needed
                "daily_pnl": daily_pnl,
                "exposure": "medium" # dynamic later
            }
        except Exception as e:
            logger.error(f"Error reading wallet status: {e}")
            return {"cash": 0, "daily_pnl": 0}

    def _get_recent_performance(self) -> Dict[str, Any]:
        """Checks if we are on a winning or losing streak."""
        # Simple heuristic: Read last 5 entries from bot_state history or ledger
        # For this v1, we'll try to parse a 'history' key from state if it exists, 
        # or mock it until the Full Ledger Parser is robust.
        
        streak = "NEUTRAL"
        win_rate = "0%"
        
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
                    history = state.get("recent_trades", [])[-5:] # Assuming we add this tracking
                    if history:
                        wins = sum(1 for h in history if h.get('pnl', 0) > 0)
                        losses = len(history) - wins
                        
                        if losses >= 3: streak = "COLD_STREAK"
                        if wins >= 3: streak = "HOT_STREAK"
                        
                        win_rate = f"{(wins/len(history))*100:.0f}%"
                        
                        return {
                            "last_5_trades": history,
                            "win_rate": win_rate,
                            "current_mood": streak
                        }
        except Exception:
            pass
            
        return {"current_mood": "NEUTRAL", "win_rate": "N/A"}

    def _analyze_order_book(self, market_data: Dict) -> Dict[str, Any]:
        """Calculates Liquidity Pressure from raw market data."""
        if not market_data:
            return {}
            
        # Assuming market_data has 'bids' and 'asks' lists
        bids = market_data.get('bids', [])
        asks = market_data.get('asks', [])
        
        # Simple volume sum of top 3 levels
        bid_vol = sum(float(b['size']) for b in bids[:3]) if bids else 0
        ask_vol = sum(float(a['size']) for a in asks[:3]) if asks else 0
        
        pressure = "BALANCED"
        if bid_vol > ask_vol * 1.5: pressure = "BUY_PRESSURE"
        if ask_vol > bid_vol * 1.5: pressure = "SELL_PRESSURE"
        
        spread = 0.0
        if bids and asks:
            try:
                best_bid = float(bids[0]['price'])
                best_ask = float(asks[0]['price'])
                spread = best_ask - best_bid
            except: pass
        
        return {
            "spread": spread,
            "liquidity_pressure": pressure,
            "bid_volume_top3": bid_vol,
            "ask_volume_top3": ask_vol
        }

    def _get_daily_sentiment(self) -> Dict[str, Any]:
        """
        In a real app, this scrapes Twitter/News.
        For now, we set a 'Global Market Vibe'.
        """
        # This could be updated via the Dashboard War Room manually
        return {
            "global_trend": "VOLATILE",
            "news_impact": "HIGH_ELECTION_CYCLE"
        }
