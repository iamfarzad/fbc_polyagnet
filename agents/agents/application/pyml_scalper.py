"""
15-Minute Crypto Scalper with Binance Arbitrage

Automatically trades 15-minute "Up or Down" crypto markets on Polymarket.
- Maintains N open positions at all times
- When a position resolves, opens a new one
- Uses BINANCE WebSocket for fastest momentum signal (arbitrage edge)
- Falls back to Chainlink RTDS for confirmation
- Cycles through BTC, ETH, SOL, XRP
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

from agents.polymarket.polymarket import Polymarket
from agents.utils.context import get_context, Position, Trade

load_dotenv()

# Config
MAX_POSITIONS = 3
BET_PERCENT = float(os.getenv("SCALPER_BET_PERCENT", "0.30"))  # 30% of total equity per position
MIN_BET_USD = 1.0   # Minimum bet size
MAX_BET_USD = 100.0 # Maximum bet size (safety cap)
ASSETS = ["bitcoin", "ethereum", "solana", "xrp"]
CHECK_INTERVAL = 60  # Check positions every 60 seconds

# Binance WebSocket config
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
BINANCE_SYMBOLS = {
    "btcusdt": "bitcoin",
    "ethusdt": "ethereum",
    "solusdt": "solana",
    "xrpusdt": "xrp"
}
MOMENTUM_WINDOW = 60  # Track last 60 seconds of prices

# Dynamic edge config (adaptive thresholds)
BASE_MOMENTUM_THRESHOLD = 0.08  # Base threshold (lowered from 0.10)
MIN_MOMENTUM_THRESHOLD = 0.03  # Minimum threshold for high-conviction scenarios
MAX_MOMENTUM_THRESHOLD = 0.25  # Maximum threshold for choppy/high-vol markets
VOLATILITY_LOOKBACK = 30       # Seconds to calculate volatility


class CryptoScalper:
    """
    Automated 15-minute crypto scalper.
    
    Keeps MAX_POSITIONS open at all times by:
    1. Checking for resolved positions
    2. Opening new positions on the next available 15-min market
    3. Using real-time Chainlink prices to decide UP vs DOWN
    """
    
    AGENT_NAME = "scalper"
    
    def __init__(self, dry_run=True):
        self.pm = Polymarket()
        self.dry_run = dry_run
        self.context = get_context()
        
        # Price tracking from RTDS
        self.chainlink_prices = {}  # asset -> current price
        self.price_history = {}     # asset -> list of recent prices
        
        # Position tracking
        self.open_positions = {}    # market_id -> position data
        self.traded_markets = set() # Markets we've already traded (avoid duplicates)
        
        self.initial_balance = 0.0
        self.address = ""
        
        # Binance price tracking (FAST - arbitrage edge)
        self.binance_prices = {}      # symbol -> current price
        self.binance_history = {}     # symbol -> deque of (timestamp, price)
        self.binance_momentum = {}    # symbol -> momentum %
        self.binance_connected = False
        self.current_threshold = BASE_MOMENTUM_THRESHOLD  # Dynamic threshold tracking
        
        # Performance tracking for adaptive thresholds
        self.trade_history = []       # List of (timestamp, won: bool)
        self.recent_win_rate = 0.5    # Rolling win rate
        
        for symbol in BINANCE_SYMBOLS:
            self.binance_history[symbol] = deque(maxlen=MOMENTUM_WINDOW * 10)  # ~10 updates/sec
        
        print(f"=" * 60)
        print(f"15-MIN CRYPTO SCALPER - BINANCE ARBITRAGE MODE")
        print(f"=" * 60)
        print(f"Mode: {'DRY RUN' if self.dry_run else '🔴 LIVE TRADING'}")
        print(f"Max Positions: {MAX_POSITIONS}")
        print(f"Bet Size: {BET_PERCENT*100:.0f}% of equity (${MIN_BET_USD}-${MAX_BET_USD})")
        print(f"Assets: {', '.join(ASSETS)}")
        print(f"Strategy: COMPOUND + BINANCE ARBITRAGE")
        print(f"Edge: Binance WS (~50ms) vs Chainlink (~500ms)")
        print()
        
        try:
            self.initial_balance = self.pm.get_usdc_balance()
            self.address = self.pm.get_address_for_private_key()
            self.context.update_balance(self.initial_balance)
            print(f"Wallet: {self.address[:10]}...")
            print(f"Balance: ${self.initial_balance:.2f}")
        except Exception as e:
            print(f"Warning: Could not get balance: {e}")
        
        print(f"=" * 60)
        print()

    def get_open_positions(self):
        """Fetch current open positions from Polymarket."""
        try:
            url = f"https://data-api.polymarket.com/positions?user={self.address}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                positions = resp.json()
                # Filter for 15-min crypto markets
                crypto_positions = []
                for p in positions:
                    title = p.get("title", "").lower()
                    if "up or down" in title:
                        crypto_positions.append(p)
                return crypto_positions
        except Exception as e:
            print(f"Error fetching positions: {e}")
        return []

    def close_position(self, position):
        """
        Close a position by selling the shares back to the market.
        
        Args:
            position: Position dict from get_open_positions()
        
        Returns:
            bool: True if closed successfully
        """
        try:
            token_id = position.get("asset")
            size = float(position.get("size", 0))
            title = position.get("title", "Unknown")
            current_value = float(position.get("currentValue", 0))
            
            if size <= 0:
                print(f"   ⚠️ No shares to sell for: {title[:40]}...")
                return False
            
            # Get current market price for this token
            try:
                orderbook = self.pm.client.get_order_book(token_id)
                best_bid = float(orderbook.bids[0].price) if orderbook.bids else 0.01
            except:
                best_bid = 0.45  # Fallback to conservative price
            
            # Sell slightly below best bid for faster fill
            sell_price = max(0.01, best_bid - 0.02)
            
            print(f"📉 Closing: {title[:45]}...")
            print(f"   Shares: {size:.4f} | Value: ${current_value:.2f}")
            print(f"   Selling @ ${sell_price:.2f}")
            
            if self.dry_run:
                print(f"   [DRY RUN] Would sell {size:.4f} shares")
                return True
            
            order_args = OrderArgs(
                token_id=str(token_id),
                price=sell_price,
                size=size,
                side=SELL
            )
            
            signed = self.pm.client.create_order(order_args)
            result = self.pm.client.post_order(signed)
            
            success = result.get("success", False)
            status = result.get("status", "unknown")
            
            if success or status == "matched":
                print(f"   ✅ SOLD! Recovered ~${size * sell_price:.2f}")
                return True
            else:
                print(f"   ⚠️ Sell status: {status}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error closing position: {e}")
            return False

    def close_all_positions(self):
        """Close all open 15-min crypto positions."""
        positions = self.get_open_positions()
        
        if not positions:
            print("No open positions to close.")
            return 0
        
        print(f"\n{'='*60}")
        print(f"CLOSING {len(positions)} OPEN POSITIONS")
        print(f"{'='*60}\n")
        
        closed = 0
        for p in positions:
            if self.close_position(p):
                closed += 1
            time.sleep(2)  # Rate limit
        
        print(f"\n✅ Closed {closed}/{len(positions)} positions")
        
        # Clear traded markets to allow re-entry with new algo
        self.traded_markets.clear()
        
        return closed

    def get_available_markets(self):
        """Get 15-min crypto markets that are accepting orders."""
        try:
            url = "https://gamma-api.polymarket.com/markets"
            params = {
                "limit": 100,
                "active": "true",
                "closed": "false",
                "order": "createdAt",
                "ascending": "false"
            }
            resp = requests.get(url, params=params, timeout=10)
            markets = resp.json()
            
            available = []
            for m in markets:
                q = m.get("question", "").lower()
                if "up or down" not in q:
                    continue
                if not m.get("acceptingOrders", False):
                    continue
                
                clob_ids = m.get("clobTokenIds")
                if not clob_ids or clob_ids == "[]":
                    continue
                
                # Check which asset
                asset = None
                for a in ASSETS:
                    if a in q:
                        asset = a
                        break
                
                if not asset:
                    continue
                
                try:
                    tokens = ast.literal_eval(clob_ids) if isinstance(clob_ids, str) else clob_ids
                    if len(tokens) >= 2:
                        available.append({
                            "id": m.get("id"),
                            "question": m.get("question"),
                            "asset": asset,
                            "up_token": tokens[0],
                            "down_token": tokens[1],
                            "condition_id": m.get("conditionId"),
                            "end_date": m.get("endDate"),
                        })
                except:
                    pass
            
            return available
        except Exception as e:
            print(f"Error fetching markets: {e}")
        return []

    def calculate_binance_momentum(self, symbol):
        """
        Calculate momentum from Binance price history.
        Returns: momentum % (positive = UP, negative = DOWN)
        """
        history = self.binance_history.get(symbol, deque())
        if len(history) < 10:
            return 0.0
        
        # Get oldest and newest prices in window
        oldest_time, oldest_price = history[0]
        newest_time, newest_price = history[-1]
        
        if oldest_price <= 0:
            return 0.0
        
        momentum = ((newest_price - oldest_price) / oldest_price) * 100
        return momentum

    def calculate_volatility(self, symbol):
        """
        Calculate recent volatility (standard deviation of returns).
        Higher volatility = need stronger signal to avoid noise.
        """
        history = self.binance_history.get(symbol, deque())
        if len(history) < 20:
            return 0.0
        
        # Get prices from last VOLATILITY_LOOKBACK seconds
        now = time.time()
        recent_prices = [p for t, p in history if now - t < VOLATILITY_LOOKBACK]
        
        if len(recent_prices) < 10:
            return 0.0
        
        # Calculate returns
        returns = []
        for i in range(1, len(recent_prices)):
            if recent_prices[i-1] > 0:
                ret = (recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1] * 100
                returns.append(ret)
        
        if not returns:
            return 0.0
        
        # Standard deviation of returns = volatility
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        volatility = variance ** 0.5
        
        return volatility

    def calculate_dynamic_threshold(self, symbol, market_price=0.5):
        """
        Calculate dynamic momentum threshold based on:
        1. Volatility - higher vol = higher threshold (filter noise)
        2. Price skew - extreme prices need less edge
        3. Recent performance - adjust based on win rate
        
        Returns: dynamic threshold for this specific trade
        """
        # Start with base threshold
        threshold = BASE_MOMENTUM_THRESHOLD
        
        # 1. VOLATILITY ADJUSTMENT
        # Higher volatility = need stronger signal to avoid false positives
        volatility = self.calculate_volatility(symbol)
        if volatility > 0.02:
            # High volatility: increase threshold proportionally
            vol_multiplier = 1 + (volatility - 0.02) * 5  # Scale up
            threshold *= min(vol_multiplier, 2.0)  # Cap at 2x
        elif volatility < 0.01 and volatility > 0:
            # Low volatility: can use lower threshold (cleaner signals)
            threshold *= 0.7
        
        # 2. PRICE SKEW ADJUSTMENT
        # Extreme prices (80/20 or higher) are high-probability, need less edge
        # 50/50 markets are coin flips, need stronger edge
        if market_price >= 0.80 or market_price <= 0.20:
            # Strong skew - high probability, lower threshold
            threshold *= 0.5
        elif market_price >= 0.70 or market_price <= 0.30:
            # Moderate skew
            threshold *= 0.75
        elif 0.45 <= market_price <= 0.55:
            # Near 50/50 - need strongest edge
            threshold *= 1.3
        
        # 3. CLAMP TO MIN/MAX
        threshold = max(MIN_MOMENTUM_THRESHOLD, min(threshold, MAX_MOMENTUM_THRESHOLD))
        
        return threshold

    def get_trade_direction(self, asset, market_price=0.5):
        """
        Decide UP or DOWN based on BINANCE momentum (fastest signal).
        Falls back to Chainlink if Binance unavailable.
        
        ARBITRAGE LOGIC:
        - Binance updates ~50ms, Chainlink ~500ms
        - We see momentum 400ms before Polymarket settlement oracle
        - If momentum > DYNAMIC threshold, bet in that direction
        
        DYNAMIC THRESHOLD adapts to:
        - Volatility (noisy = higher threshold)
        - Price skew (extreme = lower threshold needed)
        """
        # Map asset name to Binance symbol
        symbol_map = {
            "bitcoin": "btcusdt",
            "ethereum": "ethusdt",
            "solana": "solusdt",
            "xrp": "xrpusdt"
        }
        symbol = symbol_map.get(asset, "")
        
        # Calculate DYNAMIC threshold for this specific trade
        threshold = self.calculate_dynamic_threshold(symbol, market_price) if symbol else BASE_MOMENTUM_THRESHOLD
        volatility = self.calculate_volatility(symbol) if symbol else 0
        
        # Check Binance momentum (PRIMARY - fastest)
        if symbol and symbol in self.binance_history:
            momentum = self.calculate_binance_momentum(symbol)
            self.binance_momentum[symbol] = momentum
            
            # Store dynamic threshold for logging
            self.current_threshold = threshold
            
            if momentum > threshold:
                print(f"   🚀 BINANCE ARB: {asset.upper()} momentum +{momentum:.3f}% > {threshold:.3f}% (vol:{volatility:.3f}) → UP")
                return "UP"
            elif momentum < -threshold:
                print(f"   🚀 BINANCE ARB: {asset.upper()} momentum {momentum:.3f}% < -{threshold:.3f}% (vol:{volatility:.3f}) → DOWN")
                return "DOWN"
            else:
                # Momentum exists but below dynamic threshold
                print(f"   ⏳ WAITING: {asset.upper()} momentum {momentum:+.3f}% (need >{threshold:.3f}%, vol:{volatility:.3f})")
        
        # Fallback to Chainlink (SECONDARY) - also use dynamic threshold
        chainlink_threshold = threshold * 0.6  # Chainlink can use lower threshold (confirmation signal)
        history = self.price_history.get(asset, [])
        if len(history) >= 2:
            recent = history[-1]
            older = history[-5] if len(history) >= 5 else history[0]
            change_pct = (recent - older) / older * 100 if older > 0 else 0
            
            if change_pct > chainlink_threshold:
                print(f"   📡 CHAINLINK: {asset.upper()} +{change_pct:.3f}% > {chainlink_threshold:.3f}% → UP")
                return "UP"
            elif change_pct < -chainlink_threshold:
                print(f"   📡 CHAINLINK: {asset.upper()} {change_pct:.3f}% < -{chainlink_threshold:.3f}% → DOWN")
                return "DOWN"
        
        # No clear signal - skip this market instead of defaulting
        if symbol and len(self.binance_history.get(symbol, [])) > 0:
            print(f"   ⏸️ NO EDGE: {asset.upper()} - skipping (threshold: {threshold:.3f}%)")
        
        return None  # Changed from "UP" - don't trade without edge

    def get_current_balance(self):
        """Get current USDC balance."""
        try:
            return self.pm.get_usdc_balance()
        except:
            return self.initial_balance
    
    def calculate_bet_size(self):
        """
        Calculate bet size based on TOTAL EQUITY (compound strategy).
        As you win, bets get proportionally larger.
        
        Formula: bet_size = total_equity * BET_PERCENT
        With 30% and 3 positions = 90% of equity in play
        """
        current_balance = self.get_current_balance()
        
        # Get total equity (cash + position values)
        positions = self.get_open_positions()
        position_value = sum(float(p.get("currentValue", 0)) for p in positions)
        total_equity = current_balance + position_value
        
        # Bet size = percentage of TOTAL EQUITY (this is the compound magic)
        # As you win, total_equity grows, so bet_size grows
        bet_size = total_equity * BET_PERCENT
        
        # Apply min/max limits
        bet_size = max(MIN_BET_USD, min(bet_size, MAX_BET_USD))
        
        return bet_size, current_balance, total_equity

    def get_market_price(self, market):
        """Fetch current market price for dynamic threshold calculation."""
        try:
            url = f"https://gamma-api.polymarket.com/markets/{market['id']}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # Get YES/UP price
                outcomes = data.get("outcomePrices", [0.5, 0.5])
                if isinstance(outcomes, str):
                    import ast
                    outcomes = ast.literal_eval(outcomes)
                return float(outcomes[0]) if outcomes else 0.5
        except:
            pass
        return 0.5  # Default to 50/50

    def open_position(self, market):
        """Open a new position on a market with compound sizing and dynamic edge."""
        market_id = market["id"]
        question = market["question"]
        asset = market["asset"]
        
        # Skip if already traded this market
        if market_id in self.traded_markets:
            return False
        
        # Get current market price for dynamic threshold calculation
        market_price = self.get_market_price(market)
        
        # Calculate bet size based on current capital (COMPOUND!)
        bet_size, current_balance, available = self.calculate_bet_size()
        
        # Get direction based on momentum with DYNAMIC threshold
        direction = self.get_trade_direction(asset, market_price)
        
        # If no edge detected, skip this market
        if direction is None:
            print(f"   ⏸️ Skipping {asset.upper()} - no edge at current threshold")
            return False
        
        token_id = market["up_token"] if direction == "UP" else market["down_token"]
        
        # Price: use market price + slight premium for fill
        price = min(0.55, market_price + 0.03) if direction == "UP" else min(0.55, (1 - market_price) + 0.03)
        size = bet_size / price
        
        print(f"📈 Opening: {question[:45]}...")
        print(f"   Equity: ${available:.2f} | Cash: ${current_balance:.2f}")
        print(f"   Bet: ${bet_size:.2f} ({BET_PERCENT*100:.0f}% of equity - COMPOUND)")
        print(f"   Direction: {direction} @ ${price:.2f} (market: {market_price:.0%})")
        print(f"   Dynamic Threshold: {self.current_threshold:.3f}%")
        
        if self.dry_run:
            print(f"   [DRY RUN] Would place order")
            self.traded_markets.add(market_id)
            return True
        
        try:
            order_args = OrderArgs(
                token_id=str(token_id),
                price=price,
                size=size,
                side=BUY
            )
            
            signed = self.pm.client.create_order(order_args)
            result = self.pm.client.post_order(signed)
            
            success = result.get("success", False)
            status = result.get("status", "unknown")
            
            if success or status == "matched":
                print(f"   ✅ FILLED! (${bet_size:.2f} compounded)")
                self.traded_markets.add(market_id)
                
                # Record in context
                self.context.add_position(Position(
                    market_id=market_id,
                    market_question=question,
                    agent=self.AGENT_NAME,
                    outcome=direction,
                    entry_price=price,
                    size_usd=bet_size,
                    timestamp=datetime.datetime.now().isoformat(),
                    token_id=token_id
                ))
                self.context.add_trade(Trade(
                    market_id=market_id,
                    agent=self.AGENT_NAME,
                    outcome=direction,
                    size_usd=bet_size,
                    price=price,
                    timestamp=datetime.datetime.now().isoformat(),
                    status="filled"
                ))
                
                return True
            else:
                print(f"   ⚠️ Order status: {status}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False

    def check_and_rebalance(self):
        """
        Main loop: check positions and open new ones if needed.
        Shows compound growth stats.
        """
        print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] Checking positions...")
        
        # Get current balance and calculate growth
        current_balance = self.get_current_balance()
        growth = current_balance - self.initial_balance
        growth_pct = (growth / self.initial_balance * 100) if self.initial_balance > 0 else 0
        
        # Get current positions
        positions = self.get_open_positions()
        num_positions = len(positions)
        position_value = sum(float(p.get("currentValue", 0)) for p in positions)
        total_equity = current_balance + position_value
        
        print(f"   💰 Balance: ${current_balance:.2f} | Positions: ${position_value:.2f} | Total: ${total_equity:.2f}")
        print(f"   📈 Growth: ${growth:+.2f} ({growth_pct:+.1f}%) from ${self.initial_balance:.2f}")
        print(f"   📊 Open positions: {num_positions}/{MAX_POSITIONS}")
        
        # Calculate next bet size (based on total equity for compound)
        next_bet, _, equity = self.calculate_bet_size()
        print(f"   🎯 Next bet: ${next_bet:.2f} ({BET_PERCENT*100:.0f}% of ${equity:.2f} equity)")
        print(f"   ⚡ Dynamic threshold: {self.current_threshold:.3f}% (range: {MIN_MOMENTUM_THRESHOLD:.2f}-{MAX_MOMENTUM_THRESHOLD:.2f}%)")
        
        # Update state file
        self.save_state({
            "open_positions": num_positions,
            "max_positions": MAX_POSITIONS,
            "last_check": datetime.datetime.now().strftime("%H:%M:%S"),
            "current_balance": current_balance,
            "initial_balance": self.initial_balance,
            "growth_usd": growth,
            "growth_pct": growth_pct,
            "total_equity": total_equity,
            "next_bet_size": next_bet,
            "compound_mode": True,
        })
        
        # If we have fewer than MAX, open more
        if num_positions < MAX_POSITIONS:
            needed = MAX_POSITIONS - num_positions
            print(f"   Need to open {needed} new position(s)")
            
            # Get available markets
            markets = self.get_available_markets()
            print(f"   Available markets: {len(markets)}")
            
            # Filter out markets we already have positions in
            position_assets = set()
            for p in positions:
                title = p.get("title", "").lower()
                for asset in ASSETS:
                    if asset in title:
                        position_assets.add(asset)
            
            # Open positions on different assets
            opened = 0
            for market in markets:
                if opened >= needed:
                    break
                
                # Prefer diversification across assets
                if market["asset"] in position_assets:
                    continue
                
                if market["id"] in self.traded_markets:
                    continue
                
                if self.open_position(market):
                    opened += 1
                    position_assets.add(market["asset"])
                    time.sleep(2)  # Rate limit
            
            # If still need more, allow same asset
            if opened < needed:
                for market in markets:
                    if opened >= needed:
                        break
                    if market["id"] in self.traded_markets:
                        continue
                    if self.open_position(market):
                        opened += 1
                        time.sleep(2)
            
            print(f"   Opened {opened} new position(s)")
        else:
            print(f"   ✓ Positions at max capacity")

    def save_state(self, update: dict):
        """Save state for dashboard with compound + arbitrage stats."""
        state_file = "scalper_state.json"
        try:
            current = {}
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    current = json.load(f)
            
            current.update(update)
            
            # Rich activity message showing compound + arbitrage status
            growth = update.get("growth_usd", 0)
            growth_pct = update.get("growth_pct", 0)
            next_bet = update.get("next_bet_size", MIN_BET_USD)
            positions = update.get("open_positions", 0)
            binance_ok = "🔥" if self.binance_connected else "⚠️"
            
            if growth >= 0:
                current["scalper_last_activity"] = f"{binance_ok} {positions}/{MAX_POSITIONS} | ${growth:+.2f} ({growth_pct:+.1f}%) | ${next_bet:.2f}/trade"
            else:
                current["scalper_last_activity"] = f"{binance_ok} {positions}/{MAX_POSITIONS} | ${growth:.2f} ({growth_pct:.1f}%) | ${next_bet:.2f}/trade"
            
            current["scalper_last_endpoint"] = "BINANCE ARB + CHAINLINK" if self.binance_connected else "CHAINLINK ONLY"
            current["mode"] = "DRY RUN" if self.dry_run else "LIVE ARB"
            current["dynamic_threshold"] = self.current_threshold
            current["threshold_range"] = f"{MIN_MOMENTUM_THRESHOLD:.2f}-{MAX_MOMENTUM_THRESHOLD:.2f}%"
            
            with open(state_file, "w") as f:
                json.dump(current, f)
        except:
            pass

    # =========================================================================
    # BINANCE WEBSOCKET (PRIMARY - FASTEST ~50ms)
    # =========================================================================
    
    def on_binance_message(self, ws, message):
        """Handle Binance real-time price updates."""
        try:
            data = json.loads(message)
            
            # Handle individual symbol updates
            if "s" in data and "c" in data:  # Ticker format
                symbol = data["s"].lower()
                price = float(data["c"])
                
                self.binance_prices[symbol] = price
                if symbol in self.binance_history:
                    self.binance_history[symbol].append((time.time(), price))
            
            # Handle combined stream format
            elif "stream" in data and "data" in data:
                stream_data = data["data"]
                symbol = stream_data.get("s", "").lower()
                price = float(stream_data.get("c", 0))
                
                if symbol and price:
                    self.binance_prices[symbol] = price
                    if symbol in self.binance_history:
                        self.binance_history[symbol].append((time.time(), price))
                    
        except Exception as e:
            pass

    def on_binance_open(self, ws):
        """Handle Binance connection."""
        self.binance_connected = True
        print("🔥 BINANCE WS Connected - ARBITRAGE MODE ACTIVE (~50ms latency)")

    def on_binance_close(self, ws, close_status, close_msg):
        """Handle Binance disconnect."""
        self.binance_connected = False
        print("⚠️ Binance WS disconnected, reconnecting...")

    def on_binance_error(self, ws, error):
        """Handle Binance error."""
        pass

    def run_binance_ws(self):
        """Run Binance WebSocket in background thread."""
        # Combined streams for all symbols
        streams = "/".join([f"{s}@ticker" for s in BINANCE_SYMBOLS.keys()])
        url = f"wss://stream.binance.com:9443/stream?streams={streams}"
        
        while True:
            try:
                ws = websocket.WebSocketApp(
                    url,
                    on_message=self.on_binance_message,
                    on_open=self.on_binance_open,
                    on_close=self.on_binance_close,
                    on_error=self.on_binance_error
                )
                ws.run_forever(ping_interval=30)
            except Exception as e:
                print(f"Binance WS error: {e}")
            time.sleep(5)

    # =========================================================================
    # CHAINLINK RTDS (SECONDARY - ~500ms, settlement oracle)
    # =========================================================================

    def on_rtds_message(self, ws, message):
        """Handle RTDS Chainlink price updates."""
        try:
            data = json.loads(message)
            if data.get("topic") != "crypto_prices_chainlink":
                return
            
            payload = data.get("payload", {})
            symbol = payload.get("symbol", "").lower()
            price = payload.get("value")
            
            if not symbol or not price:
                return
            
            price = float(price)
            self.chainlink_prices[symbol] = price
            
            # Track history for momentum (fallback)
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append(price)
            
            # Keep last 100 prices
            if len(self.price_history[symbol]) > 100:
                self.price_history[symbol] = self.price_history[symbol][-100:]
            
        except:
            pass

    def on_rtds_open(self, ws):
        """Handle RTDS connection."""
        print("📡 CHAINLINK RTDS Connected - settlement oracle (~500ms)")
        sub = {
            "action": "subscribe",
            "subscriptions": [{
                "topic": "crypto_prices_chainlink",
                "type": "*",
                "filters": ""
            }]
        }
        ws.send(json.dumps(sub))

    def run(self):
        """Main run loop with dual WebSocket feeds."""
        
        # Start BINANCE WebSocket (PRIMARY - fastest for arbitrage)
        threading.Thread(target=self.run_binance_ws, daemon=True).start()
        
        # Start RTDS Chainlink (SECONDARY - settlement oracle)
        def run_rtds():
            while True:
                try:
                    ws = websocket.WebSocketApp(
                        "wss://ws-live-data.polymarket.com",
                        on_message=self.on_rtds_message,
                        on_open=self.on_rtds_open,
                        on_error=lambda ws, e: None,
                        on_close=lambda ws, c, m: None
                    )
                    ws.run_forever()
                except:
                    pass
                time.sleep(5)
        
        threading.Thread(target=run_rtds, daemon=True).start()
        
        # Wait for connections
        print("Connecting to price feeds...")
        time.sleep(3)
        
        # Verify Binance connection
        if self.binance_connected:
            print("✅ Binance arbitrage feed active")
        else:
            print("⚠️ Binance not connected yet, will retry...")
        
        time.sleep(2)
        
        # Main loop
        print(f"\n🚀 Starting automated trading loop (check every {CHECK_INTERVAL}s)")
        print()
        
        while True:
            try:
                # Check if enabled
                try:
                    with open("bot_state.json", "r") as f:
                        state = json.load(f)
                    if not state.get("scalper_running", True):
                        print("Scalper paused via dashboard. Sleeping...")
                        time.sleep(60)
                        continue
                    self.dry_run = state.get("dry_run", True)
                except:
                    pass
                
                # Check and rebalance positions
                self.check_and_rebalance()
                
                # Calculate and log Binance momentum (arbitrage data)
                if self.binance_prices:
                    print(f"   📊 BINANCE ARBITRAGE FEED:")
                    for symbol, asset in BINANCE_SYMBOLS.items():
                        price = self.binance_prices.get(symbol, 0)
                        # Calculate momentum NOW
                        momentum = self.calculate_binance_momentum(symbol)
                        self.binance_momentum[symbol] = momentum
                        
                        if price > 0:
                            direction = "📈" if momentum > self.current_threshold else "📉" if momentum < -self.current_threshold else "➡️"
                            signal = "SIGNAL!" if abs(momentum) > self.current_threshold else ""
                            if price > 100:
                                print(f"      {asset.upper()}: ${price:,.0f} {direction} {momentum:+.3f}% {signal}")
                            else:
                                print(f"      {asset.upper()}: ${price:.4f} {direction} {momentum:+.3f}% {signal}")
                
                # Save state with arbitrage info
                self.save_state({
                    "binance_prices": self.binance_prices,
                    "binance_momentum": self.binance_momentum,
                    "chainlink_prices": self.chainlink_prices,
                    "binance_connected": self.binance_connected,
                    "last_update": datetime.datetime.now().strftime("%H:%M:%S"),
                    "arbitrage_mode": True,
                })
                
                # Sleep until next check
                print(f"   Next check in {CHECK_INTERVAL}s...")
                time.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                print("\nStopping scalper...")
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(30)


if __name__ == "__main__":
    is_live = "--live" in sys.argv
    close_positions = "--close" in sys.argv
    
    bot = CryptoScalper(dry_run=not is_live)
    
    if close_positions:
        # Close all positions and exit
        print("\n🔄 CLOSING ALL POSITIONS MODE\n")
        closed = bot.close_all_positions()
        print(f"\nDone. Closed {closed} positions.")
        if is_live:
            print("Waiting 5s then starting new positions with dynamic edge...")
            time.sleep(5)
            bot.run()
    else:
        bot.run()
