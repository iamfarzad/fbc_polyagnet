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
from agents.utils.context import get_context, Position, Trade
from agents.utils.config import load_config
from agents.application.smart_context import SmartContext

# Import Supabase state manager
try:
    from agents.utils.supabase_client import get_supabase_state
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    get_supabase_state = None

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
    AGENT_NAME = "copy"
    
    AGENT_NAME = "copy"
    
    def __init__(self):
        self.config = load_config("copy_trader")
        self.pm = Polymarket()
        self.validator = Validator(SharedConfig(), "copy_trader")
        self.smart_context = SmartContext()
        self.pm = Polymarket()
        self.validator = Validator(self.config, agent_name=self.AGENT_NAME)
        
        # Robust Context Import
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

        self.state_file = "copy_state.json"
        self.DATA_API_URL = "https://data-api.polymarket.com"
        self.MAX_POSITIONS_PER_USER = 3
        self.initial_balance = 0.0
        try:
            self.initial_balance = self.pm.get_usdc_balance()
            self.context.update_balance(self.initial_balance)
            logger.info(f"Initial Balance: ${self.initial_balance:.2f}")
        except:
            pass
        
        # Initialize Auto-Redeemer for Compounding
        self.redeemer = None
        try:
            from agents.utils.auto_redeem import AutoRedeemer
            self.redeemer = AutoRedeemer()
            logger.info("✅ Auto-Redeemer initialized for compounding.")
        except Exception as e:
            logger.warning(f"AutoRedeemer init failed: {e}")

        # Self-Learning State
        self.last_learning_time = 0
        self.LEARNING_INTERVAL = 3600 * 4  # Run analysis every 4 hours

    def run_learning_cycle(self):
        """Run post-trade analysis to learn from mistakes."""
        # Late import to avoid circular dependencies if any
        try:
            from agents.utils.mistake_analyzer import MistakeAnalyzer
            analyzer = MistakeAnalyzer(agent_name=self.AGENT_NAME) 
        except ImportError:
            return

        now = time.time()
        if now - self.last_learning_time > self.LEARNING_INTERVAL:
            try:
                logger.info("🧠 Starting Self-Learning Cycle...")
                lessons = analyzer.analyze_completed_trades(limit=5)
                if lessons:
                    logger.info(f"🎓 Learned {len(lessons)} new lessons from recent trades.")
                else:
                    logger.info("🧠 No new lessons to learn this cycle.")
                self.last_learning_time = now
            except Exception as e:
                logger.warning(f"Self-learning cycle failed: {e}")
        
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
        # 1. Try Supabase
        if HAS_SUPABASE:
            try:
                supa = get_supabase_state()
                if supa:
                     is_running = supa.is_agent_running("copy")
                     # dry_run = supa.get_global_dry_run() # Optional
                     
                     # If we successfully got state from Supabase, return it
                     # But we need to grab local dry_run or assume true if not in supa yet
                     return is_running, True # Default dry run to True if Supabase doesn't have it explicitly mapped
            except Exception as e:
                pass

        # 2. Local Fallback
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
        # SECURITY OVERRIDE: Hard cap at $5.00
        return 5.0

    def execute_trade(self, token_id: str, amount_usd: float, outcome: str, market_id: str = "", question: str = ""):
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
            
            # Log to Dashboard
            if self.context and self.LLMActivity:
                try:
                    import uuid
                    self.context.log_llm_activity(self.LLMActivity(
                        id=str(uuid.uuid4())[:8],
                        agent=self.AGENT_NAME,
                        timestamp=datetime.datetime.now().isoformat(),
                        action_type="COPY_EXECUTE",
                        market_question=question,
                        prompt_summary=f"Copying {outcome} on {question[:30]}",
                        reasoning=f"Copied trade from top gainer. Amount: ${amount_usd}",
                        conclusion="EXECUTED",
                        confidence=1.0,
                        data_sources=["Polymarket Leaderboard"],
                        duration_ms=0
                    ))
                except: pass

            
            # === RECORD IN SHARED CONTEXT ===
            self.context.add_position(Position(
                market_id=market_id or token_id,
                market_question=question or "Copy Trade",
                agent=self.AGENT_NAME,
                outcome=outcome,
                entry_price=agg_price,
                size_usd=amount_usd,
                timestamp=datetime.datetime.now().isoformat(),
                token_id=token_id
            ))
            self.context.add_trade(Trade(
                market_id=market_id or token_id,
                agent=self.AGENT_NAME,
                outcome=outcome,
                size_usd=amount_usd,
                price=agg_price,
                timestamp=datetime.datetime.now().isoformat(),
                status="filled"
            ))
            
            self.save_state({
                "last_trade": f"{outcome} @ ${amount_usd} ({datetime.datetime.now().strftime('%H:%M:%S')})",
                "last_trade_result": str(resp)
            })
            return resp
            
        except Exception as e:
            logger.error(f"Trade Execution Failed: {e}")
            self.context.add_trade(Trade(
                market_id=market_id or token_id,
                agent=self.AGENT_NAME,
                outcome=outcome,
                size_usd=amount_usd,
                price=0,
                timestamp=datetime.datetime.now().isoformat(),
                status="failed"
            ))
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
                # 0. Auto-Redeem Winning Positions (Compounding)
                if self.redeemer:
                    try:
                        res = self.redeemer.scan_and_redeem()
                        if res['redeemed'] > 0:
                            logger.info(f"💰 CopyCompounding: Redeemed {res['redeemed']} positions")
                            self.save_state({"last_activity": "Redeemed positions"})
                    except: pass
                
                # Randomized delay to mask bot behavior (The Shadow)
                import random
                delay = random.uniform(5, 15)
                time.sleep(delay)

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
                        market_id = pos.get("market_id", pos.get("conditionId", token_id))
                        
                        if not question or not outcome or price <= 0:
                            continue
                        
                        # Skip extreme odds
                        if price > 0.95 or price < 0.05:
                            continue
                        
                        # === ENHANCED GAP FIX: 2h Window + Slippage Protection ===
                        pos_timestamp = pos.get("timestamp", pos.get("createdAt", ""))
                        if pos_timestamp:
                            try:
                                # Normalize to UTC
                                if "Z" in pos_timestamp:
                                     # pos_timestamp is ISO 8601 with Z
                                     pos_time = datetime.datetime.fromisoformat(pos_timestamp.replace("Z", "+00:00"))
                                else:
                                     pos_time = datetime.datetime.fromisoformat(pos_timestamp)
                                     if pos_time.tzinfo is None:
                                         pos_time = pos_time.replace(tzinfo=datetime.timezone.utc)

                                # Narrowed from 24h to 2h
                                if datetime.datetime.now(datetime.timezone.utc) - pos_time > datetime.timedelta(hours=2):
                                    logger.info(f"Skipping stale position (>2h): {question[:30]}")
                                    continue
                                    
                                # Slippage Check
                                current_market_price = float(pos.get("currentPrice", 0))
                                whale_entry_price = float(pos.get("price", 0))
                                if current_market_price > (whale_entry_price * 1.05):
                                    logger.info(f"Skipping: Price moved too much ({whale_entry_price} -> {current_market_price})")
                                    continue
                                    
                            except Exception as e:
                                logger.debug(f"Timestamp check error: {e}")
                        
                        # === CONTEXT CHECK: Can we trade this market? ===
                        balance = self.initial_balance
                        try:
                            balance = self.pm.get_usdc_balance()
                        except:
                            pass
                        
                        max_bet = self.get_dynamic_max_bet()
                        can_trade, ctx_reason = self.context.can_trade(
                            self.AGENT_NAME, market_id, max_bet, balance
                        )
                        if not can_trade:
                            logger.info(f"Skipping {question[:30]}... - {ctx_reason}")
                            continue
                        
                        self.context.update_agent_status(self.AGENT_NAME, f"Analyzing: {question[:25]}...")
                        
                        ctx_info = f"This position is held by a top gainer on the 24h leaderboard (User: {address[:6]})."
                        is_valid, reason, conf = self.validator.validate(question, outcome, price, additional_context=ctx_info)
                        
                        if is_valid:
                            # FADE LOGIC: Check if we want to bet against the whale
                            fade_mode = self.config.get("fade_mode", False)
                            final_outcome = outcome
                            final_reasoning = f"Copied trade from {address[:6]}."

                            if fade_mode:
                                final_outcome = "No" if outcome == "Yes" else "Yes"
                                final_reasoning = f"FADING trade from {address[:6]} (Whale is wrong)."
                                logger.info(f"🔄 FADE MODE: Switching {outcome} -> {final_outcome}")

                            logger.info(f"SIGNAL: {question} ({final_outcome}) @ {price}")
                            self.save_state({"last_signal": f"{'FADE' if fade_mode else 'COPY'} {final_outcome}: {question[:30]}..."})
                             
                            if not is_dry_run:
                                if token_id:
                                    # If fading, we need the token ID for the OPPOSITE outcome
                                    # This requires a lookup, for now we assume 'token_id' passed is correct for the logic
                                    # TODO: Fix token ID for fading (requires market lookup)
                                    # For MVP: Only support direct copy or simplified fade if IDs available
                                    
                                    # Simple Hack: We can't easily swap token_id without full market data
                                    # So if fading, we skip for now OR we accept we need to fetch the other token
                                    if fade_mode:
                                        logger.warning("Fade mode requires market lookup for opposite token. Skipping execution for safety.")
                                        continue
                                    
                                    result = self.execute_trade(token_id, max_bet, final_outcome, market_id, question)
                                    if result:
                                        self.context.broadcast(
                                            self.AGENT_NAME,
                                            f"{'Faded' if fade_mode else 'Copied'} trade: {final_outcome} on {question[:30]}",
                                            {"market_id": market_id, "whale": address[:10], "price": price}
                                        )
                                else:
                                    logger.warning("No Token ID found.")
                            else:
                                logger.info(f"[DRY RUN] Would {'Fade' if fade_mode else 'Copy'} Trade: {final_outcome}")
                        
                self.save_state({
                    "last_scan": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "Scanning Complete"
                })
                
                # Self-Learning Cycle
                self.run_learning_cycle()

                logger.info("Sleeping 60s before next scan...")
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"Copy Loop Error: {e}")
                time.sleep(60)


if __name__ == "__main__":
    import sys
    # Copy trader reads dry_run from bot_state.json
    # --live flag can force live mode by temporarily setting it
    if "--live" in sys.argv:
        import json
        try:
            state = {}
            if os.path.exists("bot_state.json"):
                with open("bot_state.json", "r") as f:
                    state = json.load(f)
            state["dry_run"] = False
            state["copy_trader_running"] = True
            with open("bot_state.json", "w") as f:
                json.dump(state, f)
        except:
            pass
    
    bot = CopyTrader()
    bot.run()
