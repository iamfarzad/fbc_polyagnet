import os
import time
import json
import logging
import datetime
import requests
import ast
from typing import List, Dict
from dotenv import load_dotenv
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY

from agents.polymarket.polymarket import Polymarket
from agents.utils.validator import Validator, SharedConfig

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("copy_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("CopyBot")


class CopyConfig(SharedConfig):
    pass


class CopyTrader:
    def __init__(self):
        self.config = CopyConfig()
        self.pm = Polymarket()
        self.validator = Validator(self.config)
        self.state_file = "copy_state.json"
        self.DATA_API_URL = "https://data-api.polymarket.com"
        self.MAX_POSITIONS_PER_USER = 3
        self.initial_balance = 0.0
        try:
            self.initial_balance = self.pm.get_usdc_balance()
            logger.info(f"Initial Balance: ${self.initial_balance:.2f}")
        except:
            pass
        
    def fetch_top_gainers(self, limit=10, period="24h"):
        """
        Fetch top traders using LLM research.
        
        The LLM searches for recent news, Twitter, and leaderboard mentions
        to discover profitable trader addresses dynamically.
        
        Falls back to a static list if LLM fails.
        """
        # Use LLM to discover traders
        traders = self.validator.discover_top_traders()
        
        if traders:
            logger.info(f"LLM discovered {len(traders)} top traders")
            # Convert to expected format
            return [{"address": t["address"], "name": t.get("name", "Unknown")} for t in traders[:limit]]
        
        # Fallback: known whale addresses (manually updated periodically)
        logger.warning("LLM discovery failed, using fallback whale list")
        fallback_whales = [
            {"address": "0x6a72f61820b26b1fe4d956e17b6dc2a1ea3033ee", "name": "kch123"},
            {"address": "0x16b29c50f2439faf627209b2ac0c7bbddaa8a881", "name": "SeriouslySirius"},
            {"address": "0xdb27bf2ac5d428a9c63dbc914611036855a6c56e", "name": "DrPufferfish"},
            {"address": "0x37e4728b3c4607fb2b3b205386bb1d1fb1a8c991", "name": "SemyonMarmeladov"},
            {"address": "0x507e52ef684ca2dd91f90a9d26d149dd3288beae", "name": "GamblingIsAllYouNeed"},
            {"address": "0x204f72f35326db932158cba6adff0b9a1da95e14", "name": "swisstony"},
            {"address": "0xe90bec87d9ef430f27f9dcfe72c34b76967d5da2", "name": "gmanas"},
        ]
        return fallback_whales[:limit]

    def fetch_user_positions(self, address):
        """Fetch active positions for a user"""
        try:
            url = f"{self.DATA_API_URL}/positions?user={address}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            logger.error(f"Fetch Positions Error: {e}")
            return []

    def save_state(self, update: Dict):
        try:
            current = {}
            if os.path.exists(self.state_file):
                with open(self.state_file, "r") as f:
                    current = json.load(f)
            current.update(update)
            with open(self.state_file, "w") as f:
                json.dump(current, f)
        except:
            pass

    def check_run_state(self):
        try:
            if os.path.exists("bot_state.json"):
                with open("bot_state.json", "r") as f:
                    state = json.load(f)
                return state.get("copy_trader_running", False), state.get("dry_run", True)
        except:
            pass
        return False, True

    def get_dynamic_max_bet(self) -> float:
        """Read dynamic max bet from bot_state.json"""
        try:
            if os.path.exists("bot_state.json"):
                with open("bot_state.json", "r") as f:
                    state = json.load(f)
                return float(state.get("dynamic_max_bet", 5.0))
        except:
            pass
        return 5.0

    def execute_trade(self, token_id: str, amount_usd: float, outcome: str):
        """Execute a copy trade using CLOB API"""
        try:
            balance = self.pm.get_usdc_balance()
            if balance < 3.0:
                logger.warning(f"Low balance (${balance:.2f} < $3.0). Skipping trade.")
                return None
            
            # Aggressive price to ensure fill
            agg_price = 0.999
            size = amount_usd / agg_price
            
            order_args = OrderArgs(
                token_id=token_id,
                price=agg_price,
                size=size,
                side=BUY
            )
            
            signed = self.pm.client.create_order(order_args)
            resp = self.pm.client.post_order(signed)
            
            logger.info(f"Order Executed: {outcome} ${amount_usd} -> {resp}")
            self.save_state({
                "last_trade": f"{outcome} @ ${amount_usd} ({datetime.datetime.now().strftime('%H:%M:%S')})",
                "last_trade_result": str(resp)
            })
            return resp
            
        except Exception as e:
            logger.error(f"Trade Execution Failed: {e}")
            self.save_state({"last_trade_error": str(e)})
            return None

    def run(self):
        logger.info("Starting Copy Trader...")
        
        while True:
            is_running, is_dry_run = self.check_run_state()
            if not is_running:
                logger.info("Copy Trader Paused. Sleeping 60s...")
                time.sleep(60)
                continue

            try:
                gainers = self.fetch_top_gainers(limit=5)
                logger.info(f"Scanning {len(gainers)} top gainers...")
                
                for user in gainers:
                    address = user.get("address")
                    if not address:
                        continue
                    
                    positions = self.fetch_user_positions(address)
                    logger.info(f"User {address[:6]}... has {len(positions)} positions.")
                    
                    for pos in positions[:self.MAX_POSITIONS_PER_USER]:
                        question = pos.get("title", pos.get("question"))
                        outcome = pos.get("outcome")
                        price = float(pos.get("price", pos.get("currentPrice", 0)))
                        token_id = pos.get("asset_id", pos.get("tokenId"))
                        
                        if not question or not outcome or price <= 0:
                            continue
                        
                        # Skip extreme odds
                        if price > 0.95 or price < 0.05:
                            continue
                        
                        context = f"This position is held by a top gainer on the 24h leaderboard (User: {address[:6]})."
                        is_valid, reason, conf = self.validator.validate(question, outcome, price, additional_context=context)
                        
                        if is_valid:
                            logger.info(f"COPY SIGNAL: {question} ({outcome}) @ {price}")
                            self.save_state({"last_signal": f"COPY {outcome}: {question[:30]}..."})
                             
                            if not is_dry_run:
                                if token_id:
                                    max_bet = self.get_dynamic_max_bet()
                                    self.execute_trade(token_id, max_bet, outcome)
                                else:
                                    logger.warning("No Token ID found in position data.")
                            else:
                                logger.info("[DRY RUN] Would Copy Trade.")
                        
                self.save_state({
                    "last_scan": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "Scanning Complete"
                })
                
                time.sleep(300)
                
            except Exception as e:
                logger.error(f"Copy Loop Error: {e}")
                time.sleep(60)


if __name__ == "__main__":
    bot = CopyTrader()
    bot.run()
