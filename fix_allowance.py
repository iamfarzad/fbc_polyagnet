#!/usr/bin/env python3
"""
Script to fix USDC allowance for automated trading
Run this on the deployment machine
"""

import sys
sys.path.append('agents')
sys.path.append('agents/agents')

from agents.polymarket.polymarket import Polymarket

def main():
    print("🔧 Fixing USDC Allowance for Automated Trading")

    try:
        pm = Polymarket()

        print("Checking current allowances...")
        allowance = pm.get_usdc_allowance()
        balance = pm.get_usdc_balance()

        print(f"Current allowance: ${allowance:.2f}")
        print(f"Current balance: ${balance:.2f}")

        if allowance < 1000:  # Less than $1000 allowance
            print("Allowance too low, approving trading...")
            pm.approve_trading()
            print("✅ Trading approval completed")

            # Check again
            new_allowance = pm.get_usdc_allowance()
            print(f"New allowance: ${new_allowance:.2f}")

        else:
            print("✅ Allowance already sufficient")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()