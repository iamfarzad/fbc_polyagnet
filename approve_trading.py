#!/usr/bin/env python3
"""
Run USDC approval for trading on Polymarket
"""

import sys
sys.path.append('agents')
sys.path.append('agents/agents')

from agents.polymarket.polymarket import Polymarket

if __name__ == "__main__":
    print("🚀 Approving USDC for Polymarket Trading...")

    pm = Polymarket()

    print("Current allowances:")
    allowance = pm.get_usdc_allowance()
    print(f"Combined allowance: ${allowance:.2f}")

    print("\nRunning approval process...")
    pm.approve_trading()

    print("\nChecking final allowances:")
    final_allowance = pm.get_usdc_allowance()
    print(f"Final allowance: ${final_allowance:.2f}")

    if final_allowance > 100:
        print("✅ SUCCESS: USDC approved for automated trading!")
    else:
        print("❌ FAILED: Allowance still insufficient")