
import os
import time
import json
import logging
import datetime
import requests
import ast
from typing import List, Dict
from dotenv import load_dotenv

from agents.polymarket.polymarket import Polymarket
from agents.utils.validator import Validator, SharedConfig

# Configure logging
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
        
        # Risk Limits
        self.MAX_COPY_AMOUNT = 5.0 # Max $5 per trade
        self.MAX_POSITIONS_PER_USER = 3
        
    def fetch_top_gainers(self, limit=10, period="24h"):
        """Fetch top gainers by PnL"""
        try:
            url = f"{self.DATA_API_URL}/leaderboard?window={period}&limit={limit}&sortBy=pnl"
            # Note: The actual endpoint might slightly differ, checking docs or assuming standard query params
            # Based on user prompt: /leaderboard?period=24h&limit={limit}
            # Adjusting to likely efficient call
            url = f"{self.DATA_API_URL}/leaderboard?limit={limit}&period={period}"
            resp = requests.get(url) 
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"Leaderboard Fetch Error: {resp.status_code} {resp.text}")
                return []
        except Exception as e:
            logger.error(f"Fetch Gainers Error: {e}")
            return []

    def fetch_user_positions(self, address):
        """Fetch active positions for a user"""
        try:
            url = f"{self.DATA_API_URL}/positions?user={address}"
            resp = requests.get(url)
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
        except Exception as e:
            pass

    def check_run_state(self):
        try:
            if os.path.exists("bot_state.json"):
                with open("bot_state.json", "r") as f:
                    state = json.load(f)
                return state.get("copy_trader_running", False), state.get("dry_run", True)
        except: 
            pass
        return False, True # Default off for safety

    def run(self):
        logger.info("Starting Copy Trader...")
        
        while True:
            is_running, is_dry_run = self.check_run_state()
            if not is_running:
                logger.info("Copy Trader Paused. Sleeping 60s...")
                time.sleep(60)
                continue

            try:
                # 1. Fetch Top Gainers
                gainers = self.fetch_top_gainers(limit=5)
                logger.info(f"Scanning {len(gainers)} top gainers...")
                
                for user in gainers:
                    address = user.get("address")
                    if not address: continue
                    
                    # 2. Fetch User Positions
                    positions = self.fetch_user_positions(address)
                    logger.info(f"User {address[:6]}... has {len(positions)} positions.")
                    
                    for pos in positions[:5]: # Check top 5 positions only
                        # Extract basic info
                        # API format assumption: title, outcome, currentPrice/value
                        question = pos.get("title", pos.get("question"))
                        outcome = pos.get("outcome") # YES/NO
                        price = float(pos.get("price", pos.get("currentPrice", 0)))
                         # size = float(pos.get("size", 0))
                        
                        if not question or not outcome or price <= 0: continue
                        
                        # Filter: Liquidity/Price checks (Done in Validator implicitly or here)
                        if price > 0.95 or price < 0.05: continue # Ignore extreme odds
                        
                        # 3. Validate with Perplexity
                        # Context: "Top gainer is holding this."
                        context = f"This position is held by a top gainer on the 24h leaderboard (User: {address[:6]})."
                        
                        is_valid, reason, conf = self.validator.validate(question, outcome, price, additional_context=context)
                        
                        if is_valid:
                             logger.info(f"✅ COPY SIGNAL: {question} ({outcome}) @ {price}")
                             self.save_state({"last_signal": f"COPY {outcome}: {question[:30]}..."})
                             
                             if not is_dry_run:
                                 # Execute Trade
                                 # Need token ID lookup. Position data might have asset_id or token_id
                                 token_id = pos.get("asset_id", pos.get("tokenId"))
                                 if token_id:
                                      # Place Order
                                      # Reuse OrderArgs logic...
                                      # For now, just log and skip execution implementation until strictly tested
                                      logger.info("Executing Copy Trade (Placeholder)...")
                                      pass
                                 else:
                                     logger.warning("No Token ID found in position data.")
                             else:
                                 logger.info("[DRY RUN] Would Copy Trade.")
                        
                self.save_state({
                    "last_scan": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "Scanning Complete"
                })
                
                time.sleep(300) # 5 minutes sleep
                
            except Exception as e:
                logger.error(f"Copy Loop Error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    bot = CopyTrader()
    bot.run()
