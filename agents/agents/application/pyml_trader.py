
import os
import time
import ast
import json
import logging
import datetime
import requests
from dotenv import load_dotenv
from typing import List, Dict, Tuple

from agents.polymarket.polymarket import Polymarket
from agents.utils.objects import SimpleMarket
from agents.utils.context import get_context, Position, Trade

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("PyMLBot")

class SafePolymarket(Polymarket):
    def _init_api_keys(self) -> None:
        if self.private_key:
            super()._init_api_keys()
        else:
            logger.warning("No private key found. Running in read-only mode (Gamma API only).")
            self.client = None

    def execute_market_order(self, market, amount):
        if not self.client:
             logger.error("Cannot execute order: No API client (missing private key).")
             return
        return super().execute_market_order(market, amount)

from agents.utils.validator import Validator, SharedConfig
from agents.utils.risk_engine import calculate_ev, kelly_size, check_drawdown

class Scanner:
    """Scans Polymarket for trading opportunities."""
    def __init__(self, pm, config):
        self.pm = pm
        self.config = config
        # Risk Limits
        self.MAX_POSITIONS_PER_USER = 3
        self.min_volume = getattr(config, 'MIN_VOLUME', 1000)
        self.high_prob_threshold = getattr(config, 'HIGH_PROB_THRESHOLD', 0.85)
        
    def get_candidates(self):
        """Returns (high_prob_opportunities, arbitrage_opportunities)"""
        high_prob = []
        arb_opportunities = []
        
        try:
            # Increase limit to 100 to catch more niche Sports markets (mimic 0p0jogggg coverage)
            markets = self.pm.get_all_markets(limit=100, active=True)
            tradeable = self.pm.filter_markets_for_trading(markets)
            
            for market in tradeable:
                # Skip low volume markets
                if market.volume < self.min_volume:
                    continue
                    
                try:
                    # Parse prices
                    import ast
                    prices_str = market.outcome_prices
                    prices = ast.literal_eval(prices_str) if prices_str else []
                    if len(prices) < 2:
                        continue
                    
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
                    
                    # High probability opportunities (outcome likely to win)
                    if yes_price >= self.high_prob_threshold:
                        high_prob.append({
                            'market': market,
                            'outcome': 'Yes',
                            'price': yes_price
                        })
                    elif no_price >= self.high_prob_threshold:
                        high_prob.append({
                            'market': market,
                            'outcome': 'No',
                            'price': no_price
                        })
                    
                    # Arbitrage check: if sum of prices < 1.0 or > 1.0
                    price_sum = yes_price + no_price
                    
                    # SAFETY: Exclude "Up or Down" crypto markets (3% fee kills this arb)
                    is_crypto_fee_market = "Up or Down" in market.question or "Above" in market.question
                    
                    if price_sum < 0.98 and not is_crypto_fee_market:  
                        arb_opportunities.append({
                            'market': market,
                            'sum_price': price_sum,
                            'yes_price': yes_price,
                            'no_price': no_price
                        })
                        
                except Exception as e:
                    logger.debug(f"Error parsing market {market.question[:30]}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Scanner error: {e}")
            
        return high_prob, arb_opportunities

class Config(SharedConfig):
   pass

class Bot:
    AGENT_NAME = "safe"
    
    def __init__(self):
        self.config = Config()
        self.pm = SafePolymarket()
        self.scanner = Scanner(self.pm, self.config)
        self.validator = Validator(self.config, agent_name=self.AGENT_NAME)
        self.context = get_context()  # Shared context
        self.initial_balance = 0.0
        try:
             self.initial_balance = self.pm.get_usdc_balance()
             self.context.update_balance(self.initial_balance)
             logger.info(f"Initial Balance: ${self.initial_balance:.2f}")
        except: pass
        
    def run(self, dry_run=False):
        logger.info(f"Starting Bot (Dry Run: {dry_run})")
        
        # Check and fix allowance
        if not dry_run:
            try:
                allowance = self.pm.get_usdc_allowance()
                if allowance < 500:
                    logger.info(f"USDC allowance {allowance} < 500. Approving trading...")
                    self.pm.approve_trading()
                else:
                    logger.info("USDC Trading Approved.")
            except Exception as e:
                logger.error(f"Allowance check/approval failed: {e}")

        # Initialize Auto-Redeemer for Compounding
        redeemer = None
        try:
            from agents.utils.auto_redeem import AutoRedeemer
            redeemer = AutoRedeemer()
            logger.info("✅ Auto-Redeemer initialized for compounding.")
        except ImportError:
            logger.warning("AutoRedeemer not found. Manual redemption required.")
        except Exception as e:
            logger.error(f"AutoRedeemer init failed: {e}")

        # State check helper
        def check_run_state():
            try:
                if os.path.exists("bot_state.json"):
                    with open("bot_state.json", "r") as f:
                        state = json.load(f)
                    return state.get("safe_running", True), state.get("dry_run", True)
            except: 
                pass
            return True, True

        def record_activity(action, endpoint="Gamma"):
            try:
                state = {}
                if os.path.exists("bot_state.json"):
                    with open("bot_state.json", "r") as f:
                        state = json.load(f)
                state["safe_last_activity"] = f"{action} ({datetime.datetime.now().strftime('%H:%M:%S')})"
                state["safe_last_endpoint"] = endpoint
                
                # atomic-ish write
                with open("bot_state.json", "w") as f:
                    json.dump(state, f)
            except: pass
                
        while True:
            # Check pause state
            is_running, is_dry_run = check_run_state()
            if not is_running:
                logger.info("Bot Paused via Dashboard. Sleeping 60s...")
                time.sleep(60)
                continue

            try:
                # 1. Auto-Redeem Winning Positions (Compounding)
                if redeemer and not is_dry_run:
                    try:
                        res = redeemer.scan_and_redeem()
                        if res['redeemed'] > 0:
                            msg = f"💰 Compounding: Redeemed {res['redeemed']} positions"
                            logger.info(msg)
                            record_activity(msg, "Polygon RPC")
                            time.sleep(2) # Let user see it
                    except Exception as e:
                        logger.error(f"Redemption failed: {e}")

                high_prob, arb = self.scanner.get_candidates()
                record_activity("Scanning Markets", "Gamma API")
                logger.info(f"Found {len(high_prob)} high-prob, {len(arb)} arb opportunities.")
                
                # Get current balance for risk checks
                balance = self.initial_balance
                try:
                    balance = self.pm.get_usdc_balance()
                except:
                    pass
                
                # Process High Prob
                for opp in high_prob:
                    market = opp['market']
                    
                    # === CONTEXT CHECK: Can we trade this? ===
                    can_trade, ctx_reason = self.context.can_trade(
                        self.AGENT_NAME, market.id, 1.0, balance
                    )
                    if not can_trade:
                        logger.info(f"Skipping {market.question[:30]}... - {ctx_reason}")
                        continue
                    
                    self.context.update_agent_status(self.AGENT_NAME, f"Analyzing: {market.question[:25]}...")
                    
                    logger.info(f"Analyzing {market.question} - {opp['outcome']} @ {opp['price']}")
                    is_valid, reason, conf = self.validator.validate(market.question, opp['outcome'], opp['price'])
                    record_activity(f"Validating {market.question[:10]}...", "Perplexity API")
                    
                    if is_valid:
                        # Risk Engine Check
                        
                        if not check_drawdown(self.initial_balance, balance):
                              logger.warning("Drawdown limit hit! Skipping trade.")
                              continue

                        potential_profit = 1.0 - opp['price']
                        ev = calculate_ev(opp['price'], conf, potential_profit, fees=0.02)
                        
                        if ev > 0.05: # Min 5% EV
                            bet_size = kelly_size(balance, ev, opp['price'])
                            
                            # Min viable bet check (kelly_size function handles floor logic now, just check > 0)
                            if bet_size > 0:
                                logger.info(f"Strong Opportunity! EV: {ev:.2f} | Size: ${bet_size:.2f}")
                                
                                self.save_state({
                                    "last_decision": f"BET: {opp['market'].question[:50]}...",
                                    "confidence": conf,
                                    "reason": reason,
                                    "ev": ev,
                                    "kelly_size": bet_size
                                })
                                
                                if not dry_run and not is_dry_run:
                                    # Check Dynamic Config for Cap
                                    dynamic_max = 0.50 # Default
                                    try:
                                        if os.path.exists("bot_state.json"):
                                            with open("bot_state.json", "r") as f:
                                                state = json.load(f)
                                            dynamic_max = float(state.get("dynamic_max_bet", 0.50))
                                    except: pass
                                    
                                    bet_size = min(bet_size, dynamic_max)
                                    
                                    logger.info(f"Executing Trade Size: ${bet_size:.2f}...")
                                    self.execute_trade(opp, amount_usd=bet_size)
                                else:
                                    logger.info(f"Dry Run (Global: {is_dry_run}, Local: {dry_run}): Would trade ${bet_size:.2f}.")
                            else:
                                 logger.info(f"Kelly size ${bet_size:.2f} too small (or 0). Skipping.")
                        else:
                             # logger.info(f"EV too low ({ev:.2f}). Skipping.") # Reduce noise
                             pass
                    else:
                        self.save_state({
                            "last_decision": f"PASS: {opp['market'].question[:50]}...",
                            "confidence": conf,
                            "reason": reason
                        })
                        logger.info(f"Skipped: {reason}")
                
                # Process Arb
                for opp in arb:
                     logger.info(f"Arb Opportunity: {opp['market'].question} (Sum: {opp['sum_price']})")
                     if not dry_run:
                         pass # Implement Arb execution
                     else:
                         logger.info("Dry Run: Would arb.")

                self.save_state({
                    "last_scan": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "high_prob_count": len(high_prob),
                    "arb_count": len(arb),
                    "status": "Scanning Complete"
                })
                logger.info("Sleeping for 60 seconds (Safe Scan Interval)...")
                time.sleep(60)
                
            except KeyboardInterrupt:
                logger.info("Stopping Bot.")
                break
            except Exception as e:
                logger.error(f"Main Loop Error: {e}")
                self.save_state({"status": f"Error: {str(e)}"})
                time.sleep(60)

    def save_state(self, update: Dict):
        state_file = "safe_state.json"
        try:
            current = {}
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    current = json.load(f)
            current.update(update)
            with open(state_file, "w") as f:
                json.dump(current, f)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def execute_trade(self, opportunity, amount_usd=None):
        """Execute a trade based on the validated opportunity"""
        try:
            market = opportunity['market']
            outcome = opportunity['outcome']  # "Yes" or "No"
            price = opportunity['price']
            
            # Get token ID for the outcome
            token_ids = ast.literal_eval(market.clob_token_ids)
            token_id = token_ids[0] if outcome.lower() == "yes" else token_ids[1]
            
            # Calculate size
            if amount_usd:
                 bet_amount = amount_usd # Use Risk Engine Size
            else:
                 # Fallback - Check Dynamic Config
                 dynamic_max_bet = float(os.getenv("MAX_BET_USD", "0.50"))
                 try:
                     if os.path.exists("bot_state.json"):
                         with open("bot_state.json", "r") as f:
                             state = json.load(f)
                         dynamic_max_bet = float(state.get("dynamic_max_bet", dynamic_max_bet))
                 except: pass
                 
                 bet_amount = min(dynamic_max_bet, 0.50)  

                 
            size = bet_amount / price
            
            # Check balance (Strict 3.0 USDC + Gas Buffer)
            balance = self.pm.get_usdc_balance()
            if balance < 3.0:
                 logger.warning(f"Balance too low for safe trading: ${balance:.2f} < $3.00")
                 return

            logger.info(f"Executing Trade: {outcome} on '{market.question[:40]}...' @ ${bet_amount}")
            
            # === SNIPER MODE (Limit Orders) ===
            # Instead of market buy, we place a LIMIT buy to control price
            # Target = Current Market Price (or slightly lower to catch dips)
            limit_price = round(price, 2) 
            
            # Safety: Ensure we don't bid > 98c
            limit_price = min(limit_price, 0.98)
            
            # Calculate exact shares for this limit price
            size_shares = bet_amount / limit_price
            
            logger.info(f"   🔫 SNIPING: Limit Buy {size_shares:.1f} shares @ ${limit_price:.2f}")
            
            result = self.pm.place_limit_order(
                token_id=token_id,
                price=limit_price,
                size=size_shares,
                side="BUY"
            )
            
            logger.info(f"Order Result: {result}")
            
            # === RECORD IN SHARED CONTEXT ===
            self.context.add_position(Position(
                market_id=market.id,
                market_question=market.question,
                agent=self.AGENT_NAME,
                outcome=outcome,
                entry_price=price,
                size_usd=bet_amount,
                timestamp=datetime.datetime.now().isoformat(),
                token_id=token_id
            ))
            self.context.add_trade(Trade(
                market_id=market.id,
                agent=self.AGENT_NAME,
                outcome=outcome,
                size_usd=bet_amount,
                price=price,
                timestamp=datetime.datetime.now().isoformat(),
                status="filled"
            ))
            
            # Broadcast to other agents
            self.context.broadcast(
                self.AGENT_NAME,
                f"Opened position: {outcome} on {market.question[:30]}",
                {"market_id": market.id, "price": price, "size": bet_amount}
            )
            
            self.save_state({
                "last_trade": f"{outcome} @ ${bet_amount} on '{market.question[:30]}...'",
                "last_trade_result": str(result),
                "last_trade_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
        except Exception as e:
            logger.error(f"Trade Execution Failed: {e}")
            self.context.add_trade(Trade(
                market_id=market.id,
                agent=self.AGENT_NAME,
                outcome=outcome,
                size_usd=bet_amount,
                price=price,
                timestamp=datetime.datetime.now().isoformat(),
                status="failed"
            ))
            self.save_state({"last_trade_error": str(e)})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Run without executing trades")
    args = parser.parse_args()
    
    bot = Bot()
    bot.run(dry_run=args.dry_run)
