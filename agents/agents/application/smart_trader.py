"""
Smart Trader - Fee-Free Market Trading Agent

Trades ONLY fee-free markets (politics, sports, news - NOT 15-min crypto).
Uses LLM to analyze markets and find edge.
Holds to resolution for maximum profit (no double fees).

Strategy:
1. Find active fee-free markets
2. Use LLM to analyze question + current odds
3. If LLM confidence > market odds, bet
4. Hold to resolution (win $1 or lose entry)
"""

import os
import sys
import time
import json
import datetime
import requests
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv

# Add parent paths for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.polymarket.polymarket import Polymarket
from agents.connectors.search import perplexity_search

load_dotenv()

# =============================================================================
# SMART TRADER CONFIG
# =============================================================================

# Position sizing
MAX_POSITIONS = 5                    # Max concurrent positions
BET_PERCENT = 0.10                   # 10% of bankroll per position
MIN_BET_USD = 1.00                   # Polymarket minimum
MAX_BET_USD = 50.00                  # Max per position

# Edge requirements
MIN_EDGE_PERCENT = 10               # Need 10%+ edge to bet (LLM confidence - market odds)
MIN_CONFIDENCE = 0.60               # LLM must be 60%+ confident
MAX_MARKET_ODDS = 0.85              # Don't buy above 85¢ (not enough upside)
MIN_MARKET_ODDS = 0.15              # Don't buy below 15¢ (likely loser)

# Timing
CHECK_INTERVAL = 300                # Check every 5 minutes
MIN_TIME_TO_RESOLUTION = 3600       # Need 1+ hour to resolution (avoid last-minute chaos)

# Market filters - EXCLUDE fee markets
EXCLUDE_KEYWORDS = [
    "up or down",                   # 15-min crypto (has fees)
    "15-minute",
    "15 minute", 
    "bitcoin price",
    "ethereum price",
    "solana price",
    "xrp price",
]

# Market categories to focus on (fee-free)
FOCUS_CATEGORIES = [
    "politics",
    "sports",
    "crypto",  # Non-price crypto (e.g., "Will ETF be approved")
    "pop-culture",
    "business",
    "science",
]

# OpenAI/Perplexity for analysis
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")


class SmartTrader:
    """
    Fee-free market trader with LLM-powered analysis.
    
    Flow:
    1. Fetch active fee-free markets
    2. For each market, use LLM to estimate true probability
    3. If LLM prob > market odds + MIN_EDGE, bet YES
    4. If LLM prob < market odds - MIN_EDGE, bet NO
    5. Hold to resolution
    """
    
    AGENT_NAME = "smart_trader"
    
    def __init__(self, dry_run=True):
        self.pm = Polymarket()
        self.dry_run = dry_run
        
        # Track positions
        self.positions = {}  # market_id -> position data
        self.traded_markets = set()
        
        # Stats
        self.session_start = datetime.datetime.now()
        self.trades_made = 0
        self.total_invested = 0.0
        
        # Get initial balance
        try:
            self.initial_balance = self.pm.get_usdc_balance()
            self.address = self.pm.get_address_for_private_key()
        except:
            self.initial_balance = 0
            self.address = ""
        
        print(f"=" * 60)
        print(f"🧠 SMART TRADER - Fee-Free Markets")
        print(f"=" * 60)
        print(f"Mode: {'DRY RUN' if self.dry_run else '🔴 LIVE TRADING'}")
        print(f"Max Positions: {MAX_POSITIONS}")
        print(f"Bet Size: {BET_PERCENT*100:.0f}% (${MIN_BET_USD}-${MAX_BET_USD})")
        print(f"Min Edge Required: {MIN_EDGE_PERCENT}%")
        print(f"Strategy: LLM Analysis → Bet if Edge → Hold to Resolution")
        print(f"Balance: ${self.initial_balance:.2f}")
        print(f"=" * 60)
        print()

    def is_fee_free_market(self, market: Dict) -> bool:
        """Check if market is fee-free (not 15-min crypto)."""
        question = market.get("question", "").lower()
        description = market.get("description", "").lower()
        
        # Exclude 15-min crypto markets
        for keyword in EXCLUDE_KEYWORDS:
            if keyword in question or keyword in description:
                return False
        
        return True

    def get_fee_free_markets(self, limit=50) -> List[Dict]:
        """Fetch active fee-free markets from Polymarket."""
        try:
            url = "https://gamma-api.polymarket.com/markets"
            params = {
                "limit": limit * 2,  # Fetch more to filter
                "active": "true",
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false"
            }
            
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                print(f"Error fetching markets: {resp.status_code}")
                return []
            
            markets = resp.json()
            
            # Filter to fee-free only
            fee_free = []
            for m in markets:
                if not m.get("acceptingOrders", False):
                    continue
                if not self.is_fee_free_market(m):
                    continue
                if m.get("id") in self.traded_markets:
                    continue
                
                # Parse tokens
                clob_ids = m.get("clobTokenIds")
                if not clob_ids or clob_ids == "[]":
                    continue
                
                try:
                    import ast
                    tokens = ast.literal_eval(clob_ids) if isinstance(clob_ids, str) else clob_ids
                    if len(tokens) >= 2:
                        m["yes_token"] = tokens[0]
                        m["no_token"] = tokens[1]
                        fee_free.append(m)
                except:
                    continue
            
            return fee_free[:limit]
            
        except Exception as e:
            print(f"Error fetching markets: {e}")
            return []

    def get_market_odds(self, market: Dict) -> Tuple[float, float]:
        """Get current YES and NO prices for a market."""
        try:
            # Try to get from market data
            outcomes = market.get("outcomePrices", "[0.5, 0.5]")
            if isinstance(outcomes, str):
                import ast
                outcomes = ast.literal_eval(outcomes)
            
            yes_price = float(outcomes[0]) if outcomes else 0.5
            no_price = float(outcomes[1]) if len(outcomes) > 1 else 1 - yes_price
            
            return yes_price, no_price
        except:
            return 0.5, 0.5

    def analyze_market_with_llm(self, market: Dict) -> Dict:
        """
        Use LLM to analyze a market and estimate true probability.
        
        Returns:
            {
                "confidence": 0.0-1.0,  # LLM's estimated probability
                "reasoning": str,        # Why LLM thinks this
                "recommended_side": "YES" | "NO" | None,
                "edge": float            # confidence - market_odds
            }
        """
        question = market.get("question", "")
        description = market.get("description", "")
        yes_price, no_price = self.get_market_odds(market)
        
        # First, search for recent news/info
        search_results = ""
        if PERPLEXITY_API_KEY:
            try:
                search_results = perplexity_search(
                    f"Latest news and information about: {question}",
                    api_key=PERPLEXITY_API_KEY
                )
            except:
                pass
        
        # Build LLM prompt
        prompt = f"""You are a prediction market analyst. Analyze this market and estimate the TRUE probability of YES.

MARKET QUESTION: {question}

DESCRIPTION: {description}

CURRENT MARKET ODDS:
- YES: {yes_price*100:.1f}%
- NO: {no_price*100:.1f}%

RECENT INFORMATION:
{search_results[:2000] if search_results else "No recent search results available."}

TASK:
1. Analyze the question and available information
2. Estimate the TRUE probability that YES will win (0-100%)
3. Explain your reasoning briefly

RESPOND IN THIS EXACT JSON FORMAT:
{{"probability": <number 0-100>, "reasoning": "<brief explanation>", "confidence_level": "<low|medium|high>"}}

Only output the JSON, nothing else."""

        # Call OpenAI
        try:
            import openai
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            # Handle markdown code blocks
            if "```" in result_text:
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            result = json.loads(result_text)
            
            llm_prob = result.get("probability", 50) / 100.0
            reasoning = result.get("reasoning", "")
            conf_level = result.get("confidence_level", "medium")
            
            # Calculate edge
            yes_edge = llm_prob - yes_price
            no_edge = (1 - llm_prob) - no_price
            
            # Determine recommendation
            recommended_side = None
            edge = 0
            
            if yes_edge > MIN_EDGE_PERCENT / 100 and llm_prob >= MIN_CONFIDENCE:
                recommended_side = "YES"
                edge = yes_edge
            elif no_edge > MIN_EDGE_PERCENT / 100 and (1 - llm_prob) >= MIN_CONFIDENCE:
                recommended_side = "NO"
                edge = no_edge
            
            return {
                "confidence": llm_prob,
                "reasoning": reasoning,
                "recommended_side": recommended_side,
                "edge": edge,
                "confidence_level": conf_level,
                "yes_edge": yes_edge,
                "no_edge": no_edge
            }
            
        except Exception as e:
            print(f"   LLM analysis error: {e}")
            return {
                "confidence": 0.5,
                "reasoning": f"Error: {str(e)}",
                "recommended_side": None,
                "edge": 0
            }

    def calculate_bet_size(self) -> float:
        """Calculate bet size based on current balance."""
        try:
            balance = self.pm.get_usdc_balance()
        except:
            balance = self.initial_balance
        
        bet_size = balance * BET_PERCENT
        bet_size = max(MIN_BET_USD, min(bet_size, MAX_BET_USD))
        
        # Don't bet if we don't have enough
        if balance < MIN_BET_USD:
            return 0
        
        return bet_size

    def place_bet(self, market: Dict, side: str, analysis: Dict) -> bool:
        """Place a bet on a market."""
        market_id = market.get("id")
        question = market.get("question", "")[:50]
        yes_price, no_price = self.get_market_odds(market)
        
        # Select token and price
        if side == "YES":
            token_id = market.get("yes_token")
            entry_price = min(0.95, yes_price + 0.02)  # Slightly above for fill
        else:
            token_id = market.get("no_token")
            entry_price = min(0.95, no_price + 0.02)
        
        # Validate price range
        if entry_price < MIN_MARKET_ODDS or entry_price > MAX_MARKET_ODDS:
            print(f"   ⚠️ Price {entry_price:.2f} outside range [{MIN_MARKET_ODDS}-{MAX_MARKET_ODDS}]")
            return False
        
        bet_size = self.calculate_bet_size()
        if bet_size == 0:
            print(f"   💸 Insufficient balance")
            return False
        
        shares = bet_size / entry_price
        
        print(f"\n🎯 BETTING: {side} on '{question}...'")
        print(f"   LLM Confidence: {analysis['confidence']*100:.0f}%")
        print(f"   Market Odds: {yes_price*100:.0f}% YES / {no_price*100:.0f}% NO")
        print(f"   Edge: +{analysis['edge']*100:.1f}%")
        print(f"   Entry: ${entry_price:.2f} | Size: ${bet_size:.2f} | Shares: {shares:.1f}")
        print(f"   Reasoning: {analysis['reasoning'][:100]}...")
        
        if self.dry_run:
            print(f"   [DRY RUN] Would buy {shares:.1f} {side} shares")
            self.traded_markets.add(market_id)
            self.trades_made += 1
            self.total_invested += bet_size
            return True
        
        try:
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import BUY
            
            order_args = OrderArgs(
                token_id=str(token_id),
                price=entry_price,
                size=shares,
                side=BUY
            )
            
            signed = self.pm.client.create_order(order_args)
            result = self.pm.client.post_order(signed)
            
            if result.get("success") or result.get("status") == "matched":
                print(f"   ✅ ORDER FILLED!")
                self.traded_markets.add(market_id)
                self.trades_made += 1
                self.total_invested += bet_size
                
                # Track position
                self.positions[market_id] = {
                    "question": question,
                    "side": side,
                    "entry_price": entry_price,
                    "shares": shares,
                    "bet_size": bet_size,
                    "entry_time": datetime.datetime.now().isoformat(),
                    "analysis": analysis
                }
                
                return True
            else:
                print(f"   ⚠️ Order status: {result.get('status', 'unknown')}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False

    def scan_and_trade(self):
        """Main trading loop - scan markets and place bets."""
        print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] Scanning fee-free markets...")
        
        # Check if enabled
        try:
            with open("bot_state.json", "r") as f:
                state = json.load(f)
            if not state.get("smart_trader_running", True):
                print("Smart Trader paused via dashboard. Sleeping...")
                return
            self.dry_run = state.get("dry_run", True)
        except:
            pass
        
        # Get current balance
        try:
            balance = self.pm.get_usdc_balance()
        except:
            balance = self.initial_balance
        
        # Count current positions
        num_positions = len(self.positions)
        
        print(f"   Balance: ${balance:.2f} | Positions: {num_positions}/{MAX_POSITIONS}")
        
        if num_positions >= MAX_POSITIONS:
            print(f"   ✓ At max positions, waiting for resolutions...")
            self.save_state()
            return
        
        if balance < MIN_BET_USD:
            print(f"   💸 Insufficient balance (${balance:.2f} < ${MIN_BET_USD})")
            self.save_state()
            return
        
        # Fetch fee-free markets
        markets = self.get_fee_free_markets(limit=20)
        print(f"   Found {len(markets)} fee-free markets to analyze")
        
        if not markets:
            print(f"   No markets available")
            self.save_state()
            return
        
        # Analyze each market with LLM
        bets_placed = 0
        for market in markets:
            if num_positions + bets_placed >= MAX_POSITIONS:
                break
            
            question = market.get("question", "")[:60]
            print(f"\n   📊 Analyzing: {question}...")
            
            # Analyze with LLM
            analysis = self.analyze_market_with_llm(market)
            
            # Check if we should bet
            if analysis["recommended_side"]:
                yes_price, no_price = self.get_market_odds(market)
                price_to_check = yes_price if analysis["recommended_side"] == "YES" else no_price
                
                # Final price check
                if MIN_MARKET_ODDS <= price_to_check <= MAX_MARKET_ODDS:
                    if self.place_bet(market, analysis["recommended_side"], analysis):
                        bets_placed += 1
                        time.sleep(2)  # Rate limit
                else:
                    print(f"      ⚠️ Price {price_to_check:.2f} outside target range")
            else:
                edge_info = f"YES:{analysis.get('yes_edge', 0)*100:+.1f}% NO:{analysis.get('no_edge', 0)*100:+.1f}%"
                print(f"      ⏭️ No edge found ({edge_info})")
        
        print(f"\n   📈 Session: {self.trades_made} trades | ${self.total_invested:.2f} invested")
        self.save_state()

    def save_state(self):
        """Save state for dashboard."""
        try:
            state = {
                "smart_trader_last_activity": f"Positions: {len(self.positions)}/{MAX_POSITIONS} | Trades: {self.trades_made}",
                "smart_trader_positions": len(self.positions),
                "smart_trader_trades": self.trades_made,
                "smart_trader_invested": self.total_invested,
                "smart_trader_last_scan": datetime.datetime.now().strftime("%H:%M:%S"),
                "smart_trader_mode": "DRY RUN" if self.dry_run else "LIVE"
            }
            
            # Load existing state
            try:
                with open("bot_state.json", "r") as f:
                    existing = json.load(f)
                existing.update(state)
                state = existing
            except:
                pass
            
            with open("bot_state.json", "w") as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            print(f"Error saving state: {e}")

    def run(self):
        """Main run loop."""
        print(f"\n🧠 SMART TRADER ACTIVE")
        print(f"   Scanning every {CHECK_INTERVAL}s")
        print(f"   Focus: Fee-free markets with {MIN_EDGE_PERCENT}%+ edge")
        print()
        
        while True:
            try:
                self.scan_and_trade()
                
                print(f"\n   ⏳ Next scan in {CHECK_INTERVAL}s...")
                time.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                print("\n\nStopping Smart Trader...")
                print(f"Session stats: {self.trades_made} trades, ${self.total_invested:.2f} invested")
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(60)


if __name__ == "__main__":
    is_live = "--live" in sys.argv
    
    trader = SmartTrader(dry_run=not is_live)
    trader.run()
