"""
15-Minute Crypto Scalper

Automatically trades 15-minute "Up or Down" crypto markets on Polymarket.
- Maintains N open positions at all times
- When a position resolves, opens a new one
- Uses RTDS for real-time Chainlink prices to inform direction
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
from dotenv import load_dotenv
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY
import websocket

from agents.polymarket.polymarket import Polymarket
from agents.utils.context import get_context, Position, Trade

load_dotenv()

# Config
MAX_POSITIONS = 3
BET_PERCENT = float(os.getenv("SCALPER_BET_PERCENT", "0.30"))  # 30% of total equity per position (90% total)
MIN_BET_USD = 1.0   # Minimum bet size
MAX_BET_USD = 100.0 # Maximum bet size (safety cap)
ASSETS = ["bitcoin", "ethereum", "solana", "xrp"]
CHECK_INTERVAL = 60  # Check positions every 60 seconds


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
        
        print(f"=" * 60)
        print(f"15-MIN CRYPTO SCALPER - COMPOUND MODE")
        print(f"=" * 60)
        print(f"Mode: {'DRY RUN' if self.dry_run else '🔴 LIVE TRADING'}")
        print(f"Max Positions: {MAX_POSITIONS}")
        print(f"Bet Size: {BET_PERCENT*100:.0f}% of available capital (${MIN_BET_USD}-${MAX_BET_USD})")
        print(f"Assets: {', '.join(ASSETS)}")
        print(f"Strategy: COMPOUND GAINS - reinvest all profits")
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

    def get_trade_direction(self, asset):
        """
        Decide UP or DOWN based on recent price momentum.
        Returns: ("UP", up_token) or ("DOWN", down_token)
        """
        history = self.price_history.get(asset, [])
        
        if len(history) >= 2:
            recent = history[-1]
            older = history[-5] if len(history) >= 5 else history[0]
            
            change_pct = (recent - older) / older * 100 if older > 0 else 0
            
            # If price rising, bet UP; if falling, bet DOWN
            if change_pct > 0.05:
                return "UP"
            elif change_pct < -0.05:
                return "DOWN"
        
        # Default: slight bullish bias for crypto
        return "UP"

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

    def open_position(self, market):
        """Open a new position on a market with compound sizing."""
        market_id = market["id"]
        question = market["question"]
        asset = market["asset"]
        
        # Skip if already traded this market
        if market_id in self.traded_markets:
            return False
        
        # Calculate bet size based on current capital (COMPOUND!)
        bet_size, current_balance, available = self.calculate_bet_size()
        
        # Get direction based on momentum
        direction = self.get_trade_direction(asset)
        token_id = market["up_token"] if direction == "UP" else market["down_token"]
        
        # Price: slightly aggressive to ensure fill
        price = 0.52 if direction == "UP" else 0.52
        size = bet_size / price
        
        print(f"📈 Opening: {question[:45]}...")
        print(f"   Equity: ${available:.2f} | Cash: ${current_balance:.2f}")
        print(f"   Bet: ${bet_size:.2f} ({BET_PERCENT*100:.0f}% of equity - COMPOUND)")
        print(f"   Direction: {direction} @ ${price:.2f}")
        
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
        """Save state for dashboard with compound stats."""
        state_file = "scalper_state.json"
        try:
            current = {}
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    current = json.load(f)
            
            current.update(update)
            
            # Rich activity message showing compound status
            growth = update.get("growth_usd", 0)
            growth_pct = update.get("growth_pct", 0)
            next_bet = update.get("next_bet_size", MIN_BET_USD)
            positions = update.get("open_positions", 0)
            
            if growth >= 0:
                current["scalper_last_activity"] = f"🔄 {positions}/{MAX_POSITIONS} pos | ${growth:+.2f} ({growth_pct:+.1f}%) | Next: ${next_bet:.2f}"
            else:
                current["scalper_last_activity"] = f"🔄 {positions}/{MAX_POSITIONS} pos | ${growth:.2f} ({growth_pct:.1f}%) | Next: ${next_bet:.2f}"
            
            current["scalper_last_endpoint"] = "COMPOUND MODE"
            current["mode"] = "DRY RUN" if self.dry_run else "LIVE COMPOUND"
            
            with open(state_file, "w") as f:
                json.dump(current, f)
        except:
            pass

    def on_rtds_message(self, ws, message):
        """Handle RTDS price updates."""
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
            
            # Track history for momentum
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
        print("📡 RTDS Connected - receiving Chainlink prices")
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
        """Main run loop."""
        # Start RTDS connection for price data
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
        
        # Wait for initial price data
        print("Waiting for price data...")
        time.sleep(5)
        
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
                
                # Log current prices
                if self.chainlink_prices:
                    prices_str = " | ".join([
                        f"{k.split('/')[0].upper()}: ${v:,.0f}" if v > 100 else f"{k.split('/')[0].upper()}: ${v:.2f}"
                        for k, v in list(self.chainlink_prices.items())[:4]
                    ])
                    print(f"   Prices: {prices_str}")
                
                # Save state
                self.save_state({
                    "prices": self.chainlink_prices,
                    "last_update": datetime.datetime.now().strftime("%H:%M:%S"),
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
    bot = CryptoScalper(dry_run=not is_live)
    bot.run()
