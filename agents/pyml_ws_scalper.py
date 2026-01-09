import os
import sys
import time
import json
import ast
import threading
import datetime
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY
import websocket

# Add current dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agents.polymarket.polymarket import Polymarket
from agents.utils.risk_engine import calculate_ev, kelly_size, check_drawdown

# Load config
load_dotenv()
key = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
if not key:
    try:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
             with open(env_path, "r") as f:
                content = f.read()
                import re
                match = re.search(r'POLYGON_WALLET_PRIVATE_KEY="?([a-fA-F0-9]+)"?', content)
                if match:
                    key = match.group(1)
                    os.environ["POLYGON_WALLET_PRIVATE_KEY"] = key
    except Exception as e:
        print(f"Manual env load failed: {e}")

# Thresholds
DUMP_THRESHOLD = float(os.getenv("DUMP_THRESHOLD", "0.32"))
SKEW_THRESHOLD = float(os.getenv("SKEW_THRESHOLD", "0.78"))
ARB_THRESHOLD = float(os.getenv("ARB_THRESHOLD", "0.97"))
MAX_BET_USD = float(os.getenv("MAX_BET_USD", "3.0"))

TARGET_ASSETS = ["BTC", "ETH", "SOL", "XRP"]

class WS_CryptoScalper:
    def __init__(self, dry_run=True):
        self.pm = Polymarket()
        self.dry_run = dry_run
        self.active_markets = {}  # token_id -> market_info
        self.current_prices = {}  # token_id -> price
        self.tokens_to_market = {} # token_id -> market_id
        self.last_trade_times = {} # token_id -> timestamp
        
        print(f"WS Agent 2 Initialized. Dry Run: {self.dry_run}")
        self.initial_balance = 0.0
        try:
             self.initial_balance = self.pm.get_usdc_balance()
             print(f"Initial Balance: ${self.initial_balance:.2f}")
        except: pass
        self.bootstrap_markets()

    def bootstrap_markets(self):
        print("Bootstrapping 15-min markets...")
        markets = self.pm.get_all_markets(limit=1000, active="true", closed="false", archived="false")
        for m in markets:
            q = m.question.lower()
            is_target = any(asset.lower() in q or (asset == "BTC" and "bitcoin" in q) for asset in TARGET_ASSETS)
            if is_target and "15" in q and "min" in q:
                try:
                    token_ids = ast.literal_eval(m.clob_token_ids)
                    self.active_markets[m.id] = m
                    for tid in token_ids:
                        self.tokens_to_market[tid] = m.id
                    print(f"  Tracking: {m.question}")
                except:
                    pass

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if data.get("type") == "error":
                print(f"WS ERROR: {data.get('message')}")
                return

            # Check for events (delivered as list)
            if isinstance(data, list):
                for item in data:
                    if et == "book":
                        self.handle_book(item)
                    elif et in ["order", "fill", "reward"]:
                        self.handle_user_event(item)
        except Exception as e:
            # print(f"Msg error: {e}")
            pass

    def handle_book(self, item):
        tid = item.get("asset_id")
        if tid in self.tokens_to_market:
            bids = item.get("bids", [])
            asks = item.get("asks", [])
            if bids and asks:
                w_bid = 0
                w_ask = 0
                vol_bid = 0
                vol_ask = 0
                
                # Process up to 3 levels of depth
                for b in bids[:3]:
                    p = float(b['price'])
                    s = float(b['size'])
                    w_bid += p * s
                    vol_bid += s
                    
                for a in asks[:3]:
                    p = float(a['price'])
                    s = float(a['size'])
                    w_ask += p * s
                    vol_ask += s
                    
                if vol_bid > 0 and vol_ask > 0:
                    avg_bid = w_bid / vol_bid
                    avg_ask = w_ask / vol_ask
                    mid = (avg_bid + avg_ask) / 2
                    
                    self.current_prices[tid] = mid
                    self.check_opportunity(tid)
                    
                    # Throttled state save
                    self.save_state({
                        "prices": {self.active_markets[m_id].question[:10]: mid for m_id, m in self.active_markets.items() if m.clob_token_ids and tid in ast.literal_eval(m.clob_token_ids)},
                        "last_update": datetime.datetime.now().strftime("%H:%M:%S")
                    })

    def handle_user_event(self, item):
        try:
            # Handle order statuses (Fills, etc)
            # data structure depends on API, usually has 'type', 'side', 'price', 'size', 'status'
            if item.get("event_type") == "fill" or item.get("type") == "fill":
                side = item.get("side", "UNKNOWN")
                price = item.get("price", "0")
                size = item.get("size", "0")
                mkt_name = "Unknown Market"
                 # Try to find market name if token_id present
                tid = item.get("asset_id")
                if tid:
                    for m_id, m in self.active_markets.items():
                        if tid in m.clob_token_ids:
                             mkt_name = m.question
                             break
                
                print(f"💰 FILL CONFIRMED: {side} {size} @ {price} in {mkt_name}")
                self.save_state({
                    "last_fill": f"{side} {size} @ {price} ({datetime.datetime.now().strftime('%H:%M:%S')})"
                })
        except: pass

    def check_opportunity(self, token_id):
        m_id = self.tokens_to_market.get(token_id)
        market = self.active_markets.get(m_id)
        if not market: return
        
        # Check Control Flag & Config
        dynamic_max_bet = MAX_BET_USD
        try:
            if os.path.exists("bot_state.json"):
                with open("bot_state.json", "r") as f:
                    state = json.load(f)
                if not state.get("scalper_running", True):
                    # print("Scalper Paused") 
                    return
                # Update Max Bet from State if Set
                dynamic_max_bet = float(state.get("dynamic_max_bet", MAX_BET_USD))
        except: pass

            
        token_ids = ast.literal_eval(market.clob_token_ids)
        p_yes = self.current_prices.get(token_ids[0])
        p_no = self.current_prices.get(token_ids[1])
        
        if p_yes is None or p_no is None: return

        # Check Cooldown
        last_trade_time = self.last_trade_times.get(token_ids[0], 0)
        if time.time() - last_trade_time < 60: # 60s cooldown per market
             return

        sum_prob = p_yes + p_no
        
        # Throttled logging (only if significant change or period?)
        # For scalping, we just check logic:
        
        # Risk / Bankroll Check
        balance = 0.0
        try: balance = self.pm.get_usdc_balance()
        except: pass
        
        if not check_drawdown(self.initial_balance, balance):
            print("  [RISK] Drawdown limit hit. Pausing trades.")
            return

        # 1. Arb
        if sum_prob < ARB_THRESHOLD:
            # Arb EV is (1 - sum_prob) - fees
            profit_margin = 1.0 - sum_prob
            # If margin > 2%, it's good.
            # We skip full Kelly for Arb effectively, just max size allowed or reasonable size
            # Since arb is theoretically 100% win if atomic (it's not here), we stick to fixed or aggressive logic.
            # Let's keep existing logic but just check 'ev' effectively via threshold.
            print(f"[{market.question[:20]}] ARB: {sum_prob:.3f}. Buying Both.")
            self.place_order(token_ids[0], dynamic_max_bet/2, "YES (Arb)")
            self.place_order(token_ids[1], dynamic_max_bet/2, "NO (Arb)")
            self.current_prices[token_ids[0]] = None # Cooldown
            return

        # Risk Engine Helper for Directional
        def check_risk_size(price, win_prob, label):
             ev = calculate_ev(price, win_prob, 1.0 - price, fees=0.015)
             if ev > 0.05:
                 size = kelly_size(balance, ev, price)
                 # Cap at MAX_BET_USD for safety
                 size = min(size, dynamic_max_bet)
                 if size >= 0.50:
                      return size, ev
             return 0.0, 0.0

        # 2. Dump
        if p_yes <= DUMP_THRESHOLD:
            size, ev = check_risk_size(p_yes, 0.85, "YES Dump")
            if size > 0:
                print(f"[{market.question[:20]}] YES Dump: {p_yes:.2f}. EV: {ev:.2f} Size: ${size:.2f}")
                self.place_order(token_ids[0], size, "YES")
                self.current_prices[token_ids[0]] = None
                
        elif p_no <= DUMP_THRESHOLD:
            size, ev = check_risk_size(p_no, 0.85, "NO Dump")
            if size > 0:
                print(f"[{market.question[:20]}] NO Dump: {p_no:.2f}. EV: {ev:.2f} Size: ${size:.2f}")
                self.place_order(token_ids[1], size, "NO")
                self.current_prices[token_ids[1]] = None
            
        # 3. Skew
        elif p_yes >= SKEW_THRESHOLD:
             # Assume Reversion/Momentum? User said "0.80 if price >= SKEW".
             size, ev = check_risk_size(p_yes, 0.80, "YES Skew")
             if size > 0:
                 print(f"[{market.question[:20]}] YES Skew: {p_yes:.2f}. EV: {ev:.2f} Size: ${size:.2f}")
                 self.place_order(token_ids[0], size, "YES")
                 self.current_prices[token_ids[0]] = None
                 
        elif p_no >= SKEW_THRESHOLD:
             size, ev = check_risk_size(p_no, 0.80, "NO Skew")
             if size > 0:
                 print(f"[{market.question[:20]}] NO Skew: {p_no:.2f}. EV: {ev:.2f} Size: ${size:.2f}")
                 self.place_order(token_ids[1], size, "NO")
                 self.current_prices[token_ids[1]] = None

    def place_order(self, token_id, amount_usd, side_label):
        agg_price = 0.999
        size = amount_usd / agg_price
        
        # Check Dry Run
        try:
            if os.path.exists("bot_state.json"):
                with open("bot_state.json", "r") as f:
                    state = json.load(f)
                if state.get("dry_run", True):
                    print(f"  [DRY RUN WS] Would buy {side_label} ${amount_usd}...")
                    return
        except: pass

        if self.dry_run: # Legacy internal dry run
            print(f"  [DRY RUN WS] Buy {side_label} ${amount_usd}...")
            return

        try:
            # Check balance (Strict 3.0 USDC minimum to prevent gas dry-out)
            balance = self.pm.get_usdc_balance()
            if balance < 3.0:
                print(f"  [SAFETY] Low balance (${balance:.2f} < $3.0). Skipping trade.")
                return
                
            order_args = OrderArgs(token_id=token_id, price=agg_price, size=size, side=BUY)
            signed = self.pm.client.create_order(order_args)
            resp = self.pm.client.post_order(signed)
            print(f"  Order Result: {resp}")
            self.last_trade_times[token_id] = time.time()
            self.save_state({
                "last_trade": f"{side_label} @ ${amount_usd} ({datetime.datetime.now().strftime('%H:%M:%S')})",
                "last_trade_status": str(resp)
            })
        except Exception as e:
            print(f"  Order Failed: {e}")
            self.save_state({"last_trade_status": f"Failed: {str(e)}"})

    def save_state(self, update: dict):
        state_file = "scalper_state.json"
        try:
            current = {}
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    current = json.load(f)
            
            # Special handling for prices to merge them
            if "prices" in update and "prices" in current:
                current["prices"].update(update["prices"])
                del update["prices"]
                
            current.update(update)
            # Add API telemetry
            current["scalper_last_activity"] = "Processing WS Feed"
            current["scalper_last_endpoint"] = "WebSocket (CLOB)"
            
            with open(state_file, "w") as f:
                json.dump(current, f)
        except Exception as e:
            pass

    def on_open(self, ws):
        print("WS Connected. Authenticating...")
        try:
            from eth_account.messages import encode_defunct
            ts = int(time.time())
            # Subscriptions API expects EIP712 or personal_sign of the timestamp
            message = encode_defunct(text=str(ts))
            sig = self.pm.web3.eth.account.sign_message(message, private_key=self.pm.private_key).signature.hex()
            
            auth_msg = {
                "type": "auth",
                "api_key": self.pm.credentials.api_key,
                "passphrase": self.pm.credentials.api_passphrase,
                "timestamp": str(ts),
                "sig": sig
            }
            ws.send(json.dumps(auth_msg))
            print("  Auth sent.")
        except Exception as e:
            print(f"  Auth failed: {e}")

        print("Subscribing to book...")
        tids = list(self.tokens_to_market.keys())
        # The subscriptions API expects "market" channel with "assets_ids" for book
        msg = {
            "type": "subscribe",
            "channels": ["book"],
            "assets_ids": tids # Plural "assets_ids" is common in samples, checking.
        }
        ws.send(json.dumps(msg))
        
        # Subscribe to User Fills/Orders
        msg_user = {
            "type": "subscribe",
            "channels": ["user"]
        }
        ws.send(json.dumps(msg_user))
        
        def ping():
            while True:
                time.sleep(20)
                try: ws.send(json.dumps({"type": "ping"}))
                except: break
        threading.Thread(target=ping, daemon=True).start()

    def run(self):
        ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        ws = websocket.WebSocketApp(
            ws_url,
            on_message=self.on_message,
            on_error=lambda ws, e: print(f"WS Error: {e}"),
            on_close=lambda ws, c, m: print("WS Closed"),
            on_open=self.on_open
        )
        ws.run_forever()

if __name__ == "__main__":
    is_live = "--live" in sys.argv
    bot = WS_CryptoScalper(dry_run=not is_live)
    bot.run()
