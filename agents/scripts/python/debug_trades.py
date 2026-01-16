#!/usr/bin/env python3
"""
Debug script to understand why sports trader validates but doesn't execute trades
"""

import sys
sys.path.append('agents')
sys.path.append('agents/agents')

from agents.application.sports_trader import SportsTrader

print('🔍 Debugging Sports Trader Execution...')

# Create trader in live mode
trader = SportsTrader(dry_run=False)
print(f'Balance: ${trader.balance:.2f}')
print(f'Dry run: {trader.dry_run}')

# Get markets
markets = trader.get_live_polymarket_sports()
print(f'Found {len(markets)} total markets')

accepting_markets = [m for m in markets if m.get('accepting_orders', False)]
print(f'Found {len(accepting_markets)} markets accepting orders')

if accepting_markets:
    # Test first market
    market = accepting_markets[0]
    print(f'Testing market: {market["question"][:40]}...')
    print(f'YES price: {market["yes_price"]:.3f}')
    print(f'NO price: {market["no_price"]:.3f}')

    # Determine favorite
    if market["yes_price"] >= market["no_price"]:
        favorite_side = "YES"
        favorite_price = market["yes_price"]
    else:
        favorite_side = "NO"
        favorite_price = market["no_price"]

    print(f'Favorite side: {favorite_side} @ ${favorite_price:.3f}')

    # Check basic filters
    if favorite_price > 0.9:
        print('❌ FAIL: Price too high (>90%)')
    elif market['yes_price'] < 0.55 and market['no_price'] < 0.55:
        print('❌ FAIL: No clear favorite (<55%)')
    else:
        print('✅ PASS: Basic filters passed')

        # Test bet size calculation
        bet_size = min(1.0, max(1.0, trader.balance * 0.15))  # MAX_BET_USD = 1.0
        print(f'Calculated bet size: ${bet_size:.2f}')

        if trader.balance < 1.0:
            print('❌ FAIL: Insufficient balance')
        else:
            print('✅ PASS: Sufficient balance for $1 trade')

            # Test validation (what happens in scan_live_markets)
            print('🤖 Testing LLM validation...')
            try:
                is_valid, reason, conf = trader.validator.validate(
                    market_question=market['question'],
                    outcome=favorite_side,
                    price=favorite_price,
                    additional_context=trader.RISK_MANAGER_PROMPT,
                    fast_mode=True
                )
                print(f'Validation result: {is_valid} (conf: {conf:.1%})')
                print(f'Reason: {reason}')

                if is_valid and conf >= 0.5:  # MIN_CONFIDENCE = 0.5 for testing
                    print('🚀 WOULD EXECUTE TRADE!')
                    print('But in production, this calls:')
                    print('trader.execute_bet(market, favorite_side, size=bet_size, price=favorite_price + 0.01)')
                else:
                    print('❌ FAIL: Validation rejected trade')

            except Exception as e:
                print(f'❌ Validation error: {e}')

else:
    print('❌ No markets accepting orders found')