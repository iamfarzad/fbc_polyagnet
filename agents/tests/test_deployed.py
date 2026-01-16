#!/usr/bin/env python3
"""
Test script to run on the deployed machine to debug trade execution
"""

import sys
import os
sys.path.append('agents')
sys.path.append('agents/agents')

def test_polymarket_basic():
    """Test basic Polymarket functionality"""
    try:
        from agents.polymarket.polymarket import Polymarket
        pm = Polymarket()

        print("✅ Polymarket client initialized")

        # Test balance
        balance = pm.get_usdc_balance()
        print(f"✅ Balance: ${balance:.2f}")

        # Test allowance
        allowance = pm.get_usdc_allowance()
        print(f"✅ Allowance: ${allowance:.2f}")

        # Test market fetch
        markets = pm.get_all_markets(limit=2, active=True)
        print(f"✅ Found {len(markets)} markets")

        return True

    except Exception as e:
        print(f"❌ Polymarket test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_trade_execution():
    """Test trade execution"""
    try:
        from agents.application.sports_trader import SportsTrader

        print("Testing trade execution with $1 limit...")

        # Create trader with live mode
        trader = SportsTrader(dry_run=False)

        # Get markets and find one to test
        markets = trader.get_live_polymarket_sports()
        accepting_markets = [m for m in markets if m.get('accepting_orders', False)]

        print(f"Found {len(accepting_markets)} accepting markets")

        if accepting_markets:
            market = accepting_markets[0]

            # Check if it meets criteria
            yes_price = market['yes_price']
            no_price = market['no_price']

            if (yes_price >= 0.55 or no_price >= 0.55) and max(yes_price, no_price) <= 0.9:
                side = "YES" if yes_price >= no_price else "NO"
                price = max(yes_price, no_price)

                print(f"Testing market: {market['question'][:50]}...")
                print(f"Side: {side}, Price: ${price:.3f}")

                # Validate first
                try:
                    is_valid, reason, conf = trader.validator.validate(
                        market_question=market['question'],
                        outcome=side,
                        price=price,
                        additional_context=trader.RISK_MANAGER_PROMPT,
                        fast_mode=True
                    )

                    if is_valid and conf >= 0.5:
                        print("✅ Validation passed, attempting $1 trade...")

                        # Execute trade
                        result = trader.execute_bet(market, side, size=1.0, price=price + 0.01)
                        print("✅ Trade execution completed!")
                        return True
                    else:
                        print(f"❌ Validation failed: {reason}")
                        return False

                except Exception as e:
                    print(f"❌ Validation error: {e}")
                    return False
            else:
                print("❌ Market doesn't meet trading criteria")
                return False
        else:
            print("❌ No accepting markets found")
            return False

    except Exception as e:
        print(f"❌ Trade execution test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 DEPLOYED MACHINE TEST SUITE")
    print("=" * 50)

    # Test basic Polymarket functionality
    pm_ok = test_polymarket_basic()
    print()

    # Test trade execution
    trade_ok = test_trade_execution()

    print("\n" + "=" * 50)
    print("🎯 RESULTS:")
    print(f"   Polymarket Client: {'✅ PASS' if pm_ok else '❌ FAIL'}")
    print(f"   Trade Execution: {'✅ PASS' if trade_ok else '❌ FAIL'}")

    if pm_ok and trade_ok:
        print("\n🎉 SUCCESS: All tests passed! $1 trades are working!")
    else:
        print("\n⚠️ Some tests failed. Check the error messages above.")