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
        
        print(f"WS Agent 2 Initialized. Dry Run: {self.dry_run}")
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

            # Check for book updates (delivered as list of events)
            if isinstance(data, list):
                for item in data:
                    if item.get("event_type") == "book":
                        tid = item.get("asset_id")
                        if tid in self.tokens_to_market:
                            bids = item.get("bids", [])
                            asks = item.get("asks", [])
                            if bids and asks:
                                best_bid = float(bids[0]['price'])
                                best_ask = float(asks[0]['price'])
                                mid = (best_bid + best_ask) / 2
                                self.current_prices[tid] = mid
                                self.check_opportunity(tid)
                                # Throttled state save (every message might be too much, but for 4 assets it's okay)
                                self.save_state({
                                    "prices": {self.active_markets[m_id].question[:10]: mid for m_id, m in self.active_markets.items() if m.clob_token_ids and tid in ast.literal_eval(m.clob_token_ids)},
                                    "last_update": datetime.datetime.now().strftime("%H:%M:%S")
                                })
        except Exception as e:
            # print(f"Msg error: {e}")
            pass

    def check_opportunity(self, token_id):
        m_id = self.tokens_to_market.get(token_id)
        market = self.active_markets.get(m_id)
        if not market: return
            
        token_ids = ast.literal_eval(market.clob_token_ids)
        p_yes = self.current_prices.get(token_ids[0])
        p_no = self.current_prices.get(token_ids[1])
        
        if p_yes is None or p_no is None: return

        sum_prob = p_yes + p_no
        
        # Throttled logging (only if significant change or period?)
        # For scalping, we just check logic:
        
        # 1. Arb
        if sum_prob < ARB_THRESHOLD:
            print(f"[{market.question[:20]}] ARB: {sum_prob:.3f}. Buying Both.")
            self.place_order(token_ids[0], MAX_BET_USD/2, "YES (Arb)")
            self.place_order(token_ids[1], MAX_BET_USD/2, "NO (Arb)")
            self.current_prices[token_ids[0]] = None # Cooldown
            return

        # 2. Dump
        if p_yes <= DUMP_THRESHOLD:
            print(f"[{market.question[:20]}] YES Dump: {p_yes:.2f}. Buying YES.")
            self.place_order(token_ids[0], MAX_BET_USD, "YES")
            self.current_prices[token_ids[0]] = None
        elif p_no <= DUMP_THRESHOLD:
            print(f"[{market.question[:20]}] NO Dump: {p_no:.2f}. Buying NO.")
            self.place_order(token_ids[1], MAX_BET_USD, "NO")
            self.current_prices[token_ids[1]] = None
            
        # 3. Skew
        elif p_yes >= SKEW_THRESHOLD:
            print(f"[{market.question[:20]}] YES Skew: {p_yes:.2f}. Buying YES.")
            self.place_order(token_ids[0], MAX_BET_USD, "YES")
            self.current_prices[token_ids[0]] = None
        elif p_no >= SKEW_THRESHOLD:
            print(f"[{market.question[:20]}] NO Skew: {p_no:.2f}. Buying NO.")
            self.place_order(token_ids[1], MAX_BET_USD, "NO")
            self.current_prices[token_ids[1]] = None

    def place_order(self, token_id, amount_usd, side_label):
        agg_price = 0.999
        size = amount_usd / agg_price
        if self.dry_run:
            print(f"  [DRY RUN WS] Buy {side_label} ${amount_usd}...")
            return

        try:
            # Check balance
            balance = self.pm.get_usdc_balance()
            if balance < amount_usd + 1:
                print("  Low balance, skipping.")
                return
                
            order_args = OrderArgs(token_id=token_id, price=agg_price, size=size, side=BUY)
            signed = self.pm.client.create_order(order_args)
            resp = self.pm.client.post_order(signed)
            print(f"  Order Result: {resp}")
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
