"""
HYBRID SNIPER SCALPER (Production Ready)
Optimized for 2026 Polymarket Fee Structure (~3% Taker Fees).

STRATEGY:
1. Discovery: Scans 15-min "Up or Down" crypto markets.
2. Entry: Smart Maker (Queue Jumper). Jumps big walls, joins small ones.
3. Exit: Hybrid. Try Maker first, panic to Taker if PnL hits -2%.
4. Safety: Dynamic timeouts (3s vs 15s) based on Binance volatility.
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

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

# Portfolio & Size - RELAXED FOR $5.00 COMPOUNDING CYCLE
MAX_POSITIONS = 5
BET_PERCENT = float(os.getenv("SCALPER_BET_PERCENT", "0.25"))  # 25% sizing (more aggressive)
MIN_BET_USD = 5.00  # FORCED $5.00
MAX_BET_USD = 5.00  # FORCED $5.00
MAX_DAILY_DRAWDOWN_PCT = 0.50       # Relaxed daily stop loss for testing

# Maker Execution (The Trap)
LIMIT_ORDER_TIMEOUT_CALM = 10       # 10s in calm markets
LIMIT_ORDER_TIMEOUT_VOLATILE = 2    # 2s in choppy markets (Anti-Adverse Selection)
QUEUE_JUMP_THRESHOLD = 0.0          # Always jump to the front of the queue
MAKER_OFFSET = 0.001                # Standard tick size

# Hybrid Exit (The Escape)
TAKE_PROFIT_PCT = 0.025             # +2.5% Target (Maker)
STOP_LOSS_PCT = -0.04               # -4.0% Hard Stop (Taker)
PANIC_THRESHOLD_PCT = -0.02         # If -2.0% PnL, switch to Taker immediately
EXIT_MAKER_TIMEOUT = 8              # Try maker exit for 8s

# Binance & Signal
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
BINANCE_SYMBOLS = {
    "btcusdt": "bitcoin",
    "ethusdt": "ethereum",
    "solusdt": "solana",
    "xrpusdt": "xrp"
}
BASE_MOMENTUM_THRESHOLD = 0.0       # 0.0% momentum - immediate trades for $5.00 compounding cycle
MIN_LIQUIDITY_USD = 15              # Minimum order book depth


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
        self.traded_markets = set()     # market_id cache

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

        # Init Components
        self.redeemer = None
        try:
            from agents.utils.auto_redeem import AutoRedeemer
            self.redeemer = AutoRedeemer()
        except: pass

        print(f"="*60)
        print(f"🧬 HYBRID SNIPER SCALPER (Production Ready)")
        print(f"="*60)
        print(f"Mode: {'DRY RUN' if self.dry_run else '🔴 LIVE'}")
        print(f"Timeouts: {LIMIT_ORDER_TIMEOUT_VOLATILE}s (Volatile) - {LIMIT_ORDER_TIMEOUT_CALM}s (Calm)")
        print(f"Exit: Maker first, Panic Taker at {PANIC_THRESHOLD_PCT*100}% PnL")
        print(f"Queue Logic: Jump wall if size > ${QUEUE_JUMP_THRESHOLD}")
        print(f"="*60)
        print(f"Queue Logic: Jump wall if size > ${QUEUE_JUMP_THRESHOLD}")
        print(f"="*60)

        # Price caching for performance
        self.price_cache = {}  # token_id -> (timestamp, price_data)
        self._init_polymarket_websocket()

    def _log(self, action, question, reasoning, confidence=1.0):
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
                    conclusion="EXECUTED",
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
            best_bid = float(book.bids[0].price) if book.bids else 0.0
            bid_size = float(book.bids[0].size) if book.bids else 0.0
            best_ask = float(book.asks[0].price) if book.asks else 1.0
            if best_bid == 0 and best_ask == 1: return 0.5, 0.0, 0.0, 1.0

            price_data = ((best_bid + best_ask)/2, best_bid, bid_size, best_ask)
            # Cache the REST data
            if not hasattr(self, 'price_cache'):
                self.price_cache = {}
            self.price_cache[token_id] = (time.time(), price_data)
            return price_data
        except: return 0.5, 0.0, 0.0, 1.0

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
        if self.dry_run: return

        try:
            # 1. Fetch actual held positions
            user = self.pm.get_address_for_private_key()
            url = f"https://data-api.polymarket.com/positions?user={user}"
            positions = requests.get(url, timeout=5).json()

            held_token_ids = {p["asset"]: p for p in positions if float(p["size"]) > 0.1}

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
        """Scale bet size based on asset volatility and correlation."""
        base_size = self.get_balance() * BET_PERCENT

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

    def open_position_maker(self, market, direction):
        token_id = market["up_token"] if direction == "UP" else market["down_token"]

        # 1. Check if already active + correlation risk
        if token_id in self.active_positions: return False
        if not self.check_correlation_risk(market["asset"], direction): return False

        # 2. Analyze Queue
        _, best_bid, bid_size, _ = self.get_current_price(token_id)

        # Queue Logic: If big wall, jump it. If small, join it.
        if bid_size > QUEUE_JUMP_THRESHOLD:
            entry_price = round(best_bid + MAKER_OFFSET, 3)
        else:
            entry_price = best_bid

        # Cap price (Risk)
        if entry_price > 0.75: return False
        if entry_price < 0.10: return False # Garbage

        # 3. Size & Balance (Now asset-aware)
        balance = self.get_balance()
        if balance < MIN_BET_USD: return False

        size_usd = self.get_optimal_bet_size(market["asset"])
        size_shares = size_usd / entry_price

        # 4. Fetch Fee Rate
        fee_rate_bps = 0
        try:
            fee_url = f"https://clob.polymarket.com/fee-rate?token_id={token_id}"
            fee_resp = requests.get(fee_url, timeout=2).json()
            fee_rate_bps = int(fee_resp.get("fee_rate_bps", 0))
        except Exception as e:
            print(f"   ⚠️ Fee Fetch Failed (Defaulting to 0): {e}")

        # 5. Place Limit Order
        print(f"   🔫 SNIPING: Maker {direction} {market['asset']} @ ${entry_price:.3f} (${size_usd:.0f}) | Fee: {fee_rate_bps} bps")

        if self.dry_run:
            # Simulate with better fill rate
            import random
            fill_chance = 0.30 if bid_size < QUEUE_JUMP_THRESHOLD else 0.20  # Better fills in small queues
            if random.random() < fill_chance:
                self.active_positions[token_id] = {
                    "token_id": token_id,
                    "asset": market["asset"],
                    "side": direction,
                    "entry_price": entry_price,
                    "size": size_shares,
                    "entry_time": time.time(),
                    "market_id": market["id"]
                }
                print("   ✅ [DRY] Simulated Fill")
                self._log("SNIPE_DRY", market["asset"], f"Simulated Maker Entry @ {entry_price}", 0.9)
                self.total_fills += 1
            return True

        try:
            # Pass fee_rate_bps to place_limit_order
            resp = self.pm.place_limit_order(token_id, entry_price, size_shares, "BUY", fee_rate_bps=fee_rate_bps)
            order_id = resp.get("orderID")

            if order_id:
                self.pending_orders[order_id] = {
                    "type": "entry",
                    "time": time.time(),
                    "token_id": token_id,
                    "market_id": market["id"],
                    "asset": market["asset"],
                    "side": direction,
                    "price": entry_price,
                    "timeout": self.get_dynamic_timeout(market["asset"])
                }
                self.total_orders += 1
                self._log("SNIPE_LIVE", market["asset"], f"Placed Limit Order @ {entry_price} (Size: {size_usd})", 1.0)
                return True
        except Exception as e:
            print(f"   ❌ Entry Failed: {e}")
            return False

    # -------------------------------------------------------------------------
    # HYBRID EXIT (Maker First -> Panic Taker)
    # -------------------------------------------------------------------------

    def manage_positions(self):
        """Check exits for all active positions."""
        for token_id, pos in list(self.active_positions.items()):
            _, best_bid, _, best_ask = self.get_current_price(token_id)

            # PnL Calc (Mark-to-Market against Best Bid)
            if best_bid == 0: continue
            pnl_pct = (best_bid - pos["entry_price"]) / pos["entry_price"]

            # 1. PANIC EXIT (Taker)
            if pnl_pct < PANIC_THRESHOLD_PCT:
                print(f"   🚨 PANIC EXIT: {pos['asset']} PnL {pnl_pct*100:.1f}%")
                if not self.dry_run:
                    self.pm.execute_market_order([{'metadata': {'clob_token_ids': str([None, token_id])}}], pos['size'])
                self.panic_exits += 1
                self.total_pnl += (pnl_pct * pos["size"] * pos["entry_price"])
                self._log("PANIC_STOP", pos["asset"], f"Taker Exit triggered at {pnl_pct*100:.1f}% PnL", 1.0)
                del self.active_positions[token_id]
                continue

            # 2. TARGET HIT (Maker)
            if pnl_pct > TAKE_PROFIT_PCT:
                # Place Maker Sell at Best Ask - 0.001
                sell_price = round(best_ask - MAKER_OFFSET, 3)
                print(f"   💰 TARGET HIT: Placing Maker Sell @ ${sell_price}")

                if self.dry_run:
                    self.total_pnl += (pnl_pct * pos["size"] * pos["entry_price"])
                    del self.active_positions[token_id]
                    continue

                try:
                    resp = self.pm.place_limit_order(token_id, sell_price, pos["size"], "SELL")
                    if resp.get("orderID"):
                        self.pending_orders[resp["orderID"]] = {
                            "type": "exit",
                            "time": time.time(),
                            "token_id": token_id,
                            "timeout": EXIT_MAKER_TIMEOUT
                        }
                        # We don't delete from active_positions until confirmed filled/gone
                        # But for simplicity in this loop, we mark it 'exiting' state?
                        # For now, just leave it. If order fills, position disappears from sync_positions.
                except: pass

    # -------------------------------------------------------------------------
    # UTILS
    # -------------------------------------------------------------------------

    def reap_stale_orders(self):
        """Cancel orders older than their dynamic timeout."""
        now = time.time()
        for oid, meta in list(self.pending_orders.items()):
            age = now - meta["time"]
            limit = meta["timeout"]

            if age > limit:
                print(f"   💀 REAPING: Order {oid[:8]} (Age {age:.1f}s)")
                if not self.dry_run:
                    try: self.pm.client.cancel(oid)
                    except: pass
                del self.pending_orders[oid]

                # If exit failed, we might need to panic next loop.
                # (Position remains in active_positions so it will be picked up by manage_positions again)

    def check_circuit_breaker(self):
        if self.total_pnl < (self.initial_balance * -MAX_DAILY_DRAWDOWN_PCT):
            print(f"   🛑 CIRCUIT BREAKER: Down {MAX_DAILY_DRAWDOWN_PCT*100}%")
            self.circuit_breaker_triggered = True
            return True
        return False

    def on_binance_message(self, ws, message):
        try:
            data = json.loads(message)
            if "data" in data and "s" in data["data"] and "c" in data["data"]:
                s = data["data"]["s"].lower()
                p = float(data["data"]["c"])
                # Store TUPLE (time, price) for correct volatility calc
                if s in self.binance_history:  # Defensive check
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

    def run(self):
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
                self.reap_stale_orders()
                self.sync_positions() # The "Check Fills" Logic
                if self.check_circuit_breaker(): continue

                if self.redeemer:
                    try: self.redeemer.scan_and_redeem()
                    except: pass

                # 3. Manage Exits
                self.manage_positions()

                # 4. Scan & Enter (Optimized)
                print(f"   🔄 SCAN: active_positions={len(self.active_positions)}, MAX_POSITIONS={MAX_POSITIONS}")
                if len(self.active_positions) < MAX_POSITIONS:
                    markets = self.get_available_markets()
                    print(f"   📊 MARKETS FOUND: {len(markets) if markets else 0}")

                    if markets:  # Only process if we found markets
                        print(f"   🔍 PROCESSING {len(markets)} markets...")
                        for m in markets:
                            try:
                                asset = m['asset']

                                # TEMPORARY: Skip Binance validation for testing - force trade on bitcoin
                                if asset == "bitcoin":
                                    print(f"   🎯 FORCED TEST TRADE: {asset.upper()} UP (bypassing Binance)")
                                    self.open_position_maker(m, "UP")
                                    continue

                                # Invert the BINANCE_SYMBOLS mapping (symbol -> asset) to (asset -> symbol)
                                asset_to_symbol = {v: k for k, v in BINANCE_SYMBOLS.items()}
                                print(f"   🔍 CHECKING {asset.upper()}: in_mapping={asset in asset_to_symbol}")

                                # Defensive check: ensure we have Binance data for this asset
                                if asset not in asset_to_symbol:
                                    print(f"   ❌ {asset.upper()}: not in asset_to_symbol mapping")
                                    continue
                                symbol = asset_to_symbol[asset]
                                print(f"   🔍 {asset.upper()}: symbol={symbol}, in_history={symbol in self.binance_history}")

                                if symbol not in self.binance_history:
                                    print(f"   ❌ {asset.upper()}: no Binance history for {symbol}")
                                    continue

                                history = self.binance_history[symbol]
                                print(f"   🔍 {asset.upper()}: history_length={len(history)}")
                                if len(history) < 2:
                                    print(f"   ❌ {asset.upper()}: insufficient history ({len(history)} < 2)")
                                    continue

                                # Calc Momentum (more responsive with recent prices)
                                recent_prices = [p for t, p in history if time.time() - t < 30]  # Last 30s
                                if len(recent_prices) < 2: continue

                                mom = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]

                                # Dynamic threshold based on volatility
                                vol = self.calculate_volatility(symbol)  # Use symbol we already validated
                                threshold = BASE_MOMENTUM_THRESHOLD * (1 + vol)  # Higher threshold in volatile markets

                                print(f"   🔍 CHECKING {asset.upper()}: mom={mom:.8f}, threshold={threshold:.8f}, prices={len(recent_prices)}")

                                # TEMPORARY: Force trade on bitcoin for testing
                                force_test_trade = (asset == "bitcoin")
                                if abs(mom) > threshold or force_test_trade:
                                    direction = "UP" if mom > 0 else "DOWN"
                                    print(f"   🎯 TEST TRADE: {asset.upper()} {direction} (mom={mom:.8f}, threshold={threshold:.8f})")
                                    self.open_position_maker(m, direction)
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