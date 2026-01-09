
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

class Config:
    def __init__(self):
        load_dotenv()
        self.MIN_PROB = float(os.getenv("MIN_PROB", "0.90"))
        self.MAX_EXPOSURE = float(os.getenv("MAX_EXPOSURE", "0.25"))
        self.PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
        self.POLYGON_WALLET_PRIVATE_KEY = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
        
        if not self.PERPLEXITY_API_KEY:
            logger.warning("No PERPLEXITY_API_KEY found. Validation will be skipped.")
        
        if not self.POLYGON_WALLET_PRIVATE_KEY:
            logger.error("No POLYGON_WALLET_PRIVATE_KEY found. Trading will fail.")

import datetime

class Scanner:
    def __init__(self, polymarket: Polymarket, config: Config):
        self.pm = polymarket
        self.config = config

    def get_candidates(self) -> Tuple[List[Dict], List[Dict]]:
        """
        Scans for High Probability and Arbitrage opportunities.
        Returns: (high_prob_markets, arb_markets)
        """
        logger.info("Fetching markets...")
        try:
            # Added archived=false per user suggestion
            markets = self.pm.get_all_markets(limit=1000, active="true", closed="false", archived="false")
        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            return [], []

        active_markets = []
        now = datetime.datetime.now(datetime.timezone.utc)
        
        for m in markets:
            # Check Active only (Funded seems unreliable)
            if not m.active:
                continue
                
            # Liquidity / Volume Filter
            # Relaxed Thresholds: Vol > 50k OR Liq > 10k
            if m.volume < 50000 and m.liquidity < 10000:
                 continue

            # Date Filter
            try:
                # m.end is ISO string "2024-01-01T..."
                # Handle "Z" for UTC
                end_str = m.end.replace('Z', '+00:00')
                end_date = datetime.datetime.fromisoformat(end_str)
                if end_date < now:
                    continue
            except Exception as e:
                logger.warning(f"Date parse error for market {m.id}: {e}")
                continue

            active_markets.append(m)

        logger.info(f"Filtered markets for trading: {len(active_markets)} / {len(markets)}")
        
        high_prob = []
        arb_opps = []
        
        for market in active_markets:
            try:
                # outcome_prices is a string like "['0.5', '0.5']"
                prices = ast.literal_eval(market.outcome_prices)
                outcomes = ast.literal_eval(market.outcomes)
                
                if not prices or len(prices) < 2:
                    continue
                
                prices = [float(p) for p in prices]
                
                # High Probability Check
                for idx, price in enumerate(prices):
                    if price >= self.config.MIN_PROB:
                        high_prob.append({
                            "market": market,
                            "outcome_idx": idx,
                            "outcome": outcomes[idx],
                            "price": price,
                            "type": "high_prob"
                        })
                
                # Arbitrage Check (Binary only for simplicity)
                if len(prices) == 2:
                    sum_price = sum(prices)
                    if sum_price < 0.98: # 2% buffer for spread/fees/slippage
                        arb_opps.append({
                             "market": market,
                             "sum_price": sum_price,
                             "type": "arb"
                        })
                        
            except Exception as e:
                logger.error(f"Error processing market {market.id}: {e}")
                continue
                
        return high_prob, arb_opps

class Validator:
    def __init__(self, config: Config):
        self.config = config
        self.api_url = "https://api.perplexity.ai/chat/completions"

    def validate(self, opportunity: Dict) -> Tuple[bool, str, float]:
        """
        Validates a trade opportunity using Perplexity.
        Returns: (is_valid, reason, confidence_score)
        """
        if not self.config.PERPLEXITY_API_KEY:
            return True, "No Perplexity Key, skipping validation", 1.0

        market: SimpleMarket = opportunity["market"]
        question = market.question
        outcome = opportunity.get("outcome", "Generic")
        price = opportunity.get("price", 0)
        
        prompt = f"""
        Analyze the Polymarket market: "{question}".
        Current price for outcome "{outcome}" is {price} (implied probability {price*100}%).
        
        Rules:
        - Analyze recent news, polls, and statistical data.
        - Determine if the true probability is significantly higher than {price}.
        - Output a JSON with keys: "confidence" (0.0 to 1.0), "recommendation" (BET or PASS), "reason".
        
        Only recommend BET if confidence > 0.92.
        """
        
        headers = {
            "Authorization": f"Bearer {self.config.PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "sonar-pro",
            "messages": [
                {"role": "system", "content": "You are a superforecaster AI."},
                {"role": "user", "content": prompt}
            ]
        }
        
        try:
            response = requests.post(self.api_url, json=payload, headers=headers)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            
            # Simple parsing (robustness improvement needed in prod)
            import re
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                confidence = float(data.get("confidence", 0))
                rec = data.get("recommendation", "PASS")
                logger.info(f"LLM Analysis: {rec} (Conf: {confidence}) - {data.get('reason')}")
                return (rec == "BET" and confidence > 0.92), data.get("reason", ""), confidence
            else:
                logger.warning(f"Could not parse LLM response: {content}")
                return False, "Parse Error", 0.0

        except Exception as e:
            logger.error(f"Validator Error: {e}")
            return False, str(e), 0.0

class Bot:
    def __init__(self):
        self.config = Config()
        self.pm = SafePolymarket()
        self.scanner = Scanner(self.pm, self.config)
        self.validator = Validator(self.config)
        
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
                
        while True:
            try:
                high_prob, arb = self.scanner.get_candidates()
                logger.info(f"Found {len(high_prob)} high-prob, {len(arb)} arb opportunities.")
                
                # Process High Prob
                for opp in high_prob:
                    logger.info(f"Analyzing {opp['market'].question} - {opp['outcome']} @ {opp['price']}")
                    is_valid, reason, conf = self.validator.validate(opp)
                    
                    if is_valid:
                        self.save_state({
                            "last_decision": f"BET: {opp['market'].question[:50]}...",
                            "confidence": conf,
                            "reason": reason
                        })
                        if not dry_run:
                            self.execute_trade(opp)
                        else:
                            logger.info("Dry Run: Would trade.")
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
                logger.info("Sleeping for 30 minutes...")
                time.sleep(1800)
                
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

    def execute_trade(self, opportunity):
        """Execute a trade based on the validated opportunity"""
        try:
            market = opportunity['market']
            outcome = opportunity['outcome']  # "Yes" or "No"
            price = opportunity['price']
            
            # Get token ID for the outcome
            token_ids = ast.literal_eval(market.clob_token_ids)
            token_id = token_ids[0] if outcome.lower() == "yes" else token_ids[1]
            
            # Calculate size based on fixed bet amount
            bet_amount = float(os.getenv("MAX_BET_USD", "0.50"))  # Small default for safety
            size = bet_amount / price
            
            # Check balance
            balance = self.pm.get_usdc_balance()
            if balance < bet_amount + 1:
                logger.warning(f"Insufficient balance: ${balance:.2f} < ${bet_amount + 1:.2f}")
                return
            
            logger.info(f"Executing Trade: {outcome} on '{market.question[:40]}...' @ ${bet_amount}")
            
            # Create and post order
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import BUY
            
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=BUY
            )
            signed_order = self.pm.client.create_order(order_args)
            result = self.pm.client.post_order(signed_order)
            
            logger.info(f"Order Result: {result}")
            self.save_state({
                "last_trade": f"{outcome} @ ${bet_amount} on '{market.question[:30]}...'",
                "last_trade_result": str(result),
                "last_trade_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
        except Exception as e:
            logger.error(f"Trade Execution Failed: {e}")
            self.save_state({"last_trade_error": str(e)})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Run without executing trades")
    args = parser.parse_args()
    
    bot = Bot()
    bot.run(dry_run=args.dry_run)
