#!/usr/bin/env python3
"""
Script to revert all agents back to normal bet sizes after $1 testing is complete.
Run this when you're satisfied with the test results.
"""

import os
import re

def revert_file(filepath, changes):
    """Apply multiple string replacements to a file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        for old_text, new_text in changes.items():
            content = content.replace(old_text, new_text)

        with open(filepath, 'w') as f:
            f.write(content)

        print(f"✅ Reverted {filepath}")
        return True
    except Exception as e:
        print(f"❌ Failed to revert {filepath}: {e}")
        return False

def main():
    print("🔄 Reverting Agent Bet Sizes to Production Values")
    print("=" * 60)

    # Sports Trader - back to normal
    sports_changes = {
        "MAX_BET_USD = 1.00  # Temporarily limit to $1 for testing": "MAX_BET_USD = 50.00  # Max per position",
        "MIN_CONFIDENCE = 0.50  # Temporarily lower for testing (was 0.65)": "MIN_CONFIDENCE = 0.65  # LLM must be 65%+ confident to trade",
        "SCAN_INTERVAL = 60     # 1 minute for faster testing (was 5 minutes)": "SCAN_INTERVAL = 300    # 5 minutes between scans"
    }

    # Esports Trader - back to normal
    esports_changes = {
        "MAX_BET_USD = 1.00              # Temporarily limit to $1 for testing": "MAX_BET_USD = 20.00             # Keep positions small for quick exits"
    }

    # Smart Trader - back to normal
    smart_changes = {
        "MAX_BET_USD = 1.00                   # Temporarily limit to $1 for testing": "MAX_BET_USD = 50.00                  # Max per position"
    }

    # Scalper - back to normal
    scalper_changes = {
        "MAX_BET_USD = 1.00  # Temporarily limit to $1 for testing": "MAX_BET_USD = 100.0",
        "QUEUE_JUMP_THRESHOLD = 10.0         # Temporarily lower for testing (was 2000.0)": "QUEUE_JUMP_THRESHOLD = 2000.0       # If bid wall > $2k, jump it. Else, join it."
    }

    # Apply all changes
    changes_applied = 0
    total_changes = len(sports_changes) + len(esports_changes) + len(smart_changes) + len(scalper_changes)

    # Sports Trader
    if revert_file("agents/agents/application/sports_trader.py", sports_changes):
        changes_applied += len(sports_changes)

    # Esports Trader
    if revert_file("agents/agents/application/esports_trader.py", esports_changes):
        changes_applied += len(esports_changes)

    # Smart Trader
    if revert_file("agents/agents/application/smart_trader.py", smart_changes):
        changes_applied += len(smart_changes)

    # Scalper
    if revert_file("agents/agents/application/pyml_scalper.py", scalper_changes):
        changes_applied += len(scalper_changes)

    print("\n" + "=" * 60)
    print("📊 Reversion Results:")
    print(f"   Changes Applied: {changes_applied}/{total_changes}")

    if changes_applied == total_changes:
        print("✅ All bet sizes reverted to production values!")
        print("\n🚀 New Agent Configuration:")
        print("   • Sports Trader: $1-$50 bets, 65% confidence, 5min scans")
        print("   • Esports Trader: $1-$20 bets, real-time game data")
        print("   • Smart Trader: $1-$50 bets, political analysis")
        print("   • Scalper: $1-$100 bets, $2000 queue threshold")
        print("\n💰 Agents will now:")
        print("   • Actively compound small gains")
        print("   • Scale bet sizes with wallet balance")
        print("   • Execute real-time buy/sell opportunities")
        print("   • Maintain proper risk management")
    else:
        print("⚠️ Some changes failed to apply. Check manually.")

    print("\n📝 Next Steps:")
    print("1. git add/commit the reverted files")
    print("2. git push to main")
    print("3. fly deploy to production")
    print("4. Watch agents actively trade and compound!")

if __name__ == "__main__":
    main()