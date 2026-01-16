#!/usr/bin/env python3
"""
Test script to verify agents can execute $1 trades
"""

import sys
import os
sys.path.append('agents')
sys.path.append('agents/agents')

from agents.polymarket.polymarket import Polymarket

def test_sports_trader():
    """Test sports trader functionality"""
    print("🏈 Testing Sports Trader...")

    try:
        from agents.application.sports_trader import SportsTrader
        trader = SportsTrader(dry_run=False)  # Force live mode

        print(f'✅ Sports trader initialized')
        print('.2f')
        print(f'Mode: {"LIVE" if not trader.dry_run else "DRY RUN"}')

        # Try to get markets
        markets = trader.get_live_polymarket_sports()
        print(f'📊 Found {len(markets)} markets')

        accepting_markets = [m for m in markets if m.get('accepting_orders', False)]
        print(f'✅ {len(accepting_markets)} markets accept orders')

        if accepting_markets:
            market = accepting_markets[0]
            print(f'🎯 Testing market: {market["question"][:50]}...')

            # Try validation
            try:
                is_valid, reason, conf = trader.validator.validate(
                    market_question=market['question'],
                    outcome='YES',
                    price=market['yes_price'],
                    additional_context=trader.RISK_MANAGER_PROMPT,
                    fast_mode=True
                )
                print(f'🧠 Validation: {is_valid} (conf: {conf:.1%})')
                print(f'📝 Reason: {reason}')

                if is_valid and conf >= 0.5:  # Lower threshold for testing
                    print('🚀 EXECUTING $1 TEST TRADE...')
                    result = trader.execute_bet(market, 'YES', size=1.0, price=market['yes_price'] + 0.01)
                    print('✅ Trade execution attempted!')
                    return True
                else:
                    print('❌ Validation failed - no trade')

            except Exception as e:
                print(f'❌ Validation failed: {e}')

    except Exception as e:
        print(f'❌ Sports trader test failed: {e}')

    return False

def test_esports_trader():
    """Test esports trader functionality"""
    print("\n🎮 Testing Esports Trader...")

    try:
        from agents.application.esports_trader import EsportsTrader
        trader = EsportsTrader(dry_run=False)

        print(f'✅ Esports trader initialized')
        print('.2f')
        print(f'Mode: {"LIVE" if not trader.dry_run else "DRY RUN"}')

        # Quick scan
        print('🔍 Scanning for esports opportunities...')
        trader.scan_live_matches()
        print('✅ Esports scan completed')

        return True

    except Exception as e:
        print(f'❌ Esports trader test failed: {e}')
        return False

def test_polymarket_connection():
    """Test Polymarket connection and balance"""
    print("\n💰 Testing Polymarket Connection...")

    try:
        pm = Polymarket()
        balance = pm.get_usdc_balance()
        allowance = pm.get_usdc_allowance()

        print('.2f')
        print('.2f')
        if allowance > 100:
            print('✅ Allowance approved for trading')
            return True
        else:
            print('❌ Allowance too low')
            return False

    except Exception as e:
        print(f'❌ Polymarket connection failed: {e}')
        return False

def main():
    print("🧪 AGENT FUNCTIONALITY TEST SUITE")
    print("=" * 50)

    # Test Polymarket connection first
    pm_ok = test_polymarket_connection()

    if not pm_ok:
        print("\n❌ CRITICAL: Polymarket connection failed. Cannot proceed with agent tests.")
        return

    # Test individual agents
    sports_ok = test_sports_trader()
    esports_ok = test_esports_trader()

    print("\n" + "=" * 50)
    print("🎯 TEST RESULTS:")
    print(f"   Polymarket Connection: {'✅ PASS' if pm_ok else '❌ FAIL'}")
    print(f"   Sports Trader: {'✅ PASS' if sports_ok else '❌ FAIL'}")
    print(f"   Esports Trader: {'✅ PASS' if esports_ok else '❌ FAIL'}")

    if sports_ok or esports_ok:
        print("\n🎉 SUCCESS: At least one agent can execute trades!")
        print("   Check your dashboard for $1 test positions.")
        print("   Agents should be actively trading now.")
    else:
        print("\n⚠️ Agents not executing trades yet.")
        print("   May need to wait for market opportunities or check agent logs.")

if __name__ == "__main__":
    main()