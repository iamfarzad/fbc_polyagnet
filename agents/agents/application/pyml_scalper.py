"""
HIGH-FREQUENCY Crypto Scalper with Binance Arbitrage

Actively trades 15-minute "Up or Down" crypto markets on Polymarket.
- Buys YES or NO based on Binance momentum
- ACTIVELY SELLS when profit target or stop loss hit (doesn't wait for resolution)
- Compounds gains on every successful flip
- Targets 100s-1000s of trades per day
- Uses BINANCE WebSocket for fastest momentum signal (arbitrage edge)
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

# =============================================================================
# HIGH-FREQUENCY SCALPER CONFIG - OPTIMIZED FOR $200 → $1000+/WEEK
# =============================================================================
# 
# GAMEPLAN: 25-30% daily returns via high-frequency compounding
# - 100+ trades/day at ~0.3% net per trade
# - Tight exits: take profits fast, cut losses faster
# - Compound ALL gains into next trade
#
# MATH: $200 × 1.28^7 = $1,140/week profit
# =============================================================================

# Position management - MORE POSITIONS, SMALLER SIZE
MAX_POSITIONS = 5                    # More concurrent positions for diversification
BET_PERCENT = float(os.getenv("SCALPER_BET_PERCENT", "0.15"))  # 15% per position = 75% max deployed
MIN_BET_USD = 0.50                   # Minimum bet (for small accounts)
MAX_BET_USD = 100.0                  # Safety cap (scales with $200 account)

# Exit strategy - TIGHT EXITS FOR HFT
TAKE_PROFIT_PCT = 0.025             # 2.5% profit = SELL (fast compound)
STOP_LOSS_PCT = -0.04               # 4% loss = CUT FAST (1.6:1 risk/reward)
MIN_HOLD_SECONDS = 15               # 15s min hold (avoid wash trades)
MAX_HOLD_SECONDS = 180              # 3 min max hold (force exit, free up capital)

# High-frequency settings - AGGRESSIVE
CHECK_INTERVAL = 10                  # Check every 10 seconds
MOMENTUM_REVERSAL_EXIT = True        # Exit if momentum flips against position

# Assets to trade - focus on most liquid
ASSETS = ["bitcoin", "ethereum", "solana", "xrp"]

# Binance WebSocket config
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
BINANCE_SYMBOLS = {
    "btcusdt": "bitcoin",
    "ethusdt": "ethereum",
    "solusdt": "solana",
    "xrpusdt": "xrp"
}
MOMENTUM_WINDOW = 20  # 20 seconds - faster signal detection

# Dynamic edge config - LOWER THRESHOLD = MORE TRADES
BASE_MOMENTUM_THRESHOLD = 0.04      # 0.04% base (enter on small moves)
MIN_MOMENTUM_THRESHOLD = 0.015      # 0.015% min (high conviction = tight)
MAX_MOMENTUM_THRESHOLD = 0.15       # 0.15% max (choppy = wider)
VOLATILITY_LOOKBACK = 15            # 15s volatility window


class CryptoScalper:
    """
    HIGH-FREQUENCY Crypto Scalper.
    
    Actively trades both YES and NO sides:
    1. Opens positions based on Binance momentum
    2. ACTIVELY SELLS when profit target or stop loss hit
    3. Compounds gains on every successful flip
    4. Tracks all trades for performance metrics
    """
    
    AGENT_NAME = "scalper"
    
    def __init__(self, dry_run=True):
        self.pm = Polymarket()
        self.dry_run = dry_run
        self.context = get_context()
        
        # Price tracking from RTDS
        self.chainlink_prices = {}  # asset -> current price
        self.price_history = {}     # asset -> list of recent prices
        
        # ACTIVE POSITION TRACKING with entry data
        self.active_positions = {}  # token_id -> {entry_price, entry_time, side, size, asset, market_id}
        self.traded_markets = set() # Markets we've already traded
        
        self.initial_balance = 0.0
        self.address = ""
        
        # Binance price tracking (FAST - arbitrage edge)
        self.binance_prices = {}      # symbol -> current price
        self.binance_history = {}     # symbol -> deque of (timestamp, price)
        self.binance_momentum = {}    # symbol -> momentum %
        self.binance_connected = False
        self.current_threshold = BASE_MOMENTUM_THRESHOLD
        
        # SESSION STATS - Track all trades
        self.session_start = datetime.datetime.now()
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.trade_log = []  # List of completed trades
        
        for symbol in BINANCE_SYMBOLS:
            self.binance_history[symbol] = deque(maxlen=MOMENTUM_WINDOW * 10)
        
        print(f"=" * 60)
        print(f"🚀 HIGH-FREQUENCY CRYPTO SCALPER")
        print(f"=" * 60)
        print(f"Mode: {'DRY RUN' if self.dry_run else '🔴 LIVE TRADING'}")
        print(f"Max Positions: {MAX_POSITIONS}")
        print(f"Bet Size: {BET_PERCENT*100:.0f}% of equity (${MIN_BET_USD}-${MAX_BET_USD})")
        print(f"Take Profit: {TAKE_PROFIT_PCT*100:.1f}% | Stop Loss: {STOP_LOSS_PCT*100:.1f}%")
        print(f"Check Interval: {CHECK_INTERVAL}s (HFT mode)")
        print(f"Strategy: BUY YES/NO → ACTIVE EXIT → COMPOUND")
        print(f"Assets: {', '.join(ASSETS)}")
        print()
        
        try:
            self.initial_balance = self.pm.get_usdc_balance()
            self.address = self.pm.get_address_for_private_key()
            self.context.update_balance(self.initial_balance)
            print(f"Wallet: {self.address[:10]}...")
            print(f"Starting Balance: ${self.initial_balance:.2f}")
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

    # =========================================================================
    # HIGH-FREQUENCY TRADING - ACTIVE POSITION MANAGEMENT
    # =========================================================================

    def get_current_price(self, token_id):
        """Get current market price for a token."""
        try:
            orderbook = self.pm.client.get_order_book(token_id)
            best_bid = float(orderbook.bids[0].price) if orderbook.bids else 0
            best_ask = float(orderbook.asks[0].price) if orderbook.asks else 1
            mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else best_bid or best_ask
            return mid_price, best_bid, best_ask
        except Exception as e:
            return 0.5, 0, 1  # Default to 50/50

    def calculate_position_pnl(self, position_data):
        """
        Calculate current PnL for an active position.
        
        Returns: (pnl_pct, current_price, best_bid)
        """
        token_id = position_data["token_id"]
        entry_price = position_data["entry_price"]
        side = position_data["side"]  # "YES" or "NO"
        
        current_price, best_bid, best_ask = self.get_current_price(token_id)
        
        # For selling, we'd get the bid price
        exit_price = best_bid if best_bid > 0 else current_price
        
        # Calculate PnL based on side
        if exit_price > 0 and entry_price > 0:
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl_pct = 0
        
        return pnl_pct, current_price, best_bid

    def should_exit_position(self, position_data):
        """
        Determine if we should exit a position.
        
        Returns: (should_exit: bool, reason: str)
        """
        token_id = position_data["token_id"]
        entry_time = position_data["entry_time"]
        asset = position_data["asset"]
        side = position_data["side"]
        
        hold_duration = (datetime.datetime.now() - entry_time).total_seconds()
        
        # Don't exit too early (avoid wash trades)
        if hold_duration < MIN_HOLD_SECONDS:
            return False, "min_hold"
        
        # Calculate current PnL
        pnl_pct, current_price, best_bid = self.calculate_position_pnl(position_data)
        
        # TAKE PROFIT - Hit our target!
        if pnl_pct >= TAKE_PROFIT_PCT:
            return True, f"TAKE_PROFIT +{pnl_pct*100:.1f}%"
        
        # STOP LOSS - Cut losses
        if pnl_pct <= STOP_LOSS_PCT:
            return True, f"STOP_LOSS {pnl_pct*100:.1f}%"
        
        # MAX HOLD TIME - Force exit
        if hold_duration >= MAX_HOLD_SECONDS:
            return True, f"MAX_HOLD {hold_duration:.0f}s"
        
        # MOMENTUM REVERSAL - Exit if momentum flipped against us
        if MOMENTUM_REVERSAL_EXIT:
            symbol_map = {"bitcoin": "btcusdt", "ethereum": "ethusdt", "solana": "solusdt", "xrp": "xrpusdt"}
            symbol = symbol_map.get(asset, "")
            if symbol:
                momentum = self.calculate_binance_momentum(symbol)
                # If we're YES (UP) and momentum went negative, or NO (DOWN) and momentum went positive
                if side == "YES" and momentum < -self.current_threshold:
                    return True, f"MOMENTUM_FLIP {momentum:.3f}%"
                elif side == "NO" and momentum > self.current_threshold:
                    return True, f"MOMENTUM_FLIP {momentum:.3f}%"
        
        return False, "hold"

    def exit_position_active(self, token_id, position_data, reason):
        """
        Actively sell a position for profit taking or stop loss.
        
        Returns: (success: bool, pnl: float)
        """
        entry_price = position_data["entry_price"]
        size = position_data["size"]
        side = position_data["side"]
        asset = position_data["asset"]
        entry_time = position_data["entry_time"]
        
        pnl_pct, current_price, best_bid = self.calculate_position_pnl(position_data)
        hold_duration = (datetime.datetime.now() - entry_time).total_seconds()
        
        # Sell at slightly below best bid for faster fill
        sell_price = max(0.01, best_bid - 0.01) if best_bid > 0.02 else 0.01
        expected_return = size * sell_price
        pnl_usd = (sell_price - entry_price) * size
        
        emoji = "💰" if pnl_usd > 0 else "🔻"
        print(f"{emoji} EXITING: {asset.upper()} {side} | {reason}")
        print(f"   Entry: ${entry_price:.3f} → Exit: ${sell_price:.3f} | PnL: ${pnl_usd:+.3f} ({pnl_pct*100:+.1f}%)")
        print(f"   Hold: {hold_duration:.0f}s | Size: {size:.2f} shares")
        
        if self.dry_run:
            print(f"   [DRY RUN] Would sell {size:.2f} shares @ ${sell_price:.3f}")
            # Update stats
            self.total_trades += 1
            self.total_pnl += pnl_usd
            if pnl_usd > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1
            # Remove from tracking
            if token_id in self.active_positions:
                del self.active_positions[token_id]
            return True, pnl_usd
        
        try:
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
                print(f"   ✅ SOLD! Return: ${expected_return:.2f}")
                
                # Update session stats
                self.total_trades += 1
                self.total_pnl += pnl_usd
                if pnl_usd > 0:
                    self.winning_trades += 1
                else:
                    self.losing_trades += 1
                
                # Log trade
                self.trade_log.append({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "asset": asset,
                    "side": side,
                    "entry_price": entry_price,
                    "exit_price": sell_price,
                    "size": size,
                    "pnl_usd": pnl_usd,
                    "pnl_pct": pnl_pct,
                    "hold_seconds": hold_duration,
                    "reason": reason
                })
                
                # Remove from active tracking
                if token_id in self.active_positions:
                    del self.active_positions[token_id]
                
                return True, pnl_usd
            else:
                print(f"   ⚠️ Sell status: {status}")
                return False, 0
                
        except Exception as e:
            print(f"   ❌ Error selling: {e}")
            return False, 0

    def check_and_exit_positions(self):
        """
        Check all active positions and exit if targets hit.
        This is the core HFT loop - runs frequently.
        
        Returns: number of positions exited
        """
        if not self.active_positions:
            return 0
        
        exited = 0
        to_exit = []
        
        # First pass: identify positions to exit
        for token_id, pos_data in self.active_positions.items():
            should_exit, reason = self.should_exit_position(pos_data)
            if should_exit:
                to_exit.append((token_id, pos_data, reason))
        
        # Second pass: execute exits
        for token_id, pos_data, reason in to_exit:
            success, pnl = self.exit_position_active(token_id, pos_data, reason)
            if success:
                exited += 1
            time.sleep(1)  # Rate limit
        
        return exited

    def print_session_stats(self):
        """Print current session statistics."""
        runtime = (datetime.datetime.now() - self.session_start).total_seconds()
        hours = runtime / 3600
        trades_per_hour = self.total_trades / hours if hours > 0 else 0
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        print(f"\n📊 SESSION STATS:")
        print(f"   Trades: {self.total_trades} ({trades_per_hour:.1f}/hr)")
        print(f"   Win Rate: {win_rate:.1f}% ({self.winning_trades}W/{self.losing_trades}L)")
        print(f"   Total PnL: ${self.total_pnl:+.2f}")
        print(f"   Active Positions: {len(self.active_positions)}/{MAX_POSITIONS}")

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
        """
        Open a new position on a market.
        
        HFT MODE:
        - Buys YES or NO based on momentum direction
        - Tracks entry for active exit management
        - Uses compound sizing
        """
        market_id = market["id"]
        question = market["question"]
        asset = market["asset"]
        up_token = market["up_token"]
        down_token = market["down_token"]
        
        # Skip if already have position in this market
        if up_token in self.active_positions or down_token in self.active_positions:
            return False
        
        # Get current market prices
        market_price = self.get_market_price(market)
        
        # Calculate bet size based on current capital (COMPOUND!)
        bet_size, current_balance, available = self.calculate_bet_size()
        
        # Get direction based on momentum
        direction = self.get_trade_direction(asset, market_price)
        
        # If no edge detected, skip
        if direction is None:
            return False
        
        # Select token and side based on direction
        # UP momentum = buy YES token, DOWN momentum = buy NO token
        if direction == "UP":
            token_id = up_token
            side_name = "YES"
            entry_price = min(0.60, market_price + 0.02)  # Slightly aggressive for fill
        else:
            token_id = down_token
            side_name = "NO"
            entry_price = min(0.60, (1 - market_price) + 0.02)
        
        # Calculate shares
        shares = bet_size / entry_price
        
        print(f"🎯 OPENING: {asset.upper()} {side_name}")
        print(f"   Market: {question[:40]}...")
        print(f"   Entry: ${entry_price:.3f} | Shares: {shares:.2f} | Size: ${bet_size:.2f}")
        print(f"   Target: +{TAKE_PROFIT_PCT*100:.0f}% (${entry_price*(1+TAKE_PROFIT_PCT):.3f}) | Stop: {STOP_LOSS_PCT*100:.0f}%")
        
        if self.dry_run:
            print(f"   [DRY RUN] Would buy {shares:.2f} {side_name} @ ${entry_price:.3f}")
            # Track position for dry run testing
            self.active_positions[token_id] = {
                "token_id": token_id,
                "market_id": market_id,
                "asset": asset,
                "side": side_name,
                "entry_price": entry_price,
                "entry_time": datetime.datetime.now(),
                "size": shares,
                "bet_usd": bet_size
            }
            return True
        
        try:
            order_args = OrderArgs(
                token_id=str(token_id),
                price=entry_price,
                size=shares,
                side=BUY
            )
            
            signed = self.pm.client.create_order(order_args)
            result = self.pm.client.post_order(signed)
            
            success = result.get("success", False)
            status = result.get("status", "unknown")
            
            if success or status == "matched":
                print(f"   ✅ FILLED! {shares:.2f} {side_name} @ ${entry_price:.3f}")
                
                # TRACK FOR ACTIVE EXIT MANAGEMENT
                self.active_positions[token_id] = {
                    "token_id": token_id,
                    "market_id": market_id,
                    "asset": asset,
                    "side": side_name,
                    "entry_price": entry_price,
                    "entry_time": datetime.datetime.now(),
                    "size": shares,
                    "bet_usd": bet_size
                }
                
                # Record in context
                self.context.add_trade(Trade(
                    market_id=market_id,
                    agent=self.AGENT_NAME,
                    outcome=side_name,
                    size_usd=bet_size,
                    price=entry_price,
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
        HIGH-FREQUENCY main loop:
        1. Check active positions for exit targets (profit/loss)
        2. Exit positions that hit targets
        3. Open new positions if slots available
        4. Track and display session stats
        """
        print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] HFT CYCLE...")
        
        # =====================================================================
        # STEP 1: CHECK AND EXIT POSITIONS (ACTIVE PROFIT TAKING)
        # =====================================================================
        exited = self.check_and_exit_positions()
        if exited > 0:
            print(f"   🔄 Exited {exited} position(s)")
        
        # Get current balance and stats
        current_balance = self.get_current_balance()
        growth = current_balance - self.initial_balance
        growth_pct = (growth / self.initial_balance * 100) if self.initial_balance > 0 else 0
        
        # Get Polymarket positions (may include positions not in our tracking)
        pm_positions = self.get_open_positions()
        pm_position_value = sum(float(p.get("currentValue", 0)) for p in pm_positions)
        
        # Active positions we're tracking
        num_active = len(self.active_positions)
        total_equity = current_balance + pm_position_value
        
        print(f"   💰 Cash: ${current_balance:.2f} | Positions: ${pm_position_value:.2f} | Equity: ${total_equity:.2f}")
        print(f"   📊 Active: {num_active}/{MAX_POSITIONS} | Session PnL: ${self.total_pnl:+.2f}")
        
        # Calculate next bet size
        next_bet, _, equity = self.calculate_bet_size()
        print(f"   🎯 Next bet: ${next_bet:.2f} | Threshold: {self.current_threshold:.3f}%")
        
        # Update state file with HFT stats
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        self.save_state({
            "open_positions": num_active,
            "max_positions": MAX_POSITIONS,
            "last_check": datetime.datetime.now().strftime("%H:%M:%S"),
            "current_balance": current_balance,
            "initial_balance": self.initial_balance,
            "growth_usd": growth,
            "growth_pct": growth_pct,
            "total_equity": total_equity,
            "next_bet_size": next_bet,
            "compound_mode": True,
            "hft_mode": True,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "session_pnl": self.total_pnl,
            "win_rate": win_rate,
            "take_profit_pct": TAKE_PROFIT_PCT * 100,
            "stop_loss_pct": STOP_LOSS_PCT * 100,
        })
        
        # =====================================================================
        # STEP 2: OPEN NEW POSITIONS IF WE HAVE SLOTS
        # =====================================================================
        if num_active < MAX_POSITIONS:
            needed = MAX_POSITIONS - num_active
            print(f"   📈 Opening {needed} new position(s)...")
            
            # Get available markets
            markets = self.get_available_markets()
            
            # Track which assets we already have positions in
            position_assets = set(p["asset"] for p in self.active_positions.values())
            
            # Open positions - prefer diversification
            opened = 0
            for market in markets:
                if opened >= needed:
                    break
                
                # Skip if already have this asset
                if market["asset"] in position_assets:
                    continue
                
                if self.open_position(market):
                    opened += 1
                    position_assets.add(market["asset"])
                    time.sleep(1)  # Faster rate limit for HFT
            
            # If still need more, allow same asset (different markets)
            if opened < needed:
                for market in markets:
                    if opened >= needed:
                        break
                    # Check if we already have position in this exact market
                    up_token = market["up_token"]
                    down_token = market["down_token"]
                    if up_token in self.active_positions or down_token in self.active_positions:
                        continue
                    if self.open_position(market):
                        opened += 1
                        time.sleep(1)
            
            if opened > 0:
                print(f"   ✅ Opened {opened} new position(s)")
        else:
            print(f"   ✓ Positions at max capacity")

    def save_state(self, update: dict):
        """Save state for dashboard with HFT stats."""
        state_file = "scalper_state.json"
        try:
            current = {}
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    current = json.load(f)
            
            current.update(update)
            
            # HFT activity message
            total_trades = update.get("total_trades", self.total_trades)
            session_pnl = update.get("session_pnl", self.total_pnl)
            win_rate = update.get("win_rate", 0)
            positions = update.get("open_positions", 0)
            binance_ok = "🚀" if self.binance_connected else "⚠️"
            
            # Format: [emoji] positions | trades | PnL | win rate
            current["scalper_last_activity"] = f"{binance_ok} {positions}/{MAX_POSITIONS} | {total_trades} trades | ${session_pnl:+.2f} | {win_rate:.0f}%W"
            
            current["scalper_last_endpoint"] = "HFT + BINANCE ARB" if self.binance_connected else "HFT ONLY"
            current["mode"] = "DRY RUN" if self.dry_run else "LIVE HFT"
            current["dynamic_threshold"] = self.current_threshold
            current["threshold_range"] = f"{MIN_MOMENTUM_THRESHOLD:.2f}-{MAX_MOMENTUM_THRESHOLD:.2f}%"
            current["check_interval"] = CHECK_INTERVAL
            current["take_profit"] = f"{TAKE_PROFIT_PCT*100:.0f}%"
            current["stop_loss"] = f"{STOP_LOSS_PCT*100:.0f}%"
            
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
        
        # Main loop - HIGH FREQUENCY
        print(f"\n🚀 HIGH-FREQUENCY SCALPER ACTIVE")
        print(f"   Check Interval: {CHECK_INTERVAL}s")
        print(f"   Take Profit: +{TAKE_PROFIT_PCT*100:.0f}% | Stop Loss: {STOP_LOSS_PCT*100:.0f}%")
        print(f"   Target: 500-1000+ trades/day")
        print()
        
        cycle_count = 0
        stats_interval = 20  # Print full stats every 20 cycles (~5 min)
        
        while True:
            try:
                cycle_count += 1
                
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
                
                # HFT CYCLE: Check exits + Open new positions
                self.check_and_rebalance()
                
                # Show momentum signals (compact, every 4th cycle)
                if self.binance_prices and cycle_count % 4 == 0:
                    signals = []
                    for symbol, asset in BINANCE_SYMBOLS.items():
                        momentum = self.calculate_binance_momentum(symbol)
                        self.binance_momentum[symbol] = momentum
                        if abs(momentum) > self.current_threshold:
                            direction = "↑" if momentum > 0 else "↓"
                            signals.append(f"{asset[:3].upper()}{direction}{abs(momentum):.2f}%")
                    if signals:
                        print(f"   📡 Signals: {' | '.join(signals)}")
                
                # Print full session stats periodically
                if cycle_count % stats_interval == 0:
                    self.print_session_stats()
                
                # Save state
                self.save_state({
                    "binance_prices": self.binance_prices,
                    "binance_momentum": self.binance_momentum,
                    "chainlink_prices": self.chainlink_prices,
                    "binance_connected": self.binance_connected,
                    "last_update": datetime.datetime.now().strftime("%H:%M:%S"),
                    "hft_mode": True,
                })
                
                # Sleep until next check (fast for HFT)
                time.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                print("\n" + "="*60)
                print("STOPPING HFT SCALPER - FINAL STATS:")
                self.print_session_stats()
                print("="*60)
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(10)  # Shorter error sleep for HFT


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
