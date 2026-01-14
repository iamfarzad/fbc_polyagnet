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
        """Execute market sell (or limit sell) to close position."""
        logger.info(f"LIQUIDATING {pos['market_question']}...")
        # In a real implementation, we would call self.pm.sell(...)
        # For safety in this update, we just log and Broadcast
        
        self.context.broadcast(
            "exit_monitor",
            f"RECOMMEND SELL: {pos['market_question']} - {reason}",
            {"market_id": pos['market_id']}
        )
        
        # TODO: Implement actual sell logic using py-clob-client
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
