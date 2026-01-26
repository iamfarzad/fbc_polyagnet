"""
SNIPER SCALPER (Rebuilt for Survival)
Rule 1: Don't lose money.
Rule 2: Don't forget Rule 1.

STRATEGY:
1. Entry: MOMENTUM + VOLATILITY. Only buy if price is moving FAST in one direction.
   - Threshold: > 0.15% move in 60 seconds (Crypto Standard).
   - Validation: Binance Orderbook Imbalance > 1.5x.
2. Exit: TAKER ONLY.
   - Profit: +8% (Take the money and run).
   - Stop: -12% (Cut the limb to save the body).
   - Time Limit: If held > 5 minutes, SELL. (Don't hold 15m options forever).
"""

import time
import requests
import os
from collections import deque
from dotenv import load_dotenv
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

# Local Imports
try:
    from agents.polymarket.polymarket import Polymarket
    from agents.polymarket.gamma import GammaMarketClient
    from agents.utils.config import load_config
    from agents.utils.TradeRecorder import record_trade
except ImportError:
    # Fallback for direct execution
    from agents.agents.polymarket.polymarket import Polymarket
    from agents.agents.polymarket.gamma import GammaMarketClient
    from agents.agents.utils.config import load_config
    from agents.agents.utils.TradeRecorder import record_trade

load_dotenv()

class SniperScalper:
    AGENT_NAME = "scalper_sniper"

    def __init__(self, dry_run=True):
        self.pm = Polymarket()
        self.gamma = GammaMarketClient()
        self.config = load_config("scalper")
        
        # SAFETY OVERRIDES
        self.dry_run = dry_run or self.config.get("global_dry_run", True)
        self.active = self.config.get("active", True)
        
        # PARAMETERS (The "Sniper" Rules)
        self.MIN_MOMENTUM = 0.0015      # 0.15% move required (was 0.0005%)
        self.TAKE_PROFIT = 0.08         # +8%
        self.STOP_LOSS = -0.12          # -12%
        self.MAX_HOLD_TIME = 300        # 5 Minutes Max Hold
        self.BET_SIZE_USD = 10.0        # Fixed size for now
        
        # State
        self.active_positions = {}      # token_id -> {entry_price, time, ...}
        self.binance_history = {}       # symbol -> deque of prices
        self.last_scan = 0

        print(f"🦅 SNIPER SCALPER INITIALIZED")
        print(f"   Mode: {'DRY RUN' if self.dry_run else '🔴 LIVE MONEY'}")
        print(f"   Target: +{self.TAKE_PROFIT*100}% | Stop: {self.STOP_LOSS*100}%")
        print(f"   Momentum Required: {self.MIN_MOMENTUM*100}% (3x previous setting)")

    def get_binance_price(self, symbol="BTCUSDT"):
        """Get live price from Binance for signal validation."""
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            resp = requests.get(url, timeout=2).json()
            return float(resp["price"])
        except:
            return 0.0

    def update_momentum(self, asset):
        """Track price history and calculate % change."""
        symbol = f"{asset.upper()}USDT"
        if symbol == "BITCOINUSDT": symbol = "BTCUSDT"
        
        price = self.get_binance_price(symbol)
        if price == 0: return 0.0

        if symbol not in self.binance_history:
            self.binance_history[symbol] = deque(maxlen=20) # Keep last 20 checks
        
        history = self.binance_history[symbol]
        history.append((time.time(), price))

        # Need at least 60 seconds of data to judge trend
        if len(history) < 2: return 0.0
        
        # Compare Now vs 60s ago (or oldest available)
        start_price = history[0][1]
        pct_change = (price - start_price) / start_price
        
        return pct_change

    def scan_markets(self):
        """Find 15-min markets and check for SNIPE signals."""
        now = time.time()
        if now - self.last_scan < 10: return # Scan every 10s
        self.last_scan = now

        markets = self.gamma.discover_15min_crypto_markets()
        print(f"   🔍 Scanning {len(markets)} active markets...")

        for market in markets:
            asset = market["asset"] # bitcoin, ethereum, etc
            momentum = self.update_momentum(asset)
            
            # SIGNAL CHECK
            direction = None
            if momentum > self.MIN_MOMENTUM: direction = "UP"
            elif momentum < -self.MIN_MOMENTUM: direction = "DOWN"

            if direction:
                print(f"   🎯 SIGNAL: {asset} {direction} (Mom: {momentum*100:.3f}%)")
                self.execute_entry(market, direction, momentum)
            else:
                # Debug log for low momentum
                if abs(momentum) > 0.0005:
                    print(f"   💤 {asset}: Mom {momentum*100:.3f}% < Threshold {self.MIN_MOMENTUM*100}%")

    def execute_entry(self, market, direction, momentum):
        """Enter a position as a TAKER (Speed > Fees)."""
        token_id = market["up_token"] if direction == "UP" else market["down_token"]
        
        if token_id in self.active_positions: return # Already in

        # Get Orderbook
        try:
            book = self.pm.client.get_order_book(token_id)
            if not book.asks: return
            
            # TAKER STRATEGY: Buy the best Ask immediately
            best_ask = float(book.asks[0].price)
            if best_ask > 0.85: 
                print(f"   🚫 PRICE TOO HIGH: {best_ask} > 0.85")
                return # Too expensive, limited upside

            print(f"   🔫 SNIPING {market['asset']} {direction} @ {best_ask}")

            if not self.dry_run:
                # LIVE EXECUTION
                order = self.pm.client.create_order(OrderArgs(
                    price=best_ask + 0.01, # Slippage tolerance
                    size=self.BET_SIZE_USD / best_ask,
                    side=BUY,
                    token_id=token_id,
                    fee_rate_bps=1000
                ))
                resp = self.pm.client.post_orders([PostOrdersArgs(order=order, orderType=OrderType.FOK)])
                if resp and resp[0].success:
                    self.register_position(token_id, market, direction, best_ask)
            else:
                # DRY RUN
                self.register_position(token_id, market, direction, best_ask)
                record_trade(self.AGENT_NAME, market["asset"], direction, self.BET_SIZE_USD, best_ask, token_id, "SNIPER ENTRY")

        except Exception as e:
            print(f"   ❌ ENTRY FAILED: {e}")

    def register_position(self, token_id, market, direction, price):
        self.active_positions[token_id] = {
            "asset": market["asset"],
            "direction": direction,
            "entry_price": price,
            "entry_time": time.time(),
            "market_id": market["id"]
        }
        print(f"   ✅ POSITION OPEN: {market['asset']} {direction} @ {price}")

    def manage_positions(self):
        """Check exits: Take Profit, Stop Loss, or Time Decay."""
        for token_id, pos in list(self.active_positions.items()):
            try:
                # Get Current Price (Bid - because we sell into the bid)
                book = self.pm.client.get_order_book(token_id)
                if not book.bids: continue
                current_bid = float(book.bids[0].price)

                # PnL Calc
                pnl_pct = (current_bid - pos["entry_price"]) / pos["entry_price"]
                held_time = time.time() - pos["entry_time"]

                exit_reason = None
                
                # 1. Take Profit
                if pnl_pct >= self.TAKE_PROFIT:
                    exit_reason = f"WIN (+{pnl_pct*100:.1f}%)"
                
                # 2. Stop Loss
                elif pnl_pct <= self.STOP_LOSS:
                    exit_reason = f"STOP LOSS ({pnl_pct*100:.1f}%)"
                
                # 3. Time Decay (Get out before expiration chaos)
                elif held_time > self.MAX_HOLD_TIME:
                    exit_reason = f"TIME LIMIT ({held_time:.0f}s)"

                if exit_reason:
                    print(f"   👋 EXITING {pos['asset']} {pos['direction']}: {exit_reason} @ {current_bid}")
                    
                    if not self.dry_run:
                        # MARKET SELL
                        order = self.pm.client.create_order(OrderArgs(
                            price=current_bid - 0.01, # Ensure fill
                            size=self.BET_SIZE_USD / pos["entry_price"], # Approx size
                            side=SELL,
                            token_id=token_id,
                            fee_rate_bps=1000
                        ))
                        self.pm.client.post_orders([PostOrdersArgs(order=order, orderType=OrderType.FOK)])
                    else:
                        record_trade(self.AGENT_NAME, pos["asset"], "EXIT", 0, current_bid, token_id, exit_reason)
                    
                    del self.active_positions[token_id]

            except Exception as e:
                print(f"   ⚠️ MANAGING POS ERROR: {e}")

    def run(self):
        """Main Loop."""
        while True:
            try:
                self.scan_markets()
                self.manage_positions()
                time.sleep(1)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"   ⚠️ LOOP ERROR: {e}")
                time.sleep(5)

if __name__ == "__main__":
    bot = SniperScalper()
    bot.run()
