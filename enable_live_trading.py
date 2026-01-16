#!/usr/bin/env python3
"""
Enable live trading for all agents
"""

import json
import os

def enable_live_trading():
    state_file = "agents/bot_state.json"

    if not os.path.exists(state_file):
        print(f"❌ {state_file} not found")
        return

    with open(state_file, 'r') as f:
        state = json.load(f)

    # Update all agent modes to LIVE
    mode_updates = {
        "sports_trader_mode": "LIVE",
        "esports_trader_mode": "LIVE",
        "smart_trader_mode": "LIVE",
        "pyml_scalper_mode": "LIVE",
        "safe_mode": "LIVE"
    }

    updated = False
    for key, new_mode in mode_updates.items():
        if key in state and state[key] != new_mode:
            print(f"🔄 {key}: {state[key]} → {new_mode}")
            state[key] = new_mode
            updated = True
        elif key not in state:
            print(f"➕ Adding {key}: {new_mode}")
            state[key] = new_mode
            updated = True

    if updated:
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
        print("✅ All agents set to LIVE mode")
    else:
        print("ℹ️ All agents already in LIVE mode")

if __name__ == "__main__":
    enable_live_trading()