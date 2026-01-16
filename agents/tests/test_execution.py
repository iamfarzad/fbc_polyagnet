#!/usr/bin/env python3
"""
Test actual trade execution on a market that passes validation
"""

import sys
sys.path.append('agents')
sys.path.append('agents/agents')

from agents.application.sports_trader import SportsTrader, RISK_MANAGER_PROMPT

print('🚀 Testing Actual Trade Execution...')

trader = SportsTrader(dry_run=False)

# Get tradeable markets
markets = trader.get_live_polymarket_sports()
accepting_markets = [m for m in markets if m.get('accepting_orders', False)]

tradeable_markets = []
for market in accepting_markets[:10]:
    yes_price = market['yes_price']
    no_price = market['no_price']

    if (yes_price >= 0.55 or no_price >= 0.55) and max(yes_price, no_price) <= 0.9:
        if yes_price >= no_price:
            favorite_side = "YES"
            favorite_price = yes_price
        else:
            favorite_side = "NO"
            favorite_price = no_price

        tradeable_markets.append((market, favorite_side, favorite_price))

print(f'Found {len(tradeable_markets)} tradeable markets')

if tradeable_markets:
    # Test execution on first market
    market, side, price = tradeable_markets[0]

    print(f'🎯 Testing execution on: {market["question"][:50]}...')
    print(f'Side: {side}, Price: ${price:.3f}')

    # Check if validation would pass
    try:
        is_valid, reason, conf = trader.validator.validate(
            market_question=market['question'],
            outcome=side,
            price=price,
            additional_context=RISK_MANAGER_PROMPT,
            fast_mode=True
        )

        print(f'Validation: {is_valid} ({conf:.1%}) - {reason}')

        if is_valid and conf >= 0.5:
            print('✅ Validation passed - attempting $1 trade...')

            # Calculate bet size
            bet_size = min(1.0, max(1.0, trader.balance * 0.15))

            print(f'Bet size: ${bet_size:.2f}')
            print(f'Execution price: ${price + 0.01:.3f}')

            # Actually execute the trade
            print('🚀 EXECUTING TRADE...')
            result = trader.execute_bet(market, side, size=bet_size, price=price + 0.01)

            if result:
                print('✅ Trade executed successfully!')
            else:
                print('❌ Trade execution failed or returned no result')

        else:
            print('❌ Validation failed')

    except Exception as e:
        print(f'❌ Validation error: {e}')

else:
    print('❌ No tradeable markets found')