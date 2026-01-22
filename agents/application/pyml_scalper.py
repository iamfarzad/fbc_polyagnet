"""
SMART MAKER-ONLY SCALPER (Production Ready)
Optimized for 2026 Polymarket Fee Structure (~0% Maker Fees).

STRATEGY:
1. Discovery: Scans 15-min "Up or Down" crypto markets.
2. Entry: Smart Maker (Queue Jumper). Jumps big walls, joins small ones.
3. Exit: Smart Maker Chasing. 100% Limit orders, chasing best ask every 3s.
4. Safety: Dynamic timeouts (1s vs 10s) based on Binance volatility.
"""

import os
import sys
import time
import json
import ast
import threading
import datetime
import requests
from collections import deque
from dotenv import load_dotenv
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY, SELL
import websocket

# Import Polymarket wrapper and Gamma client
try:
    from agents.polymarket.polymarket import Polymarket
    from agents.polymarket.gamma import GammaMarketClient
except ImportError:
    # Fallback for running as script - try the correct module path
    try:
        from agents.agents.polymarket.polymarket import Polymarket
        from agents.agents.polymarket.gamma import GammaMarketClient
        print("Direct module import successful")
    except ImportError:
        print(f"All import attempts failed")
        print(f"Current dir: {os.getcwd()}")
        raise

# Import Context
try:
    from agents.utils.context import get_context, Position, Trade
    HAS_CONTEXT = True
except ImportError:
    HAS_CONTEXT = False

# Robust Supabase Import
try:
    from agents.utils.supabase_client import get_supabase_state
    HAS_SUPABASE = True
except ImportError:
    try:
        from agents.agents.utils.supabase_client import get_supabase_state
        HAS_SUPABASE = True
    except ImportError:
        HAS_SUPABASE = False
        get_supabase_state = None

# --- NEW INTELLIGENCE LAYER IMPORTS ---
from agents.application.smart_context import SmartContext
from agents.application.universal_analyst import UniversalAnalyst
from agents.utils.config import load_config
from agents.utils.TradeRecorder import record_trade, update_agent_activity

load_dotenv()

# =============================================================================
# =============================================================================
# =============================================================================
# 4-WEEK SCALE CONFIG (MAX $500 CEILING)
# =============================================================================

# Portfolio & Size
MAX_POSITIONS = 3                   # Start with 3
BET_PERCENT = 0.99                  # ALL IN (Phoenix Mode)
MIN_BET_USD = 0.10                  # <--- LOWERED TO $0.10 FOR EXTREME RECOVERY
MAX_BET_USD = 500.00                
MAX_DAILY_DRAWDOWN_PCT = 999.0      # <--- IGNORE ALL LOSS LIMITS

# Sniper Execution
PRICE_CAP = 0.96                    
BASE_MOMENTUM_THRESHOLD = 0.0005    

# Queue Mastery
QUEUE_JUMP_THRESHOLD = 0.0          
MAKER_OFFSET = 0.001                
LIMIT_ORDER_TIMEOUT_CALM = 45       
LIMIT_ORDER_TIMEOUT_VOLATILE = 15    
EXIT_MAKER_TIMEOUT = 10             

# Smart Maker-Only Exit
TAKE_PROFIT_PCT = 0.015             
PANIC_THRESHOLD_PCT = -0.050        

# Binance & Signal
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
BINANCE_SYMBOLS = {
    "btcusdt": "bitcoin",
    "ethusdt": "ethereum",
    "solusdt": "solana",
    "xrpusdt": "xrp"
}
MIN_LIQUIDITY_USD = 15              
MIN_SENTIMENT_CONFIDENCE = 0.30     


class CryptoScalper:
    AGENT_NAME = "scalper_hybrid"

    def __init__(self, dry_run=True):
        self.pm = Polymarket()
        self.gamma = GammaMarketClient()
        self.dry_run = dry_run
        
        # Initialize Shared Context
        try:
            from agents.utils.context import get_context, LLMActivity
            self.context = get_context()
            self.LLMActivity = LLMActivity
        except ImportError:
            try:
                from agents.agents.utils.context import get_context, LLMActivity
                self.context = get_context()
                self.LLMActivity = LLMActivity
            except:
                self.context = None
                self.LLMActivity = None


        # State Tracking
        self.active_positions = {}      # token_id -> position_data
        self.pending_orders = {}        # order_id -> order_metadata
        self.traded_markets = []        # market_id cache

        # Stats
        self.session_start = datetime.datetime.now()
        self.initial_balance = self.get_balance()
        self.total_orders = 0
        self.total_fills = 0
        self.panic_exits = 0
        self.total_pnl = 0.0
        self.circuit_breaker_triggered = False

        # Data Feeds
        self.binance_history = {k: deque(maxlen=200) for k in BINANCE_SYMBOLS}
        self.binance_connected = False

        # Market Timing Intelligence
        self.market_creation_times = []  # Track when markets are created
        self.last_market_scan = 0
        self.market_scan_interval = 30  # Scan every 30s to detect new markets

        # --- INTELLIGENCE LAYER INIT ---
        self.config = load_config("scalper")
        self.active = self.config.get("active", True)
        self.smart_context = SmartContext()
        self.analyst = UniversalAnalyst()
        self.use_llm = self.config.get("use_llm_sentiment", False)
        print(f"🧠 Intelligence Layer Active: LLM={self.use_llm}")

        # Init Components
        self.redeemer = None
        try:
            from agents.utils.auto_redeem import AutoRedeemer
            self.redeemer = AutoRedeemer()
        except: pass

        print(f"="*60)
        print(f"🧬 SMART MAKER-ONLY SCALPER (Production Ready)")
        print(f"="*60)
        print(f"Mode: {'DRY RUN' if self.dry_run else '🔴 LIVE'}")
        print(f"Timeouts: {LIMIT_ORDER_TIMEOUT_VOLATILE}s (Volatile) - {LIMIT_ORDER_TIMEOUT_CALM}s (Calm)")
        print(f"Exit: Smart Maker Chasing (Profit: {TAKE_PROFIT_PCT*100}% | Stop: {PANIC_THRESHOLD_PCT*100}%)")
        print(f"Queue Logic: Jump wall if size > ${QUEUE_JUMP_THRESHOLD}")
        print(f"="*60)

        # Price caching for performance
        self.price_cache = {}  # token_id -> (timestamp, price_data)
        self._init_polymarket_websocket()

        # Self-Learning State
        self.last_learning_time = 0
        self.LEARNING_INTERVAL = 3600 * 4  # Run analysis every 4 hours

    def run_learning_cycle(self):
        """Run post-trade analysis to learn from mistakes."""
        # Late import to avoid circular dependencies if any
        try:
            from agents.utils.mistake_analyzer import MistakeAnalyzer
            analyzer = MistakeAnalyzer(agent_name=self.AGENT_NAME)
        except ImportError:
            return

        now = time.time()
        if now - self.last_learning_time > self.LEARNING_INTERVAL:
            try:
                print("   🧠 Starting Self-Learning Cycle...")
                lessons = analyzer.analyze_completed_trades(limit=5)
                if lessons:
                    print(f"   🎓 Learned {len(lessons)} new lessons from recent trades.")
                else:
                    print(f"   🧠 No new lessons to learn this cycle.")
                self.last_learning_time = now
            except Exception as e:
                print(f"   ⚠️ Self-learning cycle failed: {e}")

    def _log(self, action, question, reasoning, confidence=1.0, conclusion="EXECUTED"):
        """Log to Dashboard Terminal."""
        try:
            if HAS_SUPABASE:
                supa = get_supabase_state()
                supa.log_llm_activity(
                    agent=self.AGENT_NAME,
                    action_type=action,
                    market_question=question,
                    prompt_summary=f"{action}: {question[:40]}...",
                    reasoning=reasoning,
                    conclusion=conclusion,
                    confidence=confidence,
                    data_sources=["Binance OrderBook", "Polymarket CLOB"],
                    tokens_used=0,
                    cost_usd=0.0,
                    duration_ms=0
                )
        except Exception as e:
            print(f"   ⚠️ Log Error: {e}")

    def _init_polymarket_websocket(self):
        """Initialize Polymarket websocket for real-time price updates."""
        def price_update_callback(data):
            """Handle incoming market data updates."""
            try:
                # Parse market data and cache prices
                if 'asset_id' in data and 'price' in data:
                    token_id = data['asset_id']
                    price = float(data.get('price', 0))
                    bid = float(data.get('best_bid', price * 0.99))
                    ask = float(data.get('best_ask', price * 1.01))
                    bid_size = float(data.get('bid_size', 1000))

                    price_data = (price, bid, bid_size, ask)
                    self.price_cache[token_id] = (time.time(), price_data)
                    print(f"   📈 WS Price Update: {token_id[:8]}... @ ${price:.4f}")

                elif 'updates' in data:
                    # Handle batch updates
                    for update in data['updates']:
                        if 'asset_id' in update:
                            token_id = update['asset_id']
                            price = float(update.get('price', 0))
                            bid = float(update.get('best_bid', price * 0.99))
                            ask = float(update.get('best_ask', price * 1.01))
                            bid_size = float(update.get('bid_size', 1000))

                            price_data = (price, bid, bid_size, ask)
                            self.price_cache[token_id] = (time.time(), price_data)

            except Exception as e:
                print(f"   ⚠️ WS callback error: {e}")

        # Add callback and connect to market channel
        self.pm.add_ws_callback('market', price_update_callback)

        # Connect to websocket (will auto-subscribe to assets as needed)
        if not self.pm.connect_websocket(channel_type="market"):
            print("   ⚠️ Polymarket WS connection failed - using REST polling")
        else:
            print("   📡 Polymarket WS connected for real-time updates")

    def subscribe_to_market_assets(self, token_ids: list):
        """Subscribe to specific market assets for real-time updates."""
        if self.pm.ws_connection:
            self.pm.subscribe_to_assets(token_ids, channel_type="market")
            print(f"   📡 Subscribed to {len(token_ids)} market assets")

    # -------------------------------------------------------------------------
    # DATA & UTILS
    # -------------------------------------------------------------------------

    def get_balance(self):
        try: return self.pm.get_usdc_balance()
        except: return 0.0

    def get_current_price(self, token_id):
        """Get current price - prefer cached websocket data, fallback to REST."""
        # Check if we have recent websocket data
        if hasattr(self, 'price_cache') and token_id in self.price_cache:
            cache_time, cached_data = self.price_cache[token_id]
            if time.time() - cache_time < 1.0:  # Use cache if < 1 second old
                return cached_data

        # Fallback to REST API
        try:
            book = self.pm.client.get_order_book(token_id)
            
            # SAFE CASTING with Validation
            best_bid = float(book.bids[0].price) if book.bids else 0.0
            bid_size = float(book.bids[0].size) if book.bids else 0.0
            best_ask = float(book.asks[0].price) if book.asks else 1.0
            
            # SANITY CHECK: Probability markets must be 0-1
            # If we see > 1.0, it's garbage or we are mapped to the wrong thing
            if best_bid > 1.0 or best_ask > 1.05: 
                 print(f"   ⚠️ PRICE SANITY FAIL: Bid={best_bid}, Ask={best_ask} (Token: {token_id})")
                 return 0.5, 0.0, 0.0, 1.0

            if best_bid == 0 and best_ask == 1: return 0.5, 0.0, 0.0, 1.0

            # 4. EXPENSIVE ENTRY GUARD (New)
            # If price is > $0.80, we need really good reasons to buy
            # (Logic applied in trading loop, but good to inspect here)

            price_data = ((best_bid + best_ask)/2, best_bid, bid_size, best_ask)
            # Cache the REST data
            if not hasattr(self, 'price_cache'):
                self.price_cache = {}
            self.price_cache[token_id] = (time.time(), price_data)
            return price_data
        except Exception as e: 
            # print(f"Price Fetch Error: {e}") # Reduce noise
            return 0.5, 0.0, 0.0, 1.0

    def calculate_momentum(self, symbol):
        """Calculate momentum as % change over last 30 seconds."""
        history = self.binance_history.get(symbol, [])
        if len(history) < 2: return 0.0

        # Get prices from last 30 seconds
        now = time.time()
        recent_prices = [(t, p) for t, p in history if now - t < 30]

        if len(recent_prices) < 2: return 0.0

        # Calculate momentum as (current - oldest) / oldest
        oldest_price = recent_prices[0][1]
        current_price = recent_prices[-1][1]

        momentum = (current_price - oldest_price) / oldest_price
        return momentum

    def get_market_sentiment(self, asset, binance_symbol):
        """Calculate comprehensive market sentiment score (0-1 scale, 0.5=neutral)."""
        try:
            history = self.binance_history.get(binance_symbol, [])
            if len(history) < 20:  # Need enough data
                return 0.5

            # Get recent prices (last 10 minutes)
            now = time.time()
            recent_prices = [(t, p) for t, p in history if now - t < 600]
            if len(recent_prices) < 10:
                return 0.5

            prices = [p for t, p in recent_prices]

            # 1. TREND ANALYSIS (30% weight)
            # Simple moving averages
            if len(prices) >= 5:
                ma_short = sum(prices[-5:]) / 5
                ma_long = sum(prices[-10:]) / 10
                trend_score = 0.5 + (ma_short - ma_long) / ma_long * 2  # Scale to 0-1
                trend_score = max(0, min(1, trend_score))  # Clamp
            else:
                trend_score = 0.5

            # 2. MOMENTUM STRENGTH (25% weight)
            momentum_pct = (prices[-1] - prices[0]) / prices[0]
            momentum_score = 0.5 + momentum_pct * 10  # Scale momentum to 0-1
            momentum_score = max(0, min(1, momentum_score))

            # 3. VOLATILITY FILTER (20% weight)
            # Lower volatility = cleaner signals = higher confidence
            returns = [(prices[i] - prices[i-1])/prices[i-1] for i in range(1, len(prices))]
            volatility = sum(abs(r) for r in returns) / len(returns) if returns else 0
            volatility_score = max(0, 1 - volatility * 20)  # Lower volatility = higher score

            # 4. RECENT STRENGTH (15% weight)
            # Compare last 3 prices vs first 3
            if len(prices) >= 6:
                recent_avg = sum(prices[-3:]) / 3
                older_avg = sum(prices[:3]) / 3
                strength_score = 0.5 + (recent_avg - older_avg) / older_avg * 2
                strength_score = max(0, min(1, strength_score))
            else:
                strength_score = 0.5

            # 5. ASSET-SPECIFIC BIAS (10% weight) - based on market conditions
            asset_bias = {
                "bitcoin": 0.55,   # BTC slightly bullish bias (digital gold)
                "ethereum": 0.45,  # ETH slightly bearish (competition from layer2)
                "solana": 0.60,    # SOL bullish (fast growth)
                "xrp": 0.40        # XRP bearish (regulation concerns)
            }.get(asset, 0.5)

            # Combine scores with weights
            final_score = (
                trend_score * 0.30 +
                momentum_score * 0.25 +
                volatility_score * 0.20 +
                strength_score * 0.15 +
                asset_bias * 0.10
            )

            print(f"   📊 {asset.upper()} Sentiment: Trend={trend_score:.2f}, Momentum={momentum_score:.2f}, Volatility={volatility_score:.2f}, Strength={strength_score:.2f}, Bias={asset_bias:.2f} → {final_score:.3f}")
            return final_score

        except Exception as e:
            print(f"   ❌ Sentiment calc error for {asset}: {e}")
            return 0.5  # Neutral fallback

    def calculate_volatility(self, symbol):
        """Calculate recent volatility (Standard Deviation) from Binance deque."""
        history = self.binance_history.get(symbol, [])
        if len(history) < 10: return 0.0

        # Filter for last 10 seconds (tuples are time, price)
        now = time.time()
        recent_prices = [p for t, p in history if now - t < 10]

        if len(recent_prices) < 5: return 0.0

        # Calculate pct returns
        returns = [(recent_prices[i] - recent_prices[i-1])/recent_prices[i-1] for i in range(1, len(recent_prices))]
        if not returns: return 0.0

        avg = sum(returns) / len(returns)
        var = sum((r - avg)**2 for r in returns) / len(returns)
        return (var ** 0.5) * 100 # Return as percentage (e.g. 0.05)

    def get_dynamic_timeout(self, asset):
        """Volatile = 3s timeout. Calm = 15s timeout."""
        symbol = BINANCE_SYMBOLS.get(asset)
        if not symbol: return LIMIT_ORDER_TIMEOUT_CALM

        vol = self.calculate_volatility(symbol)
        return LIMIT_ORDER_TIMEOUT_VOLATILE if vol > 0.05 else LIMIT_ORDER_TIMEOUT_CALM

    # -------------------------------------------------------------------------
    # MARKET SCANNING (The Missing Piece)
    # -------------------------------------------------------------------------

    def detect_market_creation_patterns(self):
        """Analyze when Polymarket creates markets and optimize scan timing."""
        if len(self.market_creation_times) < 5: return

        # Get minutes past hour for creation times
        minutes = []
        for t in self.market_creation_times[-20:]:  # Last 20 markets
            try:
                # Handle different timestamp formats safely
                if t.endswith('Z'):
                    dt = datetime.datetime.fromisoformat(t.replace('Z', '+00:00'))
                elif '+' in t or t.endswith(('UTC', 'GMT')):
                    # Already has timezone info
                    dt = datetime.datetime.fromisoformat(t.replace('UTC', '+00:00').replace('GMT', '+00:00'))
                else:
                    # Assume UTC if no timezone
                    dt = datetime.datetime.fromisoformat(t + '+00:00')
                minutes.append(dt.minute)
            except (ValueError, AttributeError):
                # Skip invalid timestamps
                continue

        # Find most common creation minutes (clustering around :00, :15, :30, :45)
        from collections import Counter
        minute_counts = Counter(minutes)

        # Get top 2 most common creation minutes
        top_minutes = [m for m, _ in minute_counts.most_common(2)]

        # Adjust scan timing to be 30s before these minutes
        current_minute = datetime.datetime.now().minute
        next_scan_minutes = []

        for target_minute in top_minutes:
            if current_minute < target_minute:
                next_scan_minutes.append(target_minute - current_minute)
            else:
                next_scan_minutes.append(60 - current_minute + target_minute)

        if next_scan_minutes:
            optimal_delay = min(next_scan_minutes) * 60 - 30  # 30s early
            self.market_scan_interval = max(10, min(60, optimal_delay))  # Between 10-60s

    def get_available_markets(self):
        """
        Discovers 15-minute crypto markets using the WORKING approach:
        1. Generate event slugs for current time windows
        2. Query events API with specific slugs
        3. Extract markets from found events
        """
        # Use CENTRALIZED discovery method from GammaMarketClient
        return self.gamma.discover_15min_crypto_markets()

    def get_fee_bps(self, token_id):
        try:
            url = "https://clob.polymarket.com/fee-rate"
            resp = requests.get(url, params={"token_id": token_id}, timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                return int(data.get("base_fee", 0))  # API returns "base_fee", not "fee_rate_bps"
            return 0
        except:
            return 0




    # -------------------------------------------------------------------------
    # ORDER RECONCILIATION (The Missing "check_fills")
    # -------------------------------------------------------------------------

    def sync_positions(self):
        """
        Poll Data API to reconcile Pending Orders -> Active Positions.
        This is the 'source of truth' check.
        """
        print(f"   🔄 SYNC_POSITIONS: Checking positions for user={self.pm.funder_address}")
        if self.dry_run: return

        try:
            # 1. Fetch actual held positions
            # For Gnosis Safe proxy, use the proxy address instead of EOA
            user = self.pm.funder_address if self.pm.funder_address else self.pm.get_address_for_private_key()
            url = f"https://data-api.polymarket.com/positions?user={user}"
            print(f"   📊 FETCHING POSITIONS: {url}")
            positions = requests.get(url, timeout=5).json()
            print(f"   📊 FOUND {len(positions)} total positions")

            held_token_ids = {p["asset"]: p for p in positions if float(p["size"]) > 0.1}
            print(f"   📊 HELD TOKENS: {len(held_token_ids)} with size > 0.1")

            # 2. Reconcile Entry Orders
            for order_id, meta in list(self.pending_orders.items()):
                if meta["type"] != "entry": continue

                token_id = meta["token_id"]

                # If we hold this token now, the order filled
                if token_id in held_token_ids:
                    print(f"   ✅ ORDER FILLED: {meta['side']} {meta['asset']}")
                    self.total_fills += 1

                    # Promote to Active Managed Position
                    self.active_positions[token_id] = {
                        "token_id": token_id,
                        "asset": meta["asset"],
                        "side": meta["side"],
                        "entry_price": meta["price"],
                        "size": float(held_token_ids[token_id]["size"]),
                        "entry_time": time.time(),
                        "market_id": meta["market_id"]
                    }

                    # Clear pending
                    del self.pending_orders[order_id]

        except Exception as e:
            print(f"   ⚠️ Sync Error: {e}")

    # -------------------------------------------------------------------------
    # MAKER ENTRY (Queue Jumper)
    # -------------------------------------------------------------------------

    def check_correlation_risk(self, new_asset, new_direction):
        """Prevent over-correlation by checking if too many positions are in the same direction."""
        if len(self.active_positions) < 2: return True  # Need at least 2 to check correlation

        # Count same-direction positions
        same_direction = sum(1 for p in self.active_positions.values()
                           if p["side"] == new_direction)

        # If 3+ positions same direction, block new entry
        if same_direction >= 3:
            print(f"   🚫 CORRELATION BLOCK: {same_direction} positions {new_direction}, skipping {new_asset}")
            return False

        # Also check if we're over-concentrated in one asset
        asset_positions = sum(1 for p in self.active_positions.values()
                            if p["asset"] == new_asset)

        if asset_positions >= 2:  # Max 2 positions per asset
            print(f"   🚫 ASSET LIMIT: Already {asset_positions} {new_asset} positions")
            return False

        return True

    def get_optimal_bet_size(self, asset):
        """Scale bet size. PHOENIX MODE: If balance < $5, go all in (90%)."""
        balance = self.get_balance()
        
        # PHOENIX RECOVERY MODE
        if balance < 50.0:
            print(f"   🔥 PHOENIX MODE ACTIVE (Balance ${balance:.2f} < $50)")
            # Leave $0.10 for gas/fees if needed, otherwise use 90%
            safe_max = max(1.0, balance * 0.90)
            return min(MAX_BET_USD, float(safe_max))

        base_size = balance * BET_PERCENT

        # Scale down for volatile assets
        volatility_multiplier = {
            "bitcoin": 1.0,   # Baseline
            "ethereum": 0.9,  # Slightly less
            "solana": 0.8,    # More volatile
            "xrp": 0.7        # Most volatile
        }

        # Scale up as we get more experience (but stay conservative)
        experience_multiplier = min(1.5, 1.0 + (self.total_fills * 0.01))

        size = base_size * volatility_multiplier.get(asset, 0.8) * experience_multiplier
        return min(MAX_BET_USD, max(MIN_BET_USD, size))

    def open_position_maker(self, market, direction, momentum=0.0, sentiment_score=0.5):
        market_id = market["id"]

        # Select target token based on momentum direction
        token_id = market["up_token"] if direction == "UP" else market["down_token"]
        opposing_token = market["down_token"] if direction == "UP" else market["up_token"]

        # 1. RAPID FIRE PREVENTION: Allow 2 attempts per 15-minute window
        attempts = self.traded_markets.count(market_id)
        if attempts >= 2:
            print(f"   🚫 MAX ATTEMPTS: {market['asset']} exhausted for this window")
            return False

        # 2. LOCKOUT CHECK: Don't buy if we already hold either side of this asset
        # This prevents "doubling down" before redemption (20% rule)
        if token_id in self.active_positions or opposing_token in self.active_positions:
            print(f"   🔒 LOCKOUT: Already holding position in {market['asset']}")
            return False

        # 2. Price Analysis: Get the best bid to front-run the queue
        try:
            price_result = self.get_current_price(token_id)
            print(f"   🔍 PRICE RESULT: {price_result}")
            _, best_bid, _, best_ask = price_result
            
            # --- PHOENIX MODE: HARD PRICE CAP ---
            # STRICT RULE: If balance < $50, we ONLY buy "lottery tickets" (1c-5c).
            # We rejected the old "affordability" logic which allowed expensive buys on deposit.
            if self.get_balance() < 50.0:
                 if best_bid > 0.05:
                      print(f"   🔥 PHOENIX REJECT: Bid ${best_bid} > $0.05. Cheap shares only.")
                      return False
            # ----------------------------------------
            
            # EMPTY MARKET LOGIC: If Bid is floor (0.0) or near zero, use Sentiment
            if best_bid <= 0.05 and best_ask >= 0.95:
                 print(f"   👻 EMPTY MARKET DETECTED (Spread: {best_bid}-{best_ask})")
                 # Seed liquidity based on sentiment (conservative)
                 # FIXED: Allow 1c-5c seeds. Old $0.10 floor caused deadlock with Hard Cap.
                 # e.g. Sentiment 0.60 -> Bid 0.04. Sentiment 0.40 -> Bid 0.02.
                 target_price = max(0.01, min(0.05, sentiment_score * 0.10))
                 entry_price = round(target_price, 2)
                 print(f"   💡 SEEDING QUOTE @ {entry_price} (Sentiment {sentiment_score:.2f} -> 1c-5c Range)")
            else:
                 # Standard Queue Jump
                 print(f"   🔍 BEST BID: {best_bid}")
                 
                 # MAKER PRICING LOGIC
                 # Try to beat the bid, but NEVER cross the ask (or we get rejected as Taker)
                 potential_price = round(float(best_bid) + 0.01, 2) 
                 is_taker = False # Default to Maker

                 # PHOENIX SNIPER: If Ask is super cheap (<= 0.05), just TAKE it.
                 # We want those 1 cent shares.
                 if self.get_balance() < 50.0 and best_ask <= 0.05:
                      entry_price = round(float(best_ask), 2)
                      is_taker = True
                      print(f"   🦅 PHOENIX SNIPE: Taking cheap shares at ${entry_price}!")
                 
                 elif potential_price < best_ask:
                      entry_price = potential_price
                      print(f"   💡 INCREMENT: Bumping bid to ${entry_price} (Queue Front)")
                 else:
                      entry_price = round(float(best_bid), 2)
                      print(f"   💡 JOINING: Spread too tight, joining bid at ${entry_price}")

            print(f"   🔍 ENTRY PRICE: {entry_price}")
            
            if entry_price <= 0.0:
                print("   ⚠️ Invalid Entry Price 0.0. Skipping.")
                return False
                
        except Exception as e:
            print(f"   ❌ PRICE ERROR: {e}")
            return False

        # LIFECYCLE TEST: Stricter bounds to avoid "Bait"
        # Min $0.02 (was $0.001) to avoid worthless options
        # Max $0.92 (was $0.95) to ensure some upside room
        if entry_price > 0.92 or entry_price < 0.02:
            print(f"   ❌ PRICE FILTER: ${entry_price:.3f} outside 2¢-92¢ range")
            return False

        # --- PHOENIX HARD CAP (FINAL CHECK) ---
        # Catch-all: Ensure that even if we "Seed" an empty market, we don't pay > 5c
        if self.get_balance() < 50.0 and entry_price > 0.05:
            print(f"   🔥 PHOENIX REJECT (FINAL): Entry ${entry_price:.2f} > $0.05 Hard Cap")
            return False
        # --------------------------------------

        # PRICE CAP: Don't buy if entry price > $0.75 (risk > reward)
        # UNLESS sentiment is super high
        if entry_price > PRICE_CAP: 
             # Check if sentiment justifies the high price
             if sentiment_score < 0.75:
                 print(f"   ⚠️ PRICE TOO HIGH: ${entry_price:.3f} > ${PRICE_CAP:.2f} and Sentiment {sentiment_score:.2f} < 0.75")
                 return False
             else:
                 print(f"   ⚠️ PRICE HIGH but SENTIMENT STRONG: ${entry_price:.3f} (Allowed)")

        # 0. CONFIG CHECK
        current_config = load_config("scalper")
        if not current_config.get("active", True):
            print(f"   ⏸️ SKIPPING: Scalper paused via Config")
            return False

        # 3. Size Calculation (Config-aware)
        balance = self.get_balance()
        if balance < 0.99:
            print(f"   ❌ INSUFFICIENT BALANCE: ${balance:.2f} (need $1.00+)")
            return False

        max_size_cfg = current_config.get("max_size", MAX_BET_USD)
        # 20% rule but capped by config
        size_usd = min(max_size_cfg, balance * BET_PERCENT) 
        
        # 3.5 LLM CHECK (Optional)
        if self.use_llm:
             # Quick context check
             mkt_data = {"ticker": market['asset'], "direction": direction}
             advice = self.analyst.ask_strategy("scalper_sentiment", mkt_data)
             if advice["decision"] != "APPROVED":
                 print(f"   🧠 ANALYST VETO: {advice['reason']}")
                 return False

        size_shares = size_usd / entry_price

        # 4. Fetch the 1000 bps (1%) mandatory fee
        fee_rate_bps = self.get_fee_bps(token_id) or 1000

        print(f"   🎯 EXECUTING: {market['asset'].upper()} {direction} @ ${entry_price:.3f} (Size: ${size_usd:.2f}) | Fee: {fee_rate_bps}bps")

        if self.dry_run:
            self.active_positions[token_id] = {
                "token_id": token_id, "asset": market["asset"], "side": direction,
                "entry_price": entry_price, "size": size_shares, "entry_time": time.time(),
                "market_id": market["id"]
            }
            # Lock this market to prevent rapid-fire
            self.traded_markets.append(market_id)
            print("   ✅ [DRY] Position Opened (20% Allocation)")
            return True

        try:
            # Send the order to the sanitized Polymarket class
            # EXPLICITLY set post_only=True to ensure we never pay taker fees
            resp = self.pm.place_limit_order(token_id, entry_price, size_shares, "BUY", fee_rate_bps=fee_rate_bps, post_only=True)
            if resp.get("orderID"):
                # Record trade using TradeRecorder
                record_trade(
                    agent_name=self.AGENT_NAME,
                    market=market["asset"],
                    side=direction,
                    amount=size_usd,
                    price=entry_price,
                    token_id=token_id,
                    reasoning=f"Momentum: {momentum:.2%}, Sentiment: {sentiment_score:.2f}"
                )

                # Update agent activity
                update_agent_activity(
                    agent_name=self.AGENT_NAME,
                    activity="trade_executed",
                    extra_data={
                        "market": market["asset"],
                        "side": direction,
                        "size": size_usd,
                        "price": entry_price
                    }
                )

                self.pending_orders[resp.get("orderID")] = {
                    "type": "entry", "token_id": token_id, "asset": market["asset"],
                    "side": direction, "price": entry_price, "time": time.time(),
                    "timeout": 5,  # Note: logic uses global constant overrides now
                    "market_id": market["id"]
                }
                # Lock this market to prevent rapid-fire
                self.traded_markets.append(market_id)
                print("   ✅ [LIVE] Order Placed (20% Allocation)")
                return True
            else:
                print(f"   ❌ ORDER FAILED: {resp}")
                return False
        except Exception as e:
            print(f"   ❌ Order Failed: {e}")
            return False

    # -------------------------------------------------------------------------
    # HYBRID EXIT (Maker First -> Panic Taker)
    # -------------------------------------------------------------------------

    def manage_positions(self):
        """Check exits for all active positions (Smart Maker-Only)."""
        for token_id, pos in list(self.active_positions.items()):
            # 1. Get real-time prices (Prefer WS cache)
            _, best_bid, _, best_ask = self.get_current_price(token_id)
            if best_bid == 0:
                # 👻 GHOST TRAP: If Ask indicates a profit ("Liquidity Mirage"), use it to place a Maker Sell.
                # This ensures we don't freeze when the price spikes but there are no buyers yet.
                if best_ask > 0 and best_ask > pos["entry_price"] * 1.10:
                     print(f"   👻 GHOST TRAP ACTIVATED: Bid 0, but Ask ${best_ask}. placing Maker Sell.")
                     best_bid = best_ask # Virtual Bid to trigger profit logic below
                else:
                     continue

            # 2. Calculate PnL relative to current Bid
            pnl_pct = (best_bid - pos["entry_price"]) / pos["entry_price"]

            # 3. Check if we already have a pending exit order for this position
            existing_exit = next((oid for oid, meta in self.pending_orders.items() 
                                 if meta["type"] == "exit" and meta["token_id"] == token_id), None)

            # --- PREDATORY MOMENTUM TRAP (Shark Mode) ---
            # If we see high velocity (the same signal that baited us before),
            # we use it to SELL into the chasers.
            price_momentum = self.calculate_momentum(BINANCE_SYMBOLS.get(pos["asset"]))
            if price_momentum > 0.0005: # > 0.05% in 30s is a spike
                 print(f"   🎣 PREDATORY TRAP: High Momentum ({price_momentum:.4f}%) detected on {pos['asset']}!")
                 
                 # Sell at the Ask (or slightly higher if spread is wide)
                 # We want to be the "Whale" selling to the chasers
                 predatory_price = round(best_ask, 2)
                 
                 if existing_exit:
                     curr_price = self.pending_orders[existing_exit].get("price")
                     if curr_price < predatory_price:
                         print(f"   ⤴️ RAISING OFFER: Moving sell from ${curr_price} to ${predatory_price} to catch spike")
                         if not self.dry_run:
                            try: self.pm.client.cancel(existing_exit)
                            except: pass
                         del self.pending_orders[existing_exit]
                         existing_exit = None # Force new order placement below
                 
                 # Force pnl_pct to trigger the exit block below effectively
                 pnl_pct = 999.0 # Virtual profit trigger
                 print(f"   🚀 TRIGGERING PREDATORY EXIT @ ${predatory_price}")

            # 4. Trigger "Smart Maker" Exit if Target Hit OR Stop Loss Hit
            # 4. Trigger Exit if Target Hit OR Stop Loss Hit
            if pnl_pct > TAKE_PROFIT_PCT:
                # --- PROFIT MODE: Smart Maker (Chase Ask) ---
                if existing_exit:
                    current_order_price = self.pending_orders[existing_exit].get("price")
                    target_price = round(best_ask - MAKER_OFFSET, 2)
                    if current_order_price != target_price:
                        print(f"   🔄 CHASING FILL: Moving {pos['asset']} exit to front of queue (${target_price})...")
                        if not self.dry_run:
                            try: self.pm.client.cancel(existing_exit)
                            except: pass
                        del self.pending_orders[existing_exit]
                    else:
                        continue 

                sell_price = round(best_ask - MAKER_OFFSET, 2)
                print(f"   💰 PROFIT: Placing Aggressive Maker Sell @ ${sell_price}")

                if not self.dry_run:
                    try:
                        resp = self.pm.place_limit_order(token_id, sell_price, pos["size"], "SELL")
                        if resp.get("orderID"):
                            self.pending_orders[resp["orderID"]] = {
                                "type": "exit", "time": time.time(), "token_id": token_id, "price": sell_price,
                                "timeout": EXIT_MAKER_TIMEOUT
                            }
                    except Exception as e:
                        print(f"   ❌ Maker Exit Failed: {e}")

            elif pnl_pct < PANIC_THRESHOLD_PCT:
                # --- PANIC MODE: Taker Dump (Hit Bid) ---
                print(f"   🚨 PANIC DUMP: PnL {pnl_pct*100:.2f}% < {PANIC_THRESHOLD_PCT*100}%! FORCE SELLING!")
                
                # Cancel any existing maker orders to free up balance
                if existing_exit:
                    if not self.dry_run:
                        try: self.pm.client.cancel(existing_exit)
                        except: pass
                    del self.pending_orders[existing_exit]

                if not self.dry_run:
                    try:
                        # Place LIMIT SELL @ 0.00 to cross the entire spread and fill instantly (Taker)
                        # This behaves like a Market Sell
                        resp = self.pm.place_limit_order(token_id, 0.00, pos["size"], "SELL")
                        if resp.get("orderID"):
                            print(f"   ✅ DUMPED {pos['asset']} @ MARKET PRICE")
                            del self.active_positions[token_id] # Assume instant fill
                    except Exception as e:
                        print(f"   ❌ Panic Dump Failed: {e}")

    # -------------------------------------------------------------------------
    # UTILS
    # -------------------------------------------------------------------------

    def prune_price_cache(self):
        """Remove old price data to prevent memory leaks."""
        if not hasattr(self, 'price_cache'): return
        
        now = time.time()
        # Remove entries older than 60 seconds
        stale_keys = [k for k, v in self.price_cache.items() if now - v[0] > 60]
        for k in stale_keys:
            del self.price_cache[k]
        
        if len(stale_keys) > 0:
            # Only log occasionally to avoid noise
            if len(stale_keys) > 100:
                print(f"   🧹 Pruned {len(stale_keys)} stale cache entries")

    def reap_stale_orders(self):
        """Cancel orders older than their dynamic timeout."""
        self.prune_price_cache()

        now = time.time()
        for oid, meta in list(self.pending_orders.items()):
            age = now - meta["time"]
            limit = meta["timeout"]

            if age > limit:
                print(f"   💀 REAPING: Order {oid[:8]} (Age {age:.1f}s)")
                if not self.dry_run:
                    try: self.pm.client.cancel(oid)
                    except: pass
                
                # REFUND ATTEMPT if no partial fill occurred
                # (We only want to burn an attempt if we actually TRADED)
                # Note: This requires knowing if we got a partial fill. 
                # For now, we assume if it's still in pending, it's 0 fill (since we move to active completely on any sync)
                # But to be safe, we check if we hold the token in sync_positions next.
                
                # Remove from traded_markets to allow retry immediately
                market_id = meta.get("market_id")
                if market_id and market_id in self.traded_markets:
                    self.traded_markets.remove(market_id)
                    print(f"   ♻️  REFUNDED ATTEMPT for {meta.get('asset', '?')} (Timeout with no fill)")

                del self.pending_orders[oid]

                # If exit failed, we might need to panic next loop.
                # (Position remains in active_positions so it will be picked up by manage_positions again)

    def check_circuit_breaker(self):
        """Calculate Equity = Balance + Unrealized PnL."""
        unrealized_pnl = 0.0
        
        # Calculate unrealized PnL from active positions
        for token_id, pos in self.active_positions.items():
            current_price_data = self.get_current_price(token_id)
            # conservative: use best BID to exit
            current_bid = current_price_data[1] 
            
            # Pne = (Current - Entry) * Size
            position_val = (current_bid - pos["entry_price"]) * pos["size"]
            unrealized_pnl += position_val

        total_equity_change = self.total_pnl + unrealized_pnl
        drawdown_limit = self.initial_balance * -MAX_DAILY_DRAWDOWN_PCT
        
        if total_equity_change < drawdown_limit:
            print(f"   🛑 CIRCUIT BREAKER TRIGGERED!")
            print(f"   Realized PnL: ${self.total_pnl:.2f}")
            print(f"   Unrealized PnL: ${unrealized_pnl:.2f}")
            print(f"   Total Delta: ${total_equity_change:.2f} (Limit: ${drawdown_limit:.2f})")
            self.circuit_breaker_triggered = True
            return True
            
        return False

    def on_binance_message(self, ws, message):
        try:
            data = json.loads(message)
            # Handle single stream format (symbol@ticker) - this is what we receive
            if "s" in data and "c" in data:
                s = data["s"].lower()
                p = float(data["c"])
                if s in self.binance_history:
                    self.binance_history[s].append((time.time(), p))
            # Handle combined stream format (legacy fallback)
            elif "data" in data and "s" in data["data"] and "c" in data["data"]:
                s = data["data"]["s"].lower()
                p = float(data["data"]["c"])
                if s in self.binance_history:
                    self.binance_history[s].append((time.time(), p))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            # Silently ignore malformed messages
            pass

    def run_binance_ws(self):
        """Binance WebSocket with individual stream connections."""
        import threading

        while True:
            try:
                # Use individual streams - more reliable than combined
                for symbol in BINANCE_SYMBOLS:
                    stream = f"{symbol}@ticker"
                    url = f"{BINANCE_WS_URL}/ws/{stream}"

                    def create_connection(url, stream):
                        ws = websocket.WebSocketApp(
                            url,
                            on_message=self.on_binance_message,
                            on_error=lambda ws, error: print(f"   🔌 {stream} Error: {error}"),
                            on_close=lambda ws: print(f"   🔌 {stream} Closed"),
                            on_open=lambda ws: print(f"   🔌 {stream} Connected")
                        )
                        ws.run_forever(ping_interval=30, ping_timeout=10)

                    # Start each connection in its own thread
                    threading.Thread(
                        target=create_connection,
                        args=(url, stream),
                        daemon=True
                    ).start()

                # Keep main thread alive
                while True:
                    time.sleep(60)

            except Exception as e:
                print(f"   🔌 WS Setup Failed: {e}")
                time.sleep(5)

    # -------------------------------------------------------------------------
    # COMMAND HANDLING (New)
    # -------------------------------------------------------------------------

    def process_commands(self):
        """Check for and execute user commands from the context."""
        if not self.context: return

        try:
            commands = self.context.get_user_commands("scalper")
            for cmd in commands:
                text = cmd.get("command", "").lower()
                print(f"   📣 COMMAND RECEIVED: {text}")
                
                # 1. SCAN NOW
                if "scan" in text:
                    print("   🚀 EXECUTING: Force Scan")
                    self.last_market_scan = 0 # Force scan next loop
                    self._log("COMMAND", "User Command", "Forcing market scan", 1.0, "EXECUTED")
                
                # 2. PAUSE/RESUME
                elif "pause" in text or "stop" in text:
                    # Update local override (if we had one, but strict state comes from bot_state)
                    # For now just log, real pause needs to update state file via API which user tool does
                    print("   ⏸️ PAUSE: Pausing agent execution (via API)")
                    
                # 3. CONFIG UPDATES (Simple overrides for this session)
                elif "bet" in text and "max" in text:
                     # e.g. "max bet 10"
                     try:
                        val = float(text.split("bet")[-1].strip())
                        self.max_bet = val
                        print(f"   ⚖️  Updated MAX_BET to ${val}")
                        self._log("CONFIG", "User Update", f"Max bet set to {val}", 0, "UPDATED")
                     except: pass

        except Exception as e:
            print(f"   ⚠️ Command Error: {e}")

        # -----------------------------------------------------------
        # NEW: Poll API for Manual Overrides (Integrates with FBP Agent)
        # -----------------------------------------------------------
        try:
             # Fast poll to local API (only if running)
             import requests
             resp = requests.get("http://127.0.0.1:8000/api/manual/queue?agent_name=scalper", timeout=1)
             if resp.status_code == 200:
                 data = resp.json()
                 cmd = data.get("command")
                 if cmd:
                     print(f"   🚨 MANUAL OVERRIDE RECEIVED: {cmd['action']}")
                     self.handle_manual_override(cmd)
        except Exception as e:
            pass # API might be down or busy

    def handle_manual_override(self, cmd):
        """Execute a manual override command from the API."""
        action = cmd.get("action")
        market_id = cmd.get("market_id")
        amount = float(cmd.get("amount", self.max_bet))
        
        if action == "HALT":
            print("   🛑 EMERGENCY HALT TRIGGERED")
            self.running = False
            
        elif action in ["FORCE_BUY_YES", "FORCE_BUY_NO"]:
            # Logic to execute a generic trade on a specific market ID
            # This requires 'market_id' to be a token_id or condition_id
            side = "BUY" # logic handling needed for YES/NO maps if standardizing
            # For simplicity, assume market_id IS the token_id we want to buy
            print(f"   🔫 FORCING TRADE: {action} on {market_id} for ${amount}")
            try:
                # Bypass normal checks
                self.pm.place_limit_order(token_id=market_id, price=0.99, size=amount, side="BUY") 
                # Note: 0.99 price for 'market buy' effect (taker)
                self._log("MANUAL", "Override", f"Forced buy on {market_id}", amount, "EXECUTED")
            except Exception as e:
                print(f"   ❌ Manual trade failed: {e}")


    def run(self):
        # 0. CLEAN SLATE: Cancel all existing orders to free up balance
        # This fixes the "Insufficient Funds" issue by removing stale/orphan orders
        self.pm.cancel_all_orders()

        # 1. Start Feed
        threading.Thread(target=self.run_binance_ws, daemon=True).start()
        print("   ⏳ Connecting to Binance...")
        time.sleep(3)

        while True:
            try:
                if self.circuit_breaker_triggered:
                    time.sleep(60)
                    continue

                # 2. Housekeeping
                self.process_commands() # <--- NEW: Check commands
                self.reap_stale_orders()
                self.sync_positions() # The "Check Fills" Logic
                if self.check_circuit_breaker(): continue
                
                # Reload Config Dynamic
                # (Optional: Check bot_state.json for updates)
                
                # if self.redeemer:
                #     try:
                #         print("   🔄 RUNNING AUTO-REDEEMER...")
                #         result = self.redeemer.scan_and_redeem()
                #         if result and result.get('redeemed', 0) > 0:
                #             print(f"   💰 REDEEMED: {result['redeemed']} positions")
                #     except Exception as e:
                #         print(f"   ❌ REDEEMER ERROR: {e}")
                else:
                    print("   ⚠️ NO REDEEMER INITIALIZED")

                # 3. Manage Exits
                self.manage_positions()

                # 4. Scan & Enter (Optimized)
                # Clear traded markets every 15 minutes to allow re-entry in new windows
                if int(time.time()) % 900 == 0:  # Every 15 minutes
                    self.traded_markets.clear()
                    print("   🔄 CLEARED: Market lockouts reset for new 15m windows")

                print(f"   🔄 SCAN: active_positions={len(self.active_positions)}, MAX_POSITIONS={MAX_POSITIONS}")
                if len(self.active_positions) < MAX_POSITIONS:
                    markets = self.get_available_markets()
                    print(f"   📊 MARKETS FOUND: {len(markets) if markets else 0}")

                    if markets:  # Only process if we found markets
                        # Record a reference token for the dashboard status check
                        try:
                            update_agent_activity(self.AGENT_NAME, "Scanning", {"last_token_id": markets[0]["up_token"]})
                        except: pass
                        
                        print(f"   🔍 PROCESSING {len(markets)} markets...")
                        for m in markets:
                            try:
                                asset = m['asset']

                                # "Best Option" Entry Logic - Choose direction with REAL market sentiment
                                binance_symbol = [k for k, v in BINANCE_SYMBOLS.items() if v == asset][0]
                                momentum = self.calculate_momentum(binance_symbol)

                                # Get broader market sentiment indicators
                                sentiment_score = self.get_market_sentiment(asset, binance_symbol)

                                # Only trade if momentum exceeds threshold AND sentiment is clear
                                # Parse from config dynamic or fallback to hardcoded
                                current_config = load_config("scalper")
                                mom_threshold = current_config.get("BASE_MOMENTUM_THRESHOLD", BASE_MOMENTUM_THRESHOLD)
                                conf_threshold = current_config.get("MIN_SENTIMENT_CONFIDENCE", MIN_SENTIMENT_CONFIDENCE)

                                if abs(momentum) < mom_threshold:
                                    # Update UI with "Watching" status and momentum
                                    try:
                                        status_msg = f"STALKING | {asset.upper()} MOM {momentum:.4f}"
                                        update_agent_activity(self.AGENT_NAME, status_msg, {
                                            "last_token_id": markets[0]["up_token"],
                                            "momentum": momentum
                                        })
                                    except: pass
                                    
                                    print(f"   💤 NO MOMENTUM: {asset.upper()} {momentum:.4f}% (threshold: {mom_threshold:.4f})")
                                    self._log("SCAN", f"{asset} Momentum", f"Momentum {momentum:.4f}% < {mom_threshold:.4f}", confidence=0.0, conclusion="WAIT")
                                    continue

                                # --- SAFE ENTRY LOGIC (PHOENIX OVERRIDE) ---
                                
                                signals_agree = (momentum > 0) == (sentiment_score > 0.5)
                                confidence_met = abs(sentiment_score - 0.5) * 2 >= conf_threshold

                                # Phoenix Mode: Trust Sentiment over Momentum if aggressive
                                if BET_PERCENT > 0.5 and abs(sentiment_score - 0.5) > 0.1:
                                     print(f"   🔥 PHOENIX OVERRIDE: Trusting Sentiment {sentiment_score:.2f} despite Momentum {momentum:.4f}%")
                                     signals_agree = True
                                     confidence_met = True

                                # STRICTER LOGIC: MUST HAVE AGREEMENT and CONFIDENCE
                                if signals_agree and confidence_met:
                                    # In Phoenix Mode, follow Sentiment. Otherwise follow Momentum (they match).
                                    if BET_PERCENT > 0.5: 
                                        direction = "UP" if sentiment_score > 0.5 else "DOWN"
                                    else:
                                        direction = "UP" if momentum > 0 else "DOWN"
                                    print(f"   🎯 SIGNAL SYNC: {asset.upper()} {direction} (Mom={momentum:.4f}%, Sent={sentiment_score:.2f})")
                                    self.open_position_maker(m, direction, momentum, sentiment_score)
                                else:
                                    # Detailed rejection log
                                    if not signals_agree:
                                        reason = "Signals Disagree"
                                    else:
                                        reason = "Low Confidence"
                                    print(f"   💤 SKIPPING {asset.upper()}: {reason} (Mom={momentum:.4f}%, Sent={sentiment_score:.2f})")
                            except Exception as e:
                                # Log but don't crash the main loop
                                print(f"   ⚠️ Market processing error for {m.get('asset', 'unknown')}: {e}")
                                continue

                # 5. Enhanced Reporting
                fill_rate = (self.total_fills / max(1, self.total_orders)) * 100
                win_rate = 0
                if self.panic_exits > 0:
                    # Estimate wins (positions that hit target before panic)
                    win_rate = ((self.total_fills - self.panic_exits) / max(1, self.total_fills)) * 100

                active_by_asset = {}
                for p in self.active_positions.values():
                    asset = p["asset"]
                    active_by_asset[asset] = active_by_asset.get(asset, 0) + 1

                print(f"   📊 Active: {len(self.active_positions)} | Fills: {fill_rate:.1f}% | Wins: {win_rate:.1f}% | PnL: ${self.total_pnl:.2f}")
                if active_by_asset:
                    asset_summary = ", ".join([f"{k}:{v}" for k, v in active_by_asset.items()])
                    print(f"   🪙 Positions: {asset_summary}")

                # Self-Learning Cycle
                self.run_learning_cycle()

                time.sleep(1)

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Loop Error: {e}")
                time.sleep(1)

if __name__ == "__main__":
    is_live = "--live" in sys.argv
    bot = CryptoScalper(dry_run=not is_live)
    bot.run()
