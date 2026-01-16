#!/usr/bin/env python3
"""
Find markets that would actually trigger trades
"""

import sys
sys.path.append('agents')
sys.path.append('agents/agents')

from agents.application.sports_trader import SportsTrader

print('🎯 Finding Markets That Would Trigger Trades...')

trader = SportsTrader(dry_run=False)

# Get markets
markets = trader.get_live_polymarket_sports()
accepting_markets = [m for m in markets if m.get('accepting_orders', False)]

print(f'Found {len(accepting_markets)} markets accepting orders')

tradeable_markets = []

for market in accepting_markets[:20]:  # Check first 20
    yes_price = market['yes_price']
    no_price = market['no_price']

    # Check for clear favorite (>55%)
    if yes_price >= 0.55 or no_price >= 0.55:
        # Determine favorite
        if yes_price >= no_price:
            favorite_side = "YES"
            favorite_price = yes_price
        else:
            favorite_side = "NO"
            favorite_price = no_price

        # Check price not too high
        if favorite_price <= 0.9:
            tradeable_markets.append({
                'market': market,
                'favorite_side': favorite_side,
                'favorite_price': favorite_price,
                'question': market['question'][:60]
            })

print(f'Found {len(tradeable_markets)} potentially tradeable markets:')

for i, tm in enumerate(tradeable_markets[:5]):  # Show first 5
    print(f'{i+1}. {tm["question"]}...')
    print(f'   {tm["favorite_side"]} @ ${tm["favorite_price"]:.3f}')

if not tradeable_markets:
    print('❌ No markets currently meet trading criteria')
    print('   Need markets with one side >55% and <90%')
else:
    print(f'\n🚀 Would attempt to trade on {len(tradeable_markets)} markets!')
    print('These should trigger validation and potential execution.')