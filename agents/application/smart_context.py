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

    def get_full_context(self, market_data: Dict = None, market_question: str = "") -> Dict[str, Any]:
        """
        Aggregates Wallet, Ledger, Market, and Sentiment into one payload.
        """
        self.context = {
            "timestamp": time.time(),
            "wallet": self._get_wallet_status(),
            "performance": self._get_recent_performance(),
            "market_depth": self._analyze_order_book(market_data) if market_data else {},
            "sentiment": self._get_daily_sentiment(),
            "whale_positions": self._get_whale_positions(market_data) if market_data else {},
            "comment_sentiment": self._analyze_comment_sentiment(market_question) if market_question else {},
            "market_question": market_question
        }
        return self.context

    def _get_wallet_status(self) -> Dict[str, Any]:
        """Reads current bankroll and active exposure."""
        try:
            balance = 0.0
            daily_pnl = 0.0
            
            # 1. Try SharedContext first (Truth)
            try:
                from agents.utils.context import get_context
                ctx = get_context()
                if ctx:
                    # SharedContext maintains state in memory or shared file
                    # We might need to expose balance getter in SharedContext if not public
                    # But for now, let's try to read key files directly if ctx doesn't give it
                    pass
            except ImportError:
                pass

            # 2. Try to read from bot_state.json
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
                    daily_pnl = state.get("daily_pnl", 0)
                    # If agents are writing balance to state, use it
                    if "balance" in state:
                        balance = float(state["balance"])
            
            # 3. Fallback: Shared Context JSON directly (if we can find it)
            SHARED_FILE = os.path.join(BASE_DIR, "shared_context.json")
            if balance == 0.0 and os.path.exists(SHARED_FILE):
                try:
                    with open(SHARED_FILE, "r") as f:
                        shared = json.load(f)
                        if "total_balance" in shared:
                            balance = float(shared["total_balance"])
                except: pass

            return {
                "cash": balance, 
                "daily_pnl": daily_pnl,
                "exposure": "medium" # dynamic later
            }
        except Exception as e:
            logger.error(f"Error reading wallet status: {e}")
            return {"cash": 0, "daily_pnl": 0}

    def _get_recent_performance(self) -> Dict[str, Any]:
        """Checks if we are on a winning or losing streak."""
        streak = "NEUTRAL"
        win_rate = "0%"
        
        try:
            history = []
            
            # 1. Try SharedContext JSON first (Truth)
            SHARED_FILE = os.path.join(BASE_DIR, "shared_context.json")
            if os.path.exists(SHARED_FILE):
                try:
                    with open(SHARED_FILE, "r") as f:
                        shared = json.load(f)
                        history = shared.get("recent_trades", [])
                except: pass
            
            # 2. Fallback to bot_state.json
            if not history and os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    state = json.load(f)
                    history = state.get("recent_trades", [])

            # Analyze history
            if history:
                # Get last 5
                recent = history[-5:]
                wins = sum(1 for h in recent if h.get('pnl', 0) > 0)
                losses = len(recent) - wins
                
                if losses >= 3: streak = "COLD_STREAK"
                if wins >= 3: streak = "HOT_STREAK"
                
                win_rate = f"{(wins/len(recent))*100:.0f}%"
                
                return {
                    "last_5_trades": recent,
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

    def _get_whale_positions(self, market_data: Dict) -> Dict[str, Any]:
        """
        Analyze whale positions from market data.
        In production, this would query actual whale wallet addresses.
        """
        try:
            # Mock implementation - in production, query Polymarket API for large positions
            # or track known whale addresses from whales.json
            
            # Try to get whale addresses from config
            whale_file = os.path.join(BASE_DIR, "whale_addresses.json")
            if os.path.exists(whale_file):
                with open(whale_file, "r") as f:
                    whales = json.load(f)
                    logger.debug(f"Loaded {len(whales.get('whales', []))} whale addresses")
            
            # For now, return neutral state
            return {
                "dominant_side": None,
                "whale_count": 0,
                "total_volume": 0
            }
        except Exception as e:
            logger.error(f"Error getting whale positions: {e}")
            return {"dominant_side": None, "whale_count": 0, "total_volume": 0}

    def _analyze_comment_sentiment(self, market_question: str) -> Dict[str, Any]:
        """
        Analyze comment sentiment for a market.
        In production, this would use OpenAI to analyze Polymarket comments.
        """
        if not market_question:
            return {"sentiment_score": 0, "comment_count": 0}
        
        try:
            # Import MistakeAnalyzer to use OpenAI if available
            try:
                from openai import OpenAI
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    client = OpenAI(api_key=api_key)
                    
                    prompt = f"""Analyze the sentiment of this market question:
"{market_question}"

Rate it on a scale from -1.0 (extremely bearish/negative) to 1.0 (extremely bullish/positive).
Consider the language, uncertainty, and market implications.

Return JSON only: {{"sentiment_score": float, "comment_count": 0, "analysis": "brief explanation"}}"""
                    
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        temperature=0.1
                    )
                    
                    return json.loads(response.choices[0].message.content)
            except Exception as e:
                logger.debug(f"Could not analyze sentiment with AI: {e}")
            
            # Fallback: simple keyword-based analysis
            positive_words = ["will", "sure", "certain", "definitely", "yes", "win"]
            negative_words = ["won't", "unlikely", "maybe", "uncertain", "no", "lose"]
            
            question_lower = market_question.lower()
            pos_count = sum(1 for word in positive_words if word in question_lower)
            neg_count = sum(1 for word in negative_words if word in question_lower)
            
            if pos_count > neg_count:
                score = 0.3
            elif neg_count > pos_count:
                score = -0.3
            else:
                score = 0.0
            
            return {
                "sentiment_score": score,
                "comment_count": 0,
                "analysis": "Simple keyword-based analysis"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing comment sentiment: {e}")
            return {"sentiment_score": 0, "comment_count": 0}

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
