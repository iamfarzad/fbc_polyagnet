import os
import sys
import time
import json
import ast
import threading
import datetime
from dotenv import load_dotenv
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY
import websocket

from agents.polymarket.polymarket import Polymarket
from agents.utils.risk_engine import calculate_ev, kelly_size, check_drawdown

load_dotenv()

# Thresholds
DUMP_THRESHOLD = float(os.getenv("DUMP_THRESHOLD", "0.32"))
SKEW_THRESHOLD = float(os.getenv("SKEW_THRESHOLD", "0.78"))
ARB_THRESHOLD = float(os.getenv("ARB_THRESHOLD", "0.97"))
MAX_BET_USD = float(os.getenv("MAX_BET_USD", "3.0"))

# Asset mapping: Chainlink symbol -> Polymarket asset names
ASSET_MAP = {
    "btc/usd": ["bitcoin", "btc"],
    "eth/usd": ["ethereum", "eth"],
    "sol/usd": ["solana", "sol"],
    "xrp/usd": ["xrp"],
}


class CryptoScalper:
    """
    Scalper for 15-min crypto "Up or Down" markets.
    
    Uses RTDS (Real-Time Data Socket) for Chainlink prices since:
    1. 15-min markets are resolved via Chainlink oracles
    2. CLOB orderbooks are empty for these markets
    3. RTDS provides 3-4 price updates per second
    """
    
    def __init__(self, dry_run=True):
        self.pm = Polymarket()
        self.dry_run = dry_run
        
        # Market tracking
        self.active_markets = {}      # market_id -> market object
        self.asset_to_markets = {}    # "btc/usd" -> [market_ids]
        self.market_prices = {}       # market_id -> {"up": price, "down": price}
        
        # Chainlink prices
        self.chainlink_prices = {}    # "btc/usd" -> current_price
        self.price_at_start = {}      # market_id -> price when market opened
        
        # Trading state
        self.last_trade_times = {}
        self.initial_balance = 0.0
        
        print(f"Crypto Scalper Initialized (Dry Run: {self.dry_run})")
        try:
            self.initial_balance = self.pm.get_usdc_balance()
            print(f"Initial Balance: ${self.initial_balance:.2f}")
        except:
            pass
            
        self.bootstrap_markets()

    def bootstrap_markets(self):
        """Find live 15-min crypto 'Up or Down' markets."""
        print("Bootstrapping 15-min crypto markets...")
        
        markets = self.pm.get_all_markets(
            limit=500,
            active="true",
            closed="false",
            archived="false",
            order="createdAt",
            ascending="false"
        )
        
        self.active_markets = {}
        self.asset_to_markets = {k: [] for k in ASSET_MAP.keys()}
        
        for m in markets:
            q = m.question.lower()
            
            if "up or down" not in q:
                continue
                
            # Find which asset this market is for
            asset_symbol = None
            for symbol, names in ASSET_MAP.items():
                if any(name in q for name in names):
                    asset_symbol = symbol
                    break
                    
            if not asset_symbol:
                continue
                
            # Check if accepting orders
            if hasattr(m, 'accepting_orders') and not m.accepting_orders:
                continue
                
            try:
                token_ids = ast.literal_eval(m.clob_token_ids) if isinstance(m.clob_token_ids, str) else m.clob_token_ids
                if not token_ids or len(token_ids) < 2:
                    continue
                    
                self.active_markets[m.id] = {
                    "market": m,
                    "asset": asset_symbol,
                    "token_ids": token_ids,
                    "up_token": token_ids[0],
                    "down_token": token_ids[1],
                }
                
                self.asset_to_markets[asset_symbol].append(m.id)
                
                # Store initial prices from Gamma API
                best_bid = getattr(m, 'best_bid', None)
                if best_bid:
                    self.market_prices[m.id] = {"up": float(best_bid), "down": 1.0 - float(best_bid)}
                    
                print(f"  ✓ {m.question[:50]}... ({asset_symbol})")
                
            except Exception as e:
                print(f"  ✗ Error: {e}")
                
        total = len(self.active_markets)
        print(f"Tracking {total} markets across {len([k for k, v in self.asset_to_markets.items() if v])} assets")

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
                
            # Update Chainlink price
            old_price = self.chainlink_prices.get(symbol)
            self.chainlink_prices[symbol] = float(price)
            
            # Check opportunities for all markets of this asset
            if symbol in self.asset_to_markets:
                for market_id in self.asset_to_markets[symbol]:
                    self.check_opportunity(market_id, old_price, float(price))
                    
            # Update state
            self.save_state({
                "last_update": datetime.datetime.now().strftime("%H:%M:%S"),
                "prices": {symbol: float(price)},
                "active_markets": len(self.active_markets)
            })
            
        except Exception as e:
            pass

    def check_opportunity(self, market_id, old_price, new_price):
        """Check if there's a trading opportunity based on price movement."""
        market_data = self.active_markets.get(market_id)
        if not market_data:
            return
            
        market = market_data["market"]
        asset = market_data["asset"]
        
        # Read dynamic config
        dynamic_max_bet = MAX_BET_USD
        try:
            if os.path.exists("bot_state.json"):
                with open("bot_state.json", "r") as f:
                    state = json.load(f)
                if not state.get("scalper_running", True):
                    return
                dynamic_max_bet = float(state.get("dynamic_max_bet", MAX_BET_USD))
        except:
            pass
            
        # Rate limit: 1 trade per market per 60s
        last_trade = self.last_trade_times.get(market_id, 0)
        if time.time() - last_trade < 60:
            return
            
        # Get balance and check drawdown
        try:
            balance = self.pm.get_usdc_balance()
        except:
            balance = 0
            
        if not check_drawdown(self.initial_balance, balance):
            print("  [RISK] Drawdown limit hit. Pausing trades.")
            return
            
        # Get market prices (Up/Down odds)
        prices = self.market_prices.get(market_id, {})
        p_up = prices.get("up")
        p_down = prices.get("down")
        
        if not p_up or not p_down:
            return
            
        # Strategy: Bet on momentum
        # If price is rising rapidly, bet UP
        # If price is falling rapidly, bet DOWN
        if old_price and new_price:
            price_change_pct = (new_price - old_price) / old_price * 100
            
            # Strong upward momentum (>0.1% in one tick)
            if price_change_pct > 0.1 and p_up < 0.70:
                ev = calculate_ev(p_up, 0.65, 1.0 - p_up, fees=0.015)
                if ev > 0.03:
                    size = min(kelly_size(balance, ev, p_up), dynamic_max_bet)
                    if size >= 1.0:
                        print(f"[{market.question[:25]}] 📈 UP Momentum: +{price_change_pct:.2f}%")
                        self.place_order(market_data["up_token"], size, "UP", market_id)
                        return
                        
            # Strong downward momentum (<-0.1% in one tick)
            elif price_change_pct < -0.1 and p_down < 0.70:
                ev = calculate_ev(p_down, 0.65, 1.0 - p_down, fees=0.015)
                if ev > 0.03:
                    size = min(kelly_size(balance, ev, p_down), dynamic_max_bet)
                    if size >= 1.0:
                        print(f"[{market.question[:25]}] 📉 DOWN Momentum: {price_change_pct:.2f}%")
                        self.place_order(market_data["down_token"], size, "DOWN", market_id)
                        return
        
        # Arbitrage check
        if p_up + p_down < ARB_THRESHOLD:
            print(f"[{market.question[:25]}] ARB: {p_up + p_down:.3f}")
            self.place_order(market_data["up_token"], dynamic_max_bet/2, "UP (Arb)", market_id)
            self.place_order(market_data["down_token"], dynamic_max_bet/2, "DOWN (Arb)", market_id)
            return
            
        # Dump detection (one side extremely cheap)
        if p_up <= DUMP_THRESHOLD:
            ev = calculate_ev(p_up, 0.80, 1.0 - p_up, fees=0.015)
            if ev > 0.05:
                size = min(kelly_size(balance, ev, p_up), dynamic_max_bet)
                if size >= 0.50:
                    print(f"[{market.question[:25]}] UP Dump: {p_up:.2f}")
                    self.place_order(market_data["up_token"], size, "UP", market_id)
                    
        elif p_down <= DUMP_THRESHOLD:
            ev = calculate_ev(p_down, 0.80, 1.0 - p_down, fees=0.015)
            if ev > 0.05:
                size = min(kelly_size(balance, ev, p_down), dynamic_max_bet)
                if size >= 0.50:
                    print(f"[{market.question[:25]}] DOWN Dump: {p_down:.2f}")
                    self.place_order(market_data["down_token"], size, "DOWN", market_id)

    def place_order(self, token_id, amount_usd, side_label, market_id):
        """Place a trade order."""
        # Check dry run mode
        try:
            if os.path.exists("bot_state.json"):
                with open("bot_state.json", "r") as f:
                    state = json.load(f)
                if state.get("dry_run", True):
                    print(f"  [DRY RUN] Would buy {side_label} ${amount_usd:.2f}")
                    return
        except:
            pass

        if self.dry_run:
            print(f"  [DRY RUN] Buy {side_label} ${amount_usd:.2f}")
            return

        try:
            balance = self.pm.get_usdc_balance()
            if balance < 3.0:
                print(f"  [SAFETY] Low balance (${balance:.2f}). Skipping.")
                return
                
            agg_price = 0.999
            size = amount_usd / agg_price
            
            order_args = OrderArgs(token_id=token_id, price=agg_price, size=size, side=BUY)
            signed = self.pm.client.create_order(order_args)
            resp = self.pm.client.post_order(signed)
            
            print(f"  ✅ Order: {resp}")
            self.last_trade_times[market_id] = time.time()
            
            self.save_state({
                "last_trade": f"{side_label} @ ${amount_usd:.2f} ({datetime.datetime.now().strftime('%H:%M:%S')})",
                "last_trade_status": str(resp)
            })
            
        except Exception as e:
            print(f"  ❌ Order Failed: {e}")
            self.save_state({"last_trade_status": f"Failed: {str(e)}"})

    def save_state(self, update: dict):
        """Save state to file for dashboard."""
        state_file = "scalper_state.json"
        try:
            current = {}
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    current = json.load(f)
                    
            if "prices" in update and "prices" in current:
                current["prices"].update(update["prices"])
                del update["prices"]
                
            current.update(update)
            current["scalper_last_activity"] = "Processing RTDS Feed"
            current["scalper_last_endpoint"] = "RTDS Chainlink"
            
            with open(state_file, "w") as f:
                json.dump(current, f)
        except:
            pass

    def refresh_markets(self):
        """Periodically refresh markets and Gamma API prices."""
        while True:
            time.sleep(30)
            try:
                # Refresh market list
                self.bootstrap_markets()
                
                # Update market prices from Gamma API
                markets = self.pm.get_all_markets(
                    limit=100,
                    active="true",
                    closed="false",
                    order="createdAt",
                    ascending="false"
                )
                
                for m in markets:
                    if m.id in self.active_markets:
                        best_bid = getattr(m, 'best_bid', None)
                        if best_bid:
                            self.market_prices[m.id] = {
                                "up": float(best_bid),
                                "down": 1.0 - float(best_bid)
                            }
                            
            except Exception as e:
                print(f"Refresh error: {e}")

    def on_rtds_open(self, ws):
        """Handle RTDS connection open."""
        print("RTDS Connected!")
        
        # Subscribe to Chainlink crypto prices
        sub = {
            "action": "subscribe",
            "subscriptions": [{
                "topic": "crypto_prices_chainlink",
                "type": "*",
                "filters": ""
            }]
        }
        ws.send(json.dumps(sub))
        print("  Subscribed to Chainlink prices (BTC, ETH, SOL, XRP)")
        
        # Start ping thread
        def ping():
            while True:
                time.sleep(30)
                try:
                    ws.send(json.dumps({"action": "ping"}))
                except:
                    break
        threading.Thread(target=ping, daemon=True).start()

    def run(self):
        """Main run loop."""
        # Start market refresh thread
        threading.Thread(target=self.refresh_markets, daemon=True).start()
        
        # Connect to RTDS for real-time Chainlink prices
        rtds_url = "wss://ws-live-data.polymarket.com"
        
        print(f"Connecting to RTDS: {rtds_url}")
        
        while True:
            try:
                ws = websocket.WebSocketApp(
                    rtds_url,
                    on_message=self.on_rtds_message,
                    on_error=lambda ws, e: print(f"RTDS Error: {e}"),
                    on_close=lambda ws, c, m: print("RTDS Closed - reconnecting..."),
                    on_open=self.on_rtds_open
                )
                ws.run_forever()
                
            except Exception as e:
                print(f"RTDS connection error: {e}")
                
            # Reconnect after 5 seconds
            print("Reconnecting in 5s...")
            time.sleep(5)


if __name__ == "__main__":
    is_live = "--live" in sys.argv
    bot = CryptoScalper(dry_run=not is_live)
    bot.run()
