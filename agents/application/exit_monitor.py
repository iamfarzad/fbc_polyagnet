"""
Exit Monitor Agent.
Periodically re-validates open positions and triggers liquidation if confidence drops.
"""
import os
import time
import logging
import datetime
from agents.utils.context import get_context
from agents.utils.validator import Validator, SharedConfig
from agents.polymarket.polymarket import Polymarket

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - EXIT_MON - %(levelname)s - %(message)s')
logger = logging.getLogger("ExitMonitor")

class ExitMonitor:
    def __init__(self, interval_seconds=600):
        self.interval = interval_seconds
        self.context = get_context()
        self.pm = Polymarket() # For liquidating
        self.config = SharedConfig()
        self.validator = Validator(self.config, agent_name="exit_monitor")
        
    def check_exits(self):
        """Scan all open positions and re-validate."""
        positions = self.context.get_open_positions()
        if not positions:
            logger.info("No open positions to monitor.")
            return

        logger.info(f"Monitoring {len(positions)} open positions...")
        
        for pos in positions:
            market_id = pos['market_id']
            question = pos['market_question']
            outcome = pos['outcome']
            entry_price = float(pos['entry_price'])
            agent = pos['agent']
            token_id = pos.get('token_id')

            # Skip Copy Trader positions (they follow whales, not our logic)
            if agent == "copy":
                continue

            logger.info(f"Re-validating: {question[:40]}... ({outcome})")
            
            # 1. Fetch current price to check technical stop-loss
            # (Simplified: assume we can get price easily, otherwise skip)
            current_price = entry_price # Placeholder if fetch fails
            try:
                # Need token_id to fetch price efficiently
                if token_id:
                     # This is expensive if we do it for every pos. 
                     # For V1, we rely on the Validator's fresh analysis which includes checking tools
                     pass
            except: pass

            # 2. Re-run Validator (Logic Check)
            # We use a stricter prompt for holding
            try:
                is_valid, reason, confidence = self.validator.validate(
                    question, 
                    outcome, 
                    entry_price, 
                    additional_context="You are a Portfolio Risk Manager. Re-evaluate this position. If the thesis has degraded or new negative info exists, recommend EXIT."
                )
                
                # EXIT CRITERIA
                # 1. Confidence drops below 40%
                # 2. Validator explicitly says invalid (is_valid=False)
                
                should_exit = False
                exit_reason = ""
                
                if confidence < 0.40:
                    should_exit = True
                    exit_reason = f"Confidence cratered to {confidence:.2f}"
                elif not is_valid:
                     should_exit = True
                     exit_reason = f"Thesis invalid: {reason}"
                
                if should_exit:
                    logger.warning(f"🚨 EXIT TRIGGERED for {question[:30]}... Reason: {exit_reason}")
                    self.execute_liquidation(pos, exit_reason)
                else:
                    logger.info(f"✅ HOLD: {question[:20]}... (Conf: {confidence:.2f})")
                    
            except Exception as e:
                logger.error(f"Validation failed for {market_id}: {e}")

    def execute_liquidation(self, pos, reason):
        """Execute market sell (or limit sell as sweep) to close position."""
        logger.info(f"LIQUIDATING {pos['market_question']}...")
        market_id = pos['market_id']
        token_id = pos.get('token_id')
        
        if not token_id:
             logger.error(f"Cannot liquidate {market_id}: Missing token_id")
             return

        # Calculate shares to sell
        # size_usd is cost basis. We need shares count.
        # shares = size_usd / entry_price
        try:
            entry_price = float(pos.get('entry_price', 0.5))
            size_usd = float(pos.get('size_usd', 0))
            if entry_price <= 0: entry_price = 0.5 # Safety fallback
            
            shares = size_usd / entry_price
        except:
            shares = 0
        
        if shares <= 0:
             logger.error(f"Cannot liquidate: Invalid share count ({shares})")
             return

        # EXECUTE THE SELL
        result = self.pm.execute_market_sell(token_id, shares)
        
        # Broadcast and log result
        self.context.broadcast(
            "exit_monitor",
            f"EXECUTED SELL: {pos['market_question']} - Result: {result}",
            {"market_id": market_id, "status": "liquidated", "reason": reason}
        )
        
        # Log to Supabase if available
        try:
             # Just repurpose log_trade with status='liquidated'
             from agents.utils.supabase_client import get_supabase_state
             supa = get_supabase_state()
             supa.log_trade(
                 agent="exit_monitor",
                 market_id=market_id,
                 market_question=pos['market_question'],
                 outcome=pos.get('outcome', 'UNK'),
                 side="SELL",
                 size_usd=size_usd, # approximate exit value? No, log cost basis for now
                 price=0.01, # We don't know fill price yet without looking up trade history
                 status="liquidated",
                 reasoning=f"Auto-Exit: {reason}"
             )
        except: pass

        # Remove position from context so we don't loop on it
        self.context.remove_position(market_id)
        # This requires order builder 'SELL' side logic similar to buy
        
    def run(self):
        logger.info("Starting Exit Monitor...")
        while True:
            try:
                self.check_exits()
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
            
            logger.info(f"Sleeping {self.interval}s...")
            time.sleep(self.interval)

if __name__ == "__main__":
    monitor = ExitMonitor()
    monitor.run()
