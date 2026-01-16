#!/usr/bin/env python3
"""
Script to enable all agents for active trading.
Ensures all agents are running and in live mode.
"""

import json
import os
from datetime import datetime

def enable_all_agents():
    """Enable all agents in bot_state.json for active trading."""
    state_file = "agents/bot_state.json"

    try:
        # Read current state
        with open(state_file, 'r') as f:
            state = json.load(f)

        # Enable all agents
        state.update({
            "safe_running": True,
            "scalper_running": True,
            "copy_trader_running": True,
            "smart_trader_running": True,
            "esports_trader_running": True,
            "sports_trader_running": True,
            "dry_run": False,  # Ensure live trading globally
            "timestamp": datetime.now().isoformat()
        })

        # Write back
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)

        print("✅ All agents enabled for live trading!")
        print("📊 Agent Status:")
        print("   • Safe Trader: ACTIVE")
        print("   • Scalper: ACTIVE")
        print("   • Copy Trader: ACTIVE")
        print("   • Smart Trader: ACTIVE")
        print("   • Esports Trader: ACTIVE")
        print("   • Sports Trader: ACTIVE")
        print("   • Live Trading: ENABLED")

        return True

    except Exception as e:
        print(f"❌ Failed to enable agents: {e}")
        return False

if __name__ == "__main__":
    enable_all_agents()